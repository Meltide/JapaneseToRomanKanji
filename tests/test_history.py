from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from rename_audio import (
    compose_output_name,
    make_history_record,
    restore_history,
)


class HistoryTests(unittest.TestCase):
    def test_compose_keep_original(self) -> None:
        self.assertEqual(
            compose_output_name(
                "魔理沙は大変なものを盗んでいきました.mp3",
                "魔理沙Wa大变Na Mono Wo盗N De Iki Mashita.mp3",
                True,
            ),
            "魔理沙は大変なものを盗んでいきました"
            "（魔理沙Wa大变Na Mono Wo盗N De Iki Mashita）.mp3",
        )
        self.assertEqual(
            compose_output_name("夜桜街道.mp3", "夜樱街道.mp3", False),
            "夜樱街道.mp3",
        )
        self.assertEqual(
            compose_output_name("夜桜街道.mp3", "夜桜街道.mp3", True),
            "夜桜街道.mp3",
        )

    def test_restore_history(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as tmp:
            folder = Path(tmp)
            original = folder / "夜桜街道.mp3"
            original.write_bytes(b"")
            new = folder / "夜樱街道.mp3"
            original.rename(new)

            log = folder / "rename_history.jsonl"
            record = make_history_record(original, new, keep_original=False)
            log.write_text(
                json.dumps(record, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )

            preview = restore_history(log, apply=False)
            self.assertEqual(preview[0], 1)
            self.assertTrue(new.exists())

            restored = restore_history(log, apply=True)
            self.assertEqual(restored[0], 1)
            self.assertTrue(original.exists())
            self.assertFalse(new.exists())


if __name__ == "__main__":
    unittest.main()
