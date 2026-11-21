"""Generate data/shinjitai_map.json.

The source table is the Japanese shinjitai/kyūjitai table from
https://github.com/dahlia/shinjitai-table (based on the Agency for Cultural
Affairs' Jōyō Kanji Table).  Each kyūjitai form is converted to Simplified
Chinese with zhconv; a mapping is kept only when the result is in GB2312.
"""

from __future__ import annotations

import json
import urllib.request
from pathlib import Path

import zhconv

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "shinjitai_map.json"
URL = "https://raw.githubusercontent.com/dahlia/shinjitai-table/master/shinjitai.json"

MANUAL = {
    "桜": "樱", "変": "变", "楽": "乐", "図": "图", "売": "卖",
    "読": "读", "駅": "驿", "県": "县", "歯": "齿", "児": "儿",
    "薬": "药", "覚": "觉", "悪": "恶", "圧": "压", "広": "广",
    "転": "转", "軽": "轻", "髪": "发", "顔": "颜", "浜": "滨",
    "芸": "艺", "竜": "龙", "滝": "泷", "鉄": "铁", "関": "关",
    "闘": "斗", "収": "收", "処": "处", "経": "经", "絵": "绘",
    "続": "续", "総": "总",
}


def in_gb2312(ch: str) -> bool:
    try:
        ch.encode("gb2312")
        return True
    except UnicodeEncodeError:
        return False


def main() -> None:
    with urllib.request.urlopen(URL) as response:
        table = json.load(response)

    mapping: dict[str, str] = {}
    for shinjitai, kyujitai in table.items():
        if len(shinjitai) != 1 or in_gb2312(shinjitai) or not kyujitai:
            continue
        for old in kyujitai:
            simplified = zhconv.convert(old, "zh-cn")
            if len(simplified) == 1 and in_gb2312(simplified):
                mapping[shinjitai] = simplified
                break

    for shinjitai, simplified in MANUAL.items():
        if in_gb2312(simplified):
            mapping.setdefault(shinjitai, simplified)

    OUT.write_text(
        json.dumps(mapping, ensure_ascii=False, indent=0, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {len(mapping)} mappings to {OUT}")


if __name__ == "__main__":
    main()
