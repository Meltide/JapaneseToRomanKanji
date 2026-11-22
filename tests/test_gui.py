from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from gui import build_preview_rows, parse_extensions
from rename_audio import Converter


class GuiLogicTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.converter = Converter()

    def test_parse_extensions(self) -> None:
        self.assertEqual(
            parse_extensions("mp3, .flac, WAV"),
            {".mp3", ".flac", ".wav"},
        )

    def test_preview_rows_and_collision(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as tmp:
            folder = Path(tmp)
            (folder / "マインドブランド.mp3").write_bytes(b"")
            (folder / "Mind Brand.mp3").write_bytes(b"")
            (folder / "plain.mp3").write_bytes(b"")

            rows = build_preview_rows(folder, False, {".mp3"}, self.converter)
            by_name = {row.source.name: row for row in rows}

            self.assertEqual(len(rows), 3)
            self.assertEqual(by_name["plain.mp3"].action, "skip")
            self.assertEqual(
                by_name["マインドブランド.mp3"].target.name,
                "Mind Brand (1).mp3",
            )
            self.assertEqual(by_name["マインドブランド.mp3"].tag, "collision")

    def test_preview_keep_original(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as tmp:
            folder = Path(tmp)
            (folder / "夜桜街道 - 沙紗飛鳥.mp3").write_bytes(b"")
            rows = build_preview_rows(
                folder, False, {".mp3"}, self.converter, keep_original=True
            )
            self.assertEqual(
                rows[0].target.name,
                "夜桜街道 - 沙紗飛鳥（夜樱街道 - 沙纱飞鸟）.mp3",
            )


if __name__ == "__main__":
    unittest.main()
