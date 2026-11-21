from __future__ import annotations

import unittest

from rename_audio import Converter, safe_filename


class ExampleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.converter = Converter()

    def check(self, source: str, expected: str) -> None:
        self.assertEqual(self.converter.convert_filename(source), expected)

    def test_katakana_loanwords(self) -> None:
        self.check("マインドブランド.mp3", "Mind Brand.mp3")

    def test_mixed_kanji_katakana_hiragana(self) -> None:
        self.check(
            "インドア系ならトラックメイカー.mp3",
            "Indoor系Nara Track Maker.mp3",
        )

    def test_particles_and_hiragana_words(self) -> None:
        self.check(
            "チルノのパーフェクトさんすう教室 - miko.flac",
            "Cirno No Perfect Sansuu教室 - miko.flac",
        )

    def test_simplified_kanji_and_kokuji(self) -> None:
        self.check(
            "緋色月下、狂咲ノ絶 (1st Anniversary Remix) - nayuta.wav",
            "绯色月下、狂Saki No绝 (1st Anniversary Remix) - nayuta.wav",
        )

    def test_long_sentence(self) -> None:
        self.check(
            "魔理沙は大変なものを盗んでいきました - ARM/miko.aac",
            "魔理沙Wa大変Na Mono Wo盗N De Iki Mashita - ARM/miko.aac",
        )


class NameVariantTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.converter = Converter()

    def test_cirno_variants(self) -> None:
        self.assertEqual(self.converter.convert_stem("チルノ"), "Cirno")
        self.assertEqual(self.converter.convert_stem("チル"), "Cirno")
        self.assertEqual(self.converter.convert_stem("ちるの"), "Cirno")
        self.assertEqual(self.converter.convert_stem("チルノちゃん"), "Cirno Chan")
        self.assertEqual(self.converter.convert_stem("ちるのちゃん"), "Cirno Chan")

    def test_remilia_and_flandre_variants(self) -> None:
        self.assertEqual(self.converter.convert_stem("レミィ"), "Remilia")
        self.assertEqual(self.converter.convert_stem("れみりあ"), "Remilia")
        self.assertEqual(self.converter.convert_stem("フラン"), "Flandre")
        self.assertEqual(self.converter.convert_stem("ふらん"), "Flandre")
        self.assertEqual(
            self.converter.convert_stem("レミリア・スカーレット"),
            "Remilia Scarlet",
        )
        self.assertEqual(
            self.converter.convert_stem("フランドール・スカーレット"),
            "Flandre Scarlet",
        )

    def test_other_name_variants(self) -> None:
        self.assertEqual(self.converter.convert_stem("パチュ"), "Patchouli")
        self.assertEqual(self.converter.convert_stem("ミスティ"), "Mystia")
        self.assertEqual(self.converter.convert_stem("メディ"), "Medicine")
        self.assertEqual(self.converter.convert_stem("ナズ"), "Nazrin")
        self.assertEqual(self.converter.convert_stem("うどんげ"), "Reisen")
        self.assertEqual(self.converter.convert_stem("もこ"), "Mokou")

    def test_hiragana_spellings(self) -> None:
        self.assertEqual(self.converter.convert_stem("ぱちゅ"), "Patchouli")
        self.assertEqual(self.converter.convert_stem("みすてぃ"), "Mystia")
        self.assertEqual(self.converter.convert_stem("めでぃ"), "Medicine")
        self.assertEqual(self.converter.convert_stem("なず"), "Nazrin")


class NoLoanwordTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.converter = Converter(use_loanwords=False)

    def test_katakana_is_romanised_not_translated(self) -> None:
        self.assertEqual(
            self.converter.convert_filename("マインドブランド.mp3"),
            "Maindo Burando.mp3",
        )
        self.assertEqual(
            self.converter.convert_filename(
                "チルノのパーフェクトさんすう教室 - miko.flac"
            ),
            "Chiruno No Paafekuto Sansuu教室 - miko.flac",
        )

    def test_compound_katakana_keeps_word_boundaries(self) -> None:
        self.assertEqual(
            self.converter.convert_filename("インドア系ならトラックメイカー.mp3"),
            "Indoa系Nara Torakku Meikaa.mp3",
        )
        self.assertEqual(self.converter.convert_stem("ラブソング"), "Rabu Songu")
        self.assertEqual(self.converter.convert_stem("アイスコーヒー"), "Aisu Koohii")

    def test_contractions_are_not_split(self) -> None:
        self.assertEqual(self.converter.convert_stem("コンビニ"), "Konbini")
        self.assertEqual(self.converter.convert_stem("パソコン"), "Pasokon")

    def test_hiragana_names_are_romanised(self) -> None:
        self.assertEqual(self.converter.convert_stem("ちるの"), "Chiruno")
        self.assertEqual(self.converter.convert_stem("れみりあ"), "Remiria")
        self.assertEqual(self.converter.convert_stem("もこ"), "Moko")


class UnitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.converter = Converter()

    def test_kanji_variants(self) -> None:
        self.assertEqual(self.converter.convert_stem("緋色"), "绯色")
        self.assertEqual(self.converter.convert_stem("絶"), "绝")
        # 変 is already the Japanese simplified form; zhconv leaves it alone.
        self.assertEqual(self.converter.convert_stem("大変"), "大変")
        self.assertEqual(self.converter.convert_stem("髙"), "高")
        self.assertEqual(self.converter.convert_stem("﨑"), "崎")

    def test_kokuji_uses_reading(self) -> None:
        self.assertEqual(self.converter.convert_stem("咲"), "Saki")
        self.assertEqual(self.converter.convert_stem("凪"), "Nagi")
        self.assertEqual(self.converter.convert_stem("雫"), "Shizuku")

    def test_hiragana_word_segmentation(self) -> None:
        self.assertEqual(self.converter.convert_stem("さんすう"), "Sansuu")
        self.assertEqual(self.converter.convert_stem("とうきょう"), "Toukyou")
        self.assertEqual(self.converter.convert_stem("にほんご"), "Nihongo")
        self.assertEqual(self.converter.convert_stem("がっこう"), "Gakkou")

    def test_particles(self) -> None:
        self.assertEqual(self.converter.convert_stem("こんにちは"), "Konnichiwa")
        self.assertEqual(self.converter.convert_stem("では"), "Dewa")
        self.assertEqual(self.converter.convert_stem("を"), "Wo")
        self.assertEqual(self.converter.convert_stem("へ"), "E")

    def test_katakana_compounds(self) -> None:
        self.assertEqual(self.converter.convert_stem("ハッピーバースデー"), "Happy Birthday")
        self.assertEqual(self.converter.convert_stem("ラブソング"), "Love Song")
        self.assertEqual(self.converter.convert_stem("スーパーマリオ"), "Super Mario")

    def test_common_loanwords(self) -> None:
        self.assertEqual(self.converter.convert_stem("ビール"), "Beer")
        self.assertEqual(self.converter.convert_stem("タバコ"), "Tobacco")
        self.assertEqual(self.converter.convert_stem("フォルダ"), "Folder")
        self.assertEqual(self.converter.convert_stem("インターネット"), "Internet")

    def test_ascii_is_preserved(self) -> None:
        self.assertEqual(
            self.converter.convert_stem("曲名 - ARM/miko (Remix)"),
            "曲名 - ARM/miko (Remix)",
        )

    def test_extension_is_preserved(self) -> None:
        self.assertEqual(self.converter.convert_filename("マインドブランド.MP3"), "Mind Brand.MP3")

    def test_halfwidth_katakana(self) -> None:
        self.assertEqual(self.converter.convert_filename("ﾏｲﾝﾄﾞﾌﾞﾗﾝﾄﾞ.mp3"), "Mind Brand.mp3")

    def test_safe_filename(self) -> None:
        self.assertEqual(safe_filename("A/B:C"), "A_B_C")
        self.assertEqual(safe_filename("CON"), "_CON")
        self.assertEqual(safe_filename("name. "), "name")


if __name__ == "__main__":
    unittest.main()
