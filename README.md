# 日语音频文件名转换器

由于本人抽象MP3不支持显示日语，遂使用DeepSeek Harness跑了这个神秘项目 (x)

作用：把音频文件名中的日文转换为简体汉字+罗马音的组合，使MP3正常显示歌名

默认只预览，不会改动文件；加上 `--apply` 才会真正重命名

## 效果示例

| 原文件名                                                  | 转换后                                                       |
| --------------------------------------------------------- | ------------------------------------------------------------ |
| `マインドブランド.mp3`                                    | `Mind Brand.mp3`                                             |
| `インドア系ならトラックメイカー.mp3`                      | `Indoor系Nara Track Maker.mp3`                               |
| `チルノのパーフェクトさんすう教室 - miko.flac`            | `Cirno No Perfect Sansuu教室 - miko.flac`                    |
| `緋色月下、狂咲ノ絶 (1st Anniversary Remix) - nayuta.wav` | `绯色月下、狂Saki No绝 (1st Anniversary Remix) - nayuta.wav` |
| `魔理沙は大変なものを盗んでいきました - ARM/miko.aac`     | `魔理沙Wa大変Na Mono Wo盗N De Iki Mashita - ARM/miko.aac`    |

> Windows 文件名不能包含 `/`，实际文件中的斜杠会按 Windows 规则替换为 `_`；表里的斜杠仅用于展示“保留原文”的效果。

## 安装

需要 Python 3.10 或更高版本。

```powershell
python -m pip install -r requirements.txt
```

依赖：

