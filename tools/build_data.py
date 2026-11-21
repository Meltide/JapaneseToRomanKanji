"""Build runtime data files from JMdict and KANJIDIC2.

This is a development tool; the shipped program only reads data/*.json.

Download the two source files first (they are not distributed with this
program), then run this script from the project root:

    New-Item -ItemType Directory -Force .tmp/jmdict
    curl.exe -L -o .tmp/jmdict/JMdict_e.gz http://ftp.edrdg.org/pub/Nihongo/JMdict_e.gz
    curl.exe -L -o .tmp/jmdict/kanjidic2.xml.gz http://ftp.edrdg.org/pub/Nihongo/kanjidic2.xml.gz
    python tools/build_data.py

Rebuilding is only necessary when you want to refresh the dictionaries or
change the selection rules below.
"""
from __future__ import annotations

import gzip
import json
import re
import xml.etree.ElementTree as ET
from difflib import SequenceMatcher
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / ".tmp" / "jmdict"
DATA = ROOT / "data"

XML_LANG = "{http://www.w3.org/XML/1998/namespace}lang"
KATAKANA_RE = re.compile(r"^[\u30a0-\u30ff\u30fc\u30fb]+$")
LATIN_RE = re.compile(r"^[A-Za-zÀ-ÖØ-öø-ÿ][A-Za-zÀ-ÖØ-öø-ÿ'’ .&/+-]*$")
PAREN_RE = re.compile(r"\s*\([^)]*\)")
SPACE_RE = re.compile(r"\s+")

# Characters which are Japanese-specific enough that a Chinese reading would
# be misleading.  Kept deliberately small; users can extend name_overrides.
FORCE_ROMANJI = set("咲")

# Common Japanese variant/gaiji forms that OpenCC/zhconv leaves untouched.
MANUAL_VARIANTS = {
    "髙": "高",
    "﨑": "崎",
    "神": "神",
    "塚": "塚",
    "都": "都",
    "福": "福",
    "靑": "青",
    "濵": "滨",
    "邉": "边",
    "邊": "边",
    "𠮷": "吉",
    "𠮟": "叱",
    "竈": "灶",
    "嶋": "岛",
    "嶌": "岛",
    "冨": "富",
    "冱": "冱",
    "凉": "凉",
    "爲": "为",
}


def simple_romaji(text: str) -> str:
    """Cheap katakana romanisation used only to score English glosses."""
    table = {
        "ア": "a", "イ": "i", "ウ": "u", "エ": "e", "オ": "o",
        "カ": "ka", "キ": "ki", "ク": "ku", "ケ": "ke", "コ": "ko",
        "サ": "sa", "シ": "shi", "ス": "su", "セ": "se", "ソ": "so",
        "タ": "ta", "チ": "chi", "ツ": "tsu", "テ": "te", "ト": "to",
        "ナ": "na", "ニ": "ni", "ヌ": "nu", "ネ": "ne", "ノ": "no",
        "ハ": "ha", "ヒ": "hi", "フ": "fu", "ヘ": "he", "ホ": "ho",
        "マ": "ma", "ミ": "mi", "ム": "mu", "メ": "me", "モ": "mo",
        "ヤ": "ya", "ユ": "yu", "ヨ": "yo",
        "ラ": "ra", "リ": "ri", "ル": "ru", "レ": "re", "ロ": "ro",
        "ワ": "wa", "ヲ": "wo", "ン": "n",
        "ガ": "ga", "ギ": "gi", "グ": "gu", "ゲ": "ge", "ゴ": "go",
        "ザ": "za", "ジ": "ji", "ズ": "zu", "ゼ": "ze", "ゾ": "zo",
        "ダ": "da", "ヂ": "ji", "ヅ": "zu", "デ": "de", "ド": "do",
        "バ": "ba", "ビ": "bi", "ブ": "bu", "ベ": "be", "ボ": "bo",
        "パ": "pa", "ピ": "pi", "プ": "pu", "ペ": "pe", "ポ": "po",
        "ヴ": "vu", "ァ": "a", "ィ": "i", "ゥ": "u", "ェ": "e", "ォ": "o",
        "ャ": "ya", "ュ": "yu", "ョ": "yo", "ッ": "", "ー": "",
    }
    out = []
    i = 0
    while i < len(text):
        ch = text[i]
        if ch in "ャュョ" and i:
            # combine with preceding consonant + i
            pass
        if ch in table:
            out.append(table[ch])
        i += 1
    return "".join(out)


def clean_gloss(gloss: str) -> str | None:
    gloss = PAREN_RE.sub("", gloss).strip().strip(";,")
    gloss = re.sub(r"^(?:a|an|the|to)\s+", "", gloss, flags=re.I)
    gloss = SPACE_RE.sub(" ", gloss)
    if not gloss or len(gloss) > 48:
        return None
    if not LATIN_RE.match(gloss):
        return None
    return gloss


