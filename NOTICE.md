# Data notice

The files below are derived from dictionaries published by the
Electronic Dictionary Research and Development Group (EDRDG):

- `data/katakana_english.json` — derived from JMdict
- `data/hiragana_words.json` — derived from JMdict
- `data/kokuji.json` — derived from KANJIDIC2

JMdict and KANJIDIC2 are the property of the EDRDG and are made available
under the Creative Commons Attribution-ShareAlike 4.0 International License
(CC BY-SA 4.0).

- https://www.edrdg.org/jmdict/j_jmdict.html
- https://www.edrdg.org/wiki/index.php/KANJIDIC_Project
- https://creativecommons.org/licenses/by-sa/4.0/

`data/shinjitai_map.json` is generated from the shinjitai/kyūjitai table at
https://github.com/dahlia/shinjitai-table, whose source is the Japanese
Agency for Cultural Affairs' Jōyō Kanji Table.  The kyūjitai forms are
converted to Simplified Chinese with zhconv and kept only when the result is
in GB2312.

The remaining files (`data/variant_map.json`, `data/name_overrides.json`)
are small curated lists shipped with this program.

The program code itself is released under the MIT License; see `LICENSE`.