- [janome](https://pypi.org/project/janome/)：日语分词
- [pykakasi](https://pypi.org/project/pykakasi/)：假名转罗马音
- [zhconv](https://pypi.org/project/zhconv/)：汉字简体转换

## 使用

先预览（`--dry-run` 是默认行为）：

```powershell
python rename_audio.py "D:\Music\东方"
```

确认无误后真正改名：

```powershell
python rename_audio.py "D:\Music\东方" --apply
```

递归处理子文件夹：

```powershell
python rename_audio.py "D:\Music\东方" --recursive --apply
```

### 片假名只转罗马音

默认会把片假名还原为英语/外来语原文。如果不想做这一步，加 `--no-loanwords`（别名 `--katakana-romaji`）：

```powershell
python rename_audio.py "D:\Music\东方" --no-loanwords
```

| 原文件名                                       | 默认模式                                  | `--no-loanwords`                              |
| ---------------------------------------------- | ----------------------------------------- | --------------------------------------------- |
| `マインドブランド.mp3`                         | `Mind Brand.mp3`                          | `Maindo Burando.mp3`                          |
| `インドア系ならトラックメイカー.mp3`           | `Indoor系Nara Track Maker.mp3`            | `Indoa系Nara Torakku Meikaa.mp3`              |
| `チルノのパーフェクトさんすう教室 - miko.flac` | `Cirno No Perfect Sansuu教室 - miko.flac` | `Chiruno No Paafekuto Sansuu教室 - miko.flac` |

这个模式不读取“片假名 → 英语”的译名，所以 `チルノ` 会变成 `Chiruno` 而不是 `Cirno`；片假名复合词仍会按词边界加空格，例如 `トラックメイカー` → `Torakku Meikaa`

只处理指定扩展名：

```powershell
python rename_audio.py "D:\Music" --extensions mp3,flac,wav --apply
```

使用额外的名称覆盖表：

```powershell
python rename_audio.py "D:\Music" --overrides my_names.json --apply
```

`my_names.json` 的格式：

```json
{
    "チルノ": "Cirno",
    "レミリア": "Remilia"
}
```

其他选项：

```text
--no-loanwords, --katakana-romaji   片假名只转罗马音，不还原为英语/外来语
--quiet, -q                          只输出汇总
--version                            显示版本
```

## 转换规则

1. **分词**：用 Janome 对日文部分分词；纯平假名再用内置词表做一次动态规划分词，避免把 `さんすう` 拆成 `さんす` + `う`
2. **片假名**：默认查内置的外来语词表，还原为原文，例如 `マインド` → `mind`、`ブランド` → `brand`、`トラックメイカー` → `track maker`。词表由 JMdict 的片假名/外来语条目生成；查不到时退回罗马音。加 `--no-loanwords` 可跳过这一步，全部按罗马音输出
3. **汉字**：用 zhconv 转成简体，例如 `緋` → `绯`、`絶` → `绝`。日文国字/异体字（如 `咲`）没有合适的简体对应字时，按日语读音转罗马音，例如 `咲` → `Saki`
4. **平假名**：转罗马音；助词 `は` / `へ` / `を` 分别读作 `Wa` / `E` / `Wo`
5. **大小写**：每个罗马音/英文单词首字母大写
6. **空格**：
    - 罗马音之间用空格分隔：`No Perfect Sansuu`
    - 罗马音与汉字之间不分隔：`Sansuu教室`、`魔理沙Wa`
    - 原有的 ASCII 文本、空格、括号、连字符等保持不变：` - miko`、` (1st Anniversary Remix)`

## 自定义

- `data/name_overrides.json`：片假名词语/专名的固定译法。示例里 `チルノ` → `Cirno` 就来自这里，也可以用它修正个别外来语。
  - 已收录常见东方人名及其变种：全名（`レミリア・スカーレット` → `Remilia Scarlet`）、短名（`レミィ`、`フラン`、`パチュ`、`ミスティ`、`メディ`、`ナズ`）、平假名写法（`ちるの`、`れみりあ`、`ふらん`、`ぱちゅ`、`うどんげ`）。
  - 名字后面接 `ちゃん` 等后缀时会分开输出，例如 `チルノちゃん` → `Cirno Chan`；`--no-loanwords` 模式下仍会保持名字的完整分词，但输出罗马音，例如 `ちるの` → `Chiruno`。
- `data/variant_map.json`：额外的异体字 → 简体字映射，例如 `髙` → `高`
- `data/kokuji.json`：需要转罗马音的日文国字/异体字列表及读音
- `data/katakana_english.json`：片假名 → 外来语原文词表
- `data/hiragana_words.json`：平假名分词词表

这些数据文件已经随程序提供，通常不需要改动。重新生成的方法见 `tools/build_data.py` 顶部说明；原始 JMdict / KANJIDIC2 数据不随程序分发

## 自动构建 Windows EXE

仓库已配置 GitHub Actions：[build-exe.yml](.github/workflows/build-exe.yml)。每次 `git push`（任意分支）都会在 `windows-latest` 上自动：

1. 安装 `requirements.txt` 和 PyInstaller；
2. 用 [JapaneseAudioRenamer.spec](JapaneseAudioRenamer.spec) 构建单文件 `JapaneseAudioRenamer.exe`；
3. 运行一次冒烟测试，确认 EXE 能输出 `Mind Brand`；
4. 把 EXE 作为构建产物上传，保留 30 天。

在 GitHub 仓库的 **Actions → Build Windows EXE → 对应运行 → Artifacts** 下载 `JapaneseAudioRenamer-windows-x64` 即可。这个 EXE 已内置 `data/` 和三个 Python 依赖，目标机器不需要安装 Python。

本地构建：

```powershell
python -m pip install -r requirements.txt "pyinstaller==6.22.3"
python -m PyInstaller --noconfirm --clean JapaneseAudioRenamer.spec
.\dist\JapaneseAudioRenamer.exe --help
```

## 测试

```powershell
python -m unittest discover -s tests -v
```

测试覆盖了上面五个示例，以及汉字简化、国字读音、平假名分词、助词、片假名复合词、`--no-loanwords` 模式、半角片假名和文件名安全处理

## 已知限制

- 片假名外来语的“原文”依赖词表；词表没有的专名会退回罗马音，可用 `--overrides` 补充
- 日语汉字有多音读法；没有简体对应字而需要转罗马音时，程序使用分词器给出的读音或 pykakasi 的默认读音，个别名字可能读错
- 只改文件名，不改音频标签（ID3 / Vorbis Comment 等）
- 程序以 Windows 文件名规则做安全处理：`<>:"/\|?*` 会替换为 `_`，保留名（`CON` 等）会加前缀
- 默认不递归；需要处理子文件夹时加 `--recursive`