def gloss_similarity(reading: str, gloss: str) -> float:
    romaji = simple_romaji(reading).replace("-", "").replace(" ", "")
    letters = re.sub(r"[^a-z]", "", gloss.lower())
    if not romaji or not letters:
        return 0.0
    score = SequenceMatcher(None, romaji, letters).ratio()
    if " " in gloss:
        score -= 0.03
    return score


def best_first_sense_gloss(glosses: list[str], reading: str) -> tuple[str, float] | None:
    best: tuple[str, float] | None = None
    for gloss in glosses:
        cleaned = clean_gloss(gloss)
        if not cleaned:
            continue
        cleaned = cleaned.strip("- ").strip()
        if not cleaned:
            continue
        score = gloss_similarity(reading, cleaned)
        if best is None or score > best[1]:
            best = (cleaned, score)
    return best


def join_lsource(group: list[tuple[str, str | None]]) -> str | None:
    full = [text for text, typ in group if typ != "part"]
    parts = [text for text, typ in group if typ == "part"]
    chosen = full if full else parts
    if not chosen:
        return None
    # A trailing hyphen marks a prefix ("inter-" + "net" -> "internet").
    if any(text.endswith("-") for text in chosen):
        return "".join(text.rstrip("-") for text in chosen)
    return " ".join(chosen)


def build_katakana() -> dict[str, str]:
    mapping: dict[str, str] = {}
    best_scores: dict[str, float] = {}
    for event, elem in ET.iterparse(gzip.open(RAW / "JMdict_e.gz", "rb"), events=("end",)):
        if elem.tag != "entry":
            continue
        readings = [r.text for r in elem.findall("./r_ele/reb") if r.text]
        katakana_readings = [r for r in readings if KATAKANA_RE.match(r) and len(r) >= 2]
        if not katakana_readings:
            elem.clear()
            continue

        priorities = [p.text for p in elem.findall("./r_ele/re_pri") if p.text]
        is_gai = any(p.startswith("gai") for p in priorities)
        kebs = [k.text for k in elem.findall("./k_ele/keb") if k.text]
        has_kanji_keb = any(any("\u3400" <= c <= "\u9fff" for c in k) for k in kebs)
        first_sense = elem.find("sense")
        first_glosses = (
            [g.text for g in first_sense.findall("gloss") if g.text]
            if first_sense is not None
            else []
        )

        eng_full: list[tuple[str, str | None]] = []
        eng_parts: list[tuple[str, str | None]] = []
        other_full: list[tuple[str, str | None]] = []
        other_parts: list[tuple[str, str | None]] = []
        for sense in elem.findall("./sense"):
            for ls in sense.findall("lsource"):
                text = (ls.text or "").strip()
                if not text:
                    continue
                lang = ls.get(XML_LANG) or ""
                typ = ls.get("ls_type")
                target = eng_full if lang == "eng" and typ != "part" else (
                    eng_parts if lang == "eng" else (
                        other_full if typ != "part" else other_parts
                    )
                )
                target.append((text, typ))

        candidates: list[tuple[str, float]] = []
        # 1. A complete English lsource is the strongest signal.
        if eng_full:
            value = join_lsource(eng_full)
            if value:
                candidates.append((value, 5.0))
        # 2. The first sense's gloss is usually the modern English word.
        gloss_candidate = best_first_sense_gloss(first_glosses, katakana_readings[0])
        if gloss_candidate:
            gloss, sim = gloss_candidate
            if is_gai:
                # アルバイト (Arbeit) must not become "part-time job", but
                # ビール (Bier) should become the familiar English "beer".
                if sim >= 0.42 or not other_full:
                    candidates.append((gloss, 6.0))
            elif sim >= 0.45 and not has_kanji_keb:
                candidates.append((gloss, 3.0))
        # 3. A complete non-English source is better than a poor translation.
        if other_full:
            value = join_lsource(other_full)
            if value:
                candidates.append((value, 4.0))
        # 4. Partial sources are a last resort; prefer them over fallback romaji.
        for group in (eng_parts, other_parts):
            if group:
                value = join_lsource(group)
                if value:
                    candidates.append((value, 2.0))

        if not candidates:
            elem.clear()
            continue

        gai_bonus = 1.5 if is_gai else 0.0
        best_value = None
        best_score = -1.0
        for value, rank in candidates:
            value = SPACE_RE.sub(" ", value).strip().strip(".").strip()
            value = value.strip("- ")
            if not value or not LATIN_RE.match(value):
                continue
            source_reading = katakana_readings[0]
            score = rank + gloss_similarity(source_reading, value) * 0.5 + gai_bonus
            if score > best_score or (score == best_score and best_value and len(value) < len(best_value)):
                best_value = value
                best_score = score

        if not best_value:
            elem.clear()
            continue
        for reading in katakana_readings:
            old_score = best_scores.get(reading, -1.0)
            if best_score > old_score:
                mapping[reading] = best_value
                best_scores[reading] = best_score
            elif best_score == old_score and len(best_value) < len(mapping.get(reading, best_value)):
                mapping[reading] = best_value
        elem.clear()
    return mapping


