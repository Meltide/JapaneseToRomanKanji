#!/usr/bin/env python3
"""Rename Japanese audio filenames to Simplified Chinese + romaji.

Examples
--------
    マインドブランド.mp3
        -> Mind Brand.mp3
    インドア系ならトラックメイカー.mp3
        -> Indoor系Nara Track Maker.mp3
    チルノのパーフェクトさんすう教室 - miko.flac
        -> Cirno No Perfect Sansuu教室 - miko.flac

The script is a dry run by default.  Pass --apply to actually rename files.
Pass --no-loanwords to romanise katakana instead of using English loanwords.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import unicodedata
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Iterable, Iterator, Sequence

try:
    import zhconv
    from janome.tokenizer import Tokenizer
    from pykakasi import kakasi
except ImportError as exc:  # pragma: no cover - helpful message for users
    sys.stderr.write(
        "缺少依赖：%s\n"
        "请先运行：python -m pip install -r requirements.txt\n" % exc
    )
    raise SystemExit(1)


# When frozen by PyInstaller, data/ is unpacked under sys._MEIPASS.
BASE_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
DATA_DIR = BASE_DIR / "data"

DEFAULT_EXTENSIONS = (
    ".mp3", ".flac", ".wav", ".aac", ".m4a", ".ogg", ".opus",
    ".wma", ".aiff", ".aif", ".ape", ".alac", ".dsf", ".dff",
)

# Particles whose pronunciation differs from their kana spelling.
PARTICLE_READINGS = {
    "は": "wa",
    "へ": "e",
    "を": "wo",
}

# Words ending in は where は is a topic particle and therefore "wa".
HA_AS_WA_WORDS = {
    "は", "では", "には", "とは", "からは", "までは", "ろでは",
    "こんにちは", "こんばんは",
}

# Single-character particles are allowed in the hiragana segmenter.
SINGLE_PARTICLES = set("はがをにへとのもやかねよなさぞぜわ")

# Hiragana segmenter limits.
MAX_HIRA_WORD = 12
MAX_KATA_WORD = 16


# ---------------------------------------------------------------------------
# Character classes


def is_hiragana(ch: str) -> bool:
    return "\u3041" <= ch <= "\u309f"


def is_katakana(ch: str) -> bool:
    return "\u30a0" <= ch <= "\u30ff"


def is_kanji(ch: str) -> bool:
    code = ord(ch)
    return (
        0x3400 <= code <= 0x4DBF
        or 0x4E00 <= code <= 0x9FFF
        or 0xF900 <= code <= 0xFAFF
        or 0x20000 <= code <= 0x2FA1F
        or 0x30000 <= code <= 0x323AF
        or ch in "々〆"
    )


def is_japanese_punctuation(ch: str) -> bool:
    return ch in "、。，．！？「」『』（）【】〈〉《》〔〕…‥〜～・：；"


def is_japanese_char(ch: str) -> bool:
    return (
        is_hiragana(ch)
        or is_katakana(ch)
        or is_kanji(ch)
        or is_japanese_punctuation(ch)
        or ch == "\u30fc"
    )


# ---------------------------------------------------------------------------
# Small helpers


def title_word(word: str) -> str:
    """Title-case one Latin word without destroying acronyms / brand casing."""
    if not word:
        return word
    letters = [c for c in word if c.isalpha()]
    if not letters:
        return word
    # Keep acronyms and words with deliberate inner capitals (TV, iPhone, YouTube).
    if len(letters) > 1 and all(c.isupper() for c in letters) and len(letters) <= 5:
        return word
    if any(c.isupper() for c in word[1:]):
        return word
    return word[0].upper() + word[1:].lower()


def title_english(text: str) -> str:
    return " ".join(title_word(part) for part in text.split(" ") if part != "")


def normalize_unicode(text: str) -> str:
    return unicodedata.normalize("NFC", text)


# ---------------------------------------------------------------------------
# Converter


@dataclass
class Piece:
    text: str
    kind: str  # kanji | romaji | literal | space


@dataclass
class Converter:
    data_dir: Path = DATA_DIR
    extra_overrides: dict[str, str] = field(default_factory=dict)
    use_loanwords: bool = True

    def __post_init__(self) -> None:
        self.tokenizer = Tokenizer()
        self.kakasi = kakasi()
        self.katakana_english: dict[str, str] = self._load_json("katakana_english.json")
        self.hiragana_words: dict[str, int] = self._load_json("hiragana_words.json")
        self.kokuji_data: dict = self._load_json("kokuji.json")
        self.variant_map: dict[str, str] = self._load_json("variant_map.json")
        self.kokuji: set[str] = set(self.kokuji_data.get("kokuji", []))
        self.kokuji_readings: dict[str, list[str]] = self.kokuji_data.get("readings", {})
        self.name_overrides: dict[str, str] = dict(self._load_json("name_overrides.json"))
        self.name_overrides.update(self.extra_overrides)
        self.name_overrides = {
            normalize_unicode(k): v for k, v in self.name_overrides.items()
        }
        # Hiragana spellings such as ちるの / れみりあ should use the same
        # English names as their katakana counterparts.
        self.hiragana_overrides = {
            key: value
            for key, value in self.name_overrides.items()
            if key and all(is_hiragana(ch) or ch == "\u30fc" for ch in key)
        }

    def _load_json(self, name: str):
        path = self.data_dir / name
        if not path.exists():
            raise FileNotFoundError(
                f"缺少数据文件 {path}。请确认 data/ 目录完整，"
                "或重新运行 tools/build_data.py。"
            )
        with path.open("r", encoding="utf-8-sig") as fh:
            return json.load(fh)

    # -- public API ---------------------------------------------------------

    def convert_stem(self, stem: str) -> str:
        """Convert a filename stem (without extension)."""
        # Half-width katakana (ﾏｲﾝﾄﾞ) is common in older Japanese filenames.
        if any("\uff66" <= ch <= "\uff9d" for ch in stem):
            stem = unicodedata.normalize("NFKC", stem)
        stem = normalize_unicode(stem)
        pieces: list[Piece] = []
        for span, is_japanese in self._split_spans(stem):
            if not is_japanese:
                pieces.extend(self._literal_pieces(span))
                continue
            pieces.extend(self._convert_japanese_span(span))
        return self._join_pieces(pieces)

    def convert_filename(self, filename: str) -> str:
        path = Path(filename)
        suffix = path.suffix
        stem = filename[: -len(suffix)] if suffix else filename
        return self.convert_stem(stem) + suffix

    # -- span / token handling ---------------------------------------------

    @staticmethod
    def _split_spans(text: str) -> Iterator[tuple[str, bool]]:
        if not text:
            return
        start = 0
        current = is_japanese_char(text[0])
        for i, ch in enumerate(text[1:], start=1):
            flag = is_japanese_char(ch)
            if flag != current:
                yield text[start:i], current
                start = i
                current = flag
        yield text[start:], current

    @staticmethod
    def _literal_pieces(text: str) -> list[Piece]:
        pieces: list[Piece] = []
        buf: list[str] = []
        for ch in text:
            if ch.isspace():
                if buf:
                    pieces.append(Piece("".join(buf), "literal"))
                    buf = []
                pieces.append(Piece(ch, "space"))
            else:
                buf.append(ch)
        if buf:
            pieces.append(Piece("".join(buf), "literal"))
        return pieces

    def _convert_japanese_span(self, span: str) -> list[Piece]:
        pieces: list[Piece] = []
        hira_run: list[str] = []
        kata_run: list[str] = []

        def flush_hira() -> None:
            if not hira_run:
                return
            run = "".join(hira_run)
            hira_run.clear()
            for word in self._split_hiragana(run):
                value = self.hiragana_overrides.get(word) if self.use_loanwords else None
                if value:
                    pieces.extend(self._english_pieces(value))
                else:
                    pieces.append(self._romaji_piece(self._romanize_kana(word), word))

        def flush_kata() -> None:
            if not kata_run:
                return
            run = "".join(kata_run)
            kata_run.clear()
            pieces.extend(self._katakana_pieces(run))

        for token in self.tokenizer.tokenize(span):
            surface = token.surface
            if not surface:
                continue

            # Keep a middle dot inside a katakana phrase (アール・デコ).
            if surface == "・":
                if kata_run:
                    kata_run.append(surface)
                else:
                    flush_hira()
                    pieces.append(Piece(surface, "literal"))
                continue

            if self._is_pure_hiragana(surface):
                flush_kata()
                hira_run.append(surface)
                continue

            if self._is_pure_katakana(surface):
                flush_hira()
                kata_run.append(surface)
                continue

            flush_hira()
            flush_kata()

            if all(is_kanji(c) for c in surface):
                pieces.extend(
                    self._kanji_pieces(surface, token.reading or "", surface)
                )
                continue

            if all(is_japanese_punctuation(c) for c in surface):
                pieces.append(Piece(surface, "literal"))
                continue

            # Mixed token, e.g. 盗ん, 書い, 込み.
            pieces.extend(self._mixed_token_pieces(surface, token.reading or ""))

        flush_hira()
        flush_kata()
        return pieces

    @staticmethod
    def _is_pure_hiragana(text: str) -> bool:
        return bool(text) and all(is_hiragana(c) or c == "\u30fc" for c in text)

    @staticmethod
    def _is_pure_katakana(text: str) -> bool:
        return bool(text) and all(is_katakana(c) or c == "\u30fc" for c in text)

    def _mixed_token_pieces(self, surface: str, reading: str) -> list[Piece]:
        pieces: list[Piece] = []
        for text, kind in self._script_groups(surface):
            if kind == "kanji":
                pieces.extend(self._kanji_pieces(text, reading, surface))
            elif kind == "hira":
                if text:
                    value = self.hiragana_overrides.get(text) if self.use_loanwords else None
                    if value:
                        pieces.extend(self._english_pieces(value))
                    else:
                        pieces.append(
                            Piece(self._title_romaji(self._romanize_kana(text)), "romaji")
                        )
            elif kind == "kata":
                pieces.extend(self._katakana_pieces(text))
            else:
                pieces.append(Piece(text, "literal"))
        return pieces

    @staticmethod
    def _script_groups(text: str) -> list[tuple[str, str]]:
        groups: list[tuple[str, str]] = []
        if not text:
            return groups
        buf = [text[0]]
        kind = Converter._char_group(text[0])
        for ch in text[1:]:
            new_kind = Converter._char_group(ch)
            if new_kind == kind or (kind == "hira" and ch == "ー") or (kind == "kata" and ch == "ー"):
                buf.append(ch)
            else:
                groups.append(("".join(buf), kind))
                buf = [ch]
                kind = new_kind
        groups.append(("".join(buf), kind))
        return groups

    @staticmethod
    def _char_group(ch: str) -> str:
        if is_kanji(ch):
            return "kanji"
        if is_hiragana(ch):
            return "hira"
        if is_katakana(ch):
            return "kata"
        return "other"

    # -- hiragana -----------------------------------------------------------

    def _split_hiragana(self, run: str) -> list[str]:
        """Segment a hiragana run with a small dictionary + DP."""
        n = len(run)
        if n <= 1:
            return [run] if run else []

        neg = float("-inf")
        best_score = [neg] * (n + 1)
        back: list[tuple[int, str] | None] = [None] * (n + 1)
        best_score[0] = 0.0

        for i in range(n):
            if best_score[i] == neg:
                continue
            # Known words, longest first.  Prefer longer, frequent words.
            for end in range(min(n, i + MAX_HIRA_WORD), i + 1, -1):
                word = run[i:end]
                if len(word) < 2:
                    continue
                override = self.hiragana_overrides.get(word)
                if override is not None:
                    score = best_score[i] + len(word) * len(word) + 100.0
                else:
                    freq = self.hiragana_words.get(word)
                    if freq is None:
                        continue
                    score = best_score[i] + len(word) * len(word) + freq * 0.4
                if score > best_score[end]:
                    best_score[end] = score
                    back[end] = (i, word)
            # Single-character fallback.  Particles are worth more than random kana.
            ch = run[i]
            score = best_score[i] + (1.0 if ch in SINGLE_PARTICLES else 0.05)
            if score > best_score[i + 1]:
                best_score[i + 1] = score
                back[i + 1] = (i, ch)

        if back[n] is None:
            return [run]

        words: list[str] = []
        pos = n
        while pos > 0:
            entry = back[pos]
            if entry is None:
                return [run]
            start, word = entry
            words.append(word)
            pos = start
        words.reverse()
        return words

    def _romanize_kana(self, text: str) -> str:
        """Hiragana/katakana -> lowercase Hepburn romaji."""
        result = self.kakasi.convert(text)
        return "".join(item.get("hepburn", "") for item in result).strip()

    @staticmethod
    def _title_romaji(text: str) -> str:
        return " ".join(title_word(part) for part in text.split(" "))

    def _romaji_piece(self, romaji: str, original: str) -> Piece:
        """Turn a romanised kana word into a display piece, handling particles."""
        lower = romaji.lower()
        if original in PARTICLE_READINGS:
            lower = PARTICLE_READINGS[original]
        elif original in HA_AS_WA_WORDS and lower.endswith("ha"):
            lower = lower[:-2] + "wa"
        return Piece(self._title_romaji(lower), "romaji")

    # -- katakana -----------------------------------------------------------

    def _katakana_pieces(self, text: str) -> list[Piece]:
        key = normalize_unicode(text)
        plain = key.replace("・", "")
        if not self.use_loanwords:
            return self._katakana_romaji_pieces(key)
        value = self.name_overrides.get(key) or self.name_overrides.get(plain)
        if value is None:
            value = self.katakana_english.get(key) or self.katakana_english.get(plain)
        if value is not None:
            return self._english_pieces(value)

        # Unknown katakana: fall back to romaji.  For short words this is almost
        # always a name, so do not split it into accidental dictionary words.
        if len(plain) <= 5:
            return self._english_pieces(self._romanize_kana(plain))

        segments = self._segment_katakana(plain)
        known_len = sum(len(s) for s, known in segments if known)
        if known_len < len(plain) * 0.6:
            return self._english_pieces(self._romanize_kana(plain))

        pieces: list[Piece] = []
        for segment, known in segments:
            if known:
                value = self.name_overrides.get(segment) or self.katakana_english.get(segment)
                if value:
                    pieces.extend(self._english_pieces(value))
                    continue
            pieces.extend(self._english_pieces(self._romanize_kana(segment)))
        return pieces

    def _katakana_romaji_pieces(self, text: str) -> list[Piece]:
        """Romanise katakana without replacing it with an English loanword."""
        if not text:
            return []
        if "・" in text:
            pieces: list[Piece] = []
            for part in text.split("・"):
                if part:
                    pieces.extend(self._english_pieces(self._romanize_kana(part)))
            return pieces

        full_value = self.name_overrides.get(text) or self.katakana_english.get(text)

        if full_value and " " not in full_value:
            segments = [(text, True)]
        elif full_value:
            # "track maker" tells us how to split トラックメイカー, but
            # "personal computer" must not split パソコン into パソ + コン.
            candidate = self._segment_katakana(text, skip_full=True)
            if self._segments_match_words(candidate, full_value.split()):
                segments = candidate
            else:
                segments = [(text, False)]
        else:
            segments = self._segment_katakana(text)
            known_len = sum(len(segment) for segment, known in segments if known)
            if known_len < len(text) * 0.6:
                segments = [(text, False)]

        pieces: list[Piece] = []
        for segment, _known in segments:
            romaji = self._romanize_kana(segment)
            pieces.extend(self._english_pieces(romaji))
        return pieces

    def _segments_match_words(
        self, segments: list[tuple[str, bool]], words: list[str]
    ) -> bool:
        if len(segments) != len(words) or len(segments) < 2:
            return False
        for (segment, _known), word in zip(segments, words):
            if len(segment) < 2:
                return False
            source = self.name_overrides.get(segment) or self.katakana_english.get(segment)
            source_text = source if source else self._romanize_kana(segment)
            source_letters = re.sub(r"[^a-z]", "", source_text.lower())
            target = re.sub(r"[^a-z]", "", word.lower())
            if not source_letters or not target:
                return False
            if SequenceMatcher(None, source_letters, target).ratio() < 0.45:
                return False
        return True

    def _segment_katakana(self, text: str, skip_full: bool = False) -> list[tuple[str, bool]]:
        n = len(text)
        neg = float("-inf")
        best = [neg] * (n + 1)
        back: list[tuple[int, str, bool] | None] = [None] * (n + 1)
        best[0] = 0.0

        for i in range(n):
            if best[i] == neg:
                continue
            for end in range(min(n, i + MAX_KATA_WORD), i + 1, -1):
                word = text[i:end]
                if len(word) < 2:
                    continue
                if skip_full and i == 0 and end == n:
                    continue
                if word in self.katakana_english or word in self.name_overrides:
                    score = best[i] + len(word) * len(word) * 10
                    if score > best[end]:
                        best[end] = score
                        back[end] = (i, word, True)
            score = best[i] - 1.0
            if score > best[i + 1]:
                best[i + 1] = score
                back[i + 1] = (i, text[i], False)

        if back[n] is None:
            return [(text, False)]

        raw: list[tuple[str, bool]] = []
        pos = n
        while pos > 0:
            entry = back[pos]
            if entry is None:
                return [(text, False)]
            start, word, known = entry
            raw.append((word, known))
            pos = start
        raw.reverse()

        # Merge adjacent unknown characters into one fallback segment.
        merged: list[tuple[str, bool]] = []
        for word, known in raw:
            if not known and merged and not merged[-1][1]:
                merged[-1] = (merged[-1][0] + word, False)
            else:
                merged.append((word, known))
        return merged

    def _english_pieces(self, value: str) -> list[Piece]:
        value = normalize_unicode(value).strip()
        if not value:
            return []
        pieces: list[Piece] = []
        for part in re.split(r"(\s+)", value):
            if not part:
                continue
            if part.isspace():
                pieces.append(Piece(" ", "space"))
            else:
                pieces.append(Piece(title_english(part), "romaji"))
        return pieces

    # -- kanji --------------------------------------------------------------

    def _kanji_pieces(self, text: str, reading: str, surface: str) -> list[Piece]:
        if not any(ch in self.kokuji for ch in text):
            return [Piece(self._simplify_kanji(text), "kanji")]

        pieces: list[Piece] = []
        buf: list[str] = []
        for ch in text:
            if ch in self.kokuji:
                if buf:
                    pieces.append(Piece(self._simplify_kanji("".join(buf)), "kanji"))
                    buf = []
                romaji = self._kokuji_romaji(ch, reading, surface)
                if romaji:
                    pieces.append(Piece(title_english(romaji), "romaji"))
            else:
                buf.append(ch)
        if buf:
            pieces.append(Piece(self._simplify_kanji("".join(buf)), "kanji"))
        return pieces

    def _simplify_kanji(self, text: str) -> str:
        converted = zhconv.convert(text, "zh-cn")
        if len(converted) != len(text):
            converted = "".join(zhconv.convert(ch, "zh-cn") for ch in text)
        out: list[str] = []
        for original, simplified in zip(text, converted):
            out.append(self.variant_map.get(original, simplified))
        return "".join(out)

    def _kokuji_romaji(self, ch: str, token_reading: str, surface: str) -> str:
        # Best case: the token is exactly the kokuji, so Janome knows the reading.
        if surface == ch and token_reading and token_reading != "*":
            return self._romanize_kana(token_reading)

        # Mixed token with okurigana: subtract the okurigana from the reading.
        if token_reading and token_reading != "*" and surface.endswith(ch):
            suffix = surface[surface.index(ch) + 1:]
            if suffix and all(is_hiragana(c) or is_katakana(c) for c in suffix):
                full = self._romanize_kana(token_reading)
                suffix_romaji = self._romanize_kana(suffix)
                if suffix_romaji and full.endswith(suffix_romaji):
                    return full[: -len(suffix_romaji)]

        # Otherwise use pykakasi's single-character reading.
        romaji = self._romanize_kana(ch)
        if romaji:
            return romaji
        readings = self.kokuji_readings.get(ch, [])
        if readings:
            first = readings[0].rstrip(".")
            return self._romanize_kana(first)
        return ""

    # -- assembly -----------------------------------------------------------

    @staticmethod
    def _join_pieces(pieces: Sequence[Piece]) -> str:
        out: list[str] = []
        prev_kind: str | None = None
        for piece in pieces:
            if not piece.text:
                continue
            if piece.kind == "space":
                out.append(piece.text)
                prev_kind = "space"
                continue
            if piece.kind == "romaji":
                if prev_kind == "romaji" and out and not out[-1].endswith((" ", "\t")):
                    out.append(" ")
                out.append(piece.text)
                prev_kind = "romaji"
                continue
            out.append(piece.text)
            prev_kind = piece.kind
        return "".join(out)


# ---------------------------------------------------------------------------
# Filename safety / collisions


WINDOWS_INVALID = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
WINDOWS_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def safe_filename(name: str) -> str:
    """Make a converted name safe for Windows without changing normal names."""
    name = WINDOWS_INVALID.sub("_", name)
    name = name.rstrip(" .")
    if not name:
        name = "_"
    stem, suffix = os.path.splitext(name)
    if stem.upper() in WINDOWS_RESERVED:
        stem = "_" + stem
    return stem + suffix


def unique_target(target: Path) -> Path:
    if not target.exists():
        return target
    stem, suffix = target.stem, target.suffix
    for i in range(1, 10_000):
        candidate = target.with_name(f"{stem} ({i}){suffix}")
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"无法为 {target} 找到不冲突的文件名")


# ---------------------------------------------------------------------------
# CLI


def iter_audio_files(folder: Path, recursive: bool, extensions: set[str]) -> Iterable[Path]:
    iterator = folder.rglob("*") if recursive else folder.glob("*")
    for path in sorted(iterator, key=lambda p: str(p).lower()):
        if path.is_file() and path.suffix.lower() in extensions:
            yield path


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="把音频文件名中的日文转换为「简体汉字 + 罗马音」。默认只预览，不修改文件。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例：\n"
            "  python rename_audio.py D:\\Music\n"
            "  python rename_audio.py D:\\Music --apply\n"
            "  python rename_audio.py D:\\Music --recursive --apply\n"
        ),
    )
    parser.add_argument("folder", type=Path, help="要处理的文件夹")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true", help="真正重命名（默认只预览）")
    mode.add_argument("--dry-run", action="store_true", help="只预览（默认行为）")
    parser.add_argument("--recursive", "-r", action="store_true", help="递归处理子文件夹")
    parser.add_argument(
        "--extensions",
        default=",".join(DEFAULT_EXTENSIONS),
        help="要处理的扩展名，逗号分隔（默认：常见音频格式）",
    )
    parser.add_argument(
        "--overrides",
        type=Path,
        help="额外的片假名/名称覆盖表（JSON，例如 {\"チルノ\": \"Cirno\"}）",
    )
    parser.add_argument(
        "--no-loanwords",
        "--katakana-romaji",
        dest="no_loanwords",
        action="store_true",
        help="片假名只转罗马音，不还原为英语/外来语原文",
    )
    parser.add_argument("--quiet", "-q", action="store_true", help="只输出汇总")
    parser.add_argument("--version", action="version", version="%(prog)s 1.0.0")
    args = parser.parse_args(argv)

    folder: Path = args.folder
    if not folder.exists() or not folder.is_dir():
        parser.error(f"文件夹不存在或不是目录：{folder}")

    extensions = {
        ("." + ext.strip().lstrip(".")).lower()
        for ext in args.extensions.split(",")
        if ext.strip()
    }

    extra_overrides: dict[str, str] = {}
    if args.overrides:
        try:
            with args.overrides.open("r", encoding="utf-8-sig") as fh:
                extra_overrides = json.load(fh)
        except (OSError, json.JSONDecodeError) as exc:
            parser.error(f"无法读取覆盖表 {args.overrides}：{exc}")
        if not isinstance(extra_overrides, dict) or not all(
            isinstance(k, str) and isinstance(v, str) for k, v in extra_overrides.items()
        ):
            parser.error("覆盖表必须是 JSON 对象，例如 {\"チルノ\": \"Cirno\"}")

    converter = Converter(
        extra_overrides=extra_overrides,
        use_loanwords=not args.no_loanwords,
    )

    files = list(iter_audio_files(folder, args.recursive, extensions))
    if not files:
        print(f"在 {folder} 中没有找到音频文件。")
        return 0

    renamed = 0
    skipped = 0
    failed = 0
    preview_only = not args.apply

    for path in files:
        old_name = path.name
        try:
            new_name = safe_filename(converter.convert_filename(old_name))
        except Exception as exc:  # keep processing other files
            failed += 1
            print(f"[转换失败] {path}: {exc}", file=sys.stderr)
            continue

        if new_name == old_name:
            skipped += 1
            if not args.quiet:
                print(f"[跳过] {old_name}")
            continue

        target = path.with_name(new_name)
        if target.exists() and target != path:
            target = unique_target(target)

        if preview_only:
            renamed += 1
            if not args.quiet:
                print(f"[预览] {old_name}  ->  {target.name}")
            continue

        try:
            path.rename(target)
        except OSError as exc:
            failed += 1
            print(f"[重命名失败] {path}: {exc}", file=sys.stderr)
            continue

        renamed += 1
        if not args.quiet:
            print(f"[完成] {old_name}  ->  {target.name}")

    verb = "可重命名" if preview_only else "已重命名"
    print(
        f"\n{verb} {renamed} 个文件，跳过 {skipped} 个，失败 {failed} 个。"
        + ("（预览模式；加 --apply 才会真正改名）" if preview_only else "")
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