def kata_to_hira(text: str) -> str:
    out = []
    for ch in text:
        code = ord(ch)
        if 0x30A1 <= code <= 0x30F6:
            out.append(chr(code - 0x60))
        else:
            out.append(ch)
    return "".join(out)


def build_hiragana_words() -> dict[str, int]:
    words: dict[str, int] = {}
    priority_bonus = {
        "ichi1": 6, "news1": 5, "news2": 4, "spec1": 3, "spec2": 2,
        "gai1": 2, "gai2": 1,
    }
    for event, elem in ET.iterparse(gzip.open(RAW / "JMdict_e.gz", "rb"), events=("end",)):
        if elem.tag != "entry":
            continue
        readings = [r.text for r in elem.findall("./r_ele/reb") if r.text]
        kebs = [k.text for k in elem.findall("./k_ele/keb") if k.text]
        priorities = [p.text for p in elem.findall("./r_ele/re_pri") if p.text]
        has_priority = any(
            p in priority_bonus or (p.startswith("nf") and p[2:].isdigit())
            for p in priorities
        )
        hira_keb = any(all(("\u3041" <= c <= "\u309f") or c == "\u30fc" for c in k) for k in kebs)
        if not has_priority and not hira_keb:
            elem.clear()
            continue
        bonus = 0
        for p in priorities:
            if p in priority_bonus:
                bonus = max(bonus, priority_bonus[p])
            elif p.startswith("nf") and p[2:].isdigit():
                bonus = max(bonus, 4)
        if hira_keb:
            bonus += 2
        for reading in readings:
            word = kata_to_hira(reading)
            if not (2 <= len(word) <= 10):
                continue
            if not all(("\u3041" <= c <= "\u309f") or c == "\u30fc" for c in word):
                continue
            words[word] = max(words.get(word, 0), bonus)
        elem.clear()
    # Frequent auxiliary / conjugational chunks that JMdict does not list.
    aux = {
        "ました": 8, "ません": 8, "ましょう": 8, "でした": 8, "でしょう": 8,
        "だった": 6, "だったら": 6, "ます": 5, "です": 5, "なら": 4,
        "ている": 5, "ています": 5, "てる": 4, "ちゃう": 4, "じゃう": 4,
        "ない": 5, "なかった": 5, "たく": 4, "たかった": 4, "れる": 3,
        "られる": 3, "せる": 3, "させる": 3, "たい": 4, "そう": 3,
        "よう": 3, "らしい": 4, "みたい": 4, "ください": 6, "ござい": 5,
        "ございます": 7, "おります": 6, "いたします": 6, "ありがとう": 7,
        "おはよう": 6, "こんにちは": 7, "こんばんは": 7, "さようなら": 7,
        "すみません": 7, "ごめんなさい": 7,
    }
    for word, score in aux.items():
        words[word] = max(words.get(word, 0), score)
    return words


def build_kokuji() -> tuple[set[str], dict[str, list[str]]]:
    kokuji: set[str] = set()
    readings: dict[str, list[str]] = {}
    for event, elem in ET.iterparse(gzip.open(RAW / "kanjidic2.xml.gz", "rb"), events=("end",)):
        if elem.tag != "character":
            continue
        lit = elem.findtext("literal")
        if not lit:
            elem.clear()
            continue
        meanings = [m.text or "" for m in elem.findall("./reading_meaning/rmgroup/meaning")]
        if any("kokuji" in m for m in meanings):
            kokuji.add(lit)
        kun = [r.text for r in elem.findall("./reading_meaning/rmgroup/reading") if r.get("r_type") == "ja_kun" and r.text]
        if kun:
            readings[lit] = kun
        elem.clear()
    kokuji.update(FORCE_ROMANJI)
    return kokuji, readings


def main() -> None:
    DATA.mkdir(exist_ok=True)
    print("building katakana lexicon ...")
    katakana = build_katakana()
    (DATA / "katakana_english.json").write_text(
        json.dumps(katakana, ensure_ascii=False, indent=0, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"  {len(katakana)} katakana entries")

    print("building hiragana word list ...")
    hiragana = build_hiragana_words()
    (DATA / "hiragana_words.json").write_text(
        json.dumps(hiragana, ensure_ascii=False, indent=0, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"  {len(hiragana)} hiragana words")

    print("building kokuji list ...")
    kokuji, readings = build_kokuji()
    (DATA / "kokuji.json").write_text(
        json.dumps({"kokuji": sorted(kokuji), "readings": {k: readings[k] for k in sorted(kokuji) if k in readings}},
                   ensure_ascii=False, indent=0, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"  {len(kokuji)} kokuji / force-romaji entries")

    variants = dict(MANUAL_VARIANTS)
    (DATA / "variant_map.json").write_text(
        json.dumps(variants, ensure_ascii=False, indent=0, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"  {len(variants)} variant mappings")


if __name__ == "__main__":
    main()
