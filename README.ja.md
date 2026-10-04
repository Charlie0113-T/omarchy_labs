<div align="center">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/omarchy-logo-dark.svg">
  <img src="assets/omarchy-logo.svg" alt="Omarchy" width="360">
</picture>

# Omarchy Lab

**Linux / Omarchy 向けの 3 モード性能テスト：ハードウェア、AI Agent によるプログラミング、日常のマルチタスク**

Omarchy のバー用プラグイン、または単一の `.pyz` ファイル · Python 標準ライブラリのみ · 一般ユーザーで実行

![version](https://img.shields.io/badge/version-2.2-2ea44f)
![python](https://img.shields.io/badge/python-3.9%2B-3776AB?logo=python&logoColor=white)
![platform](https://img.shields.io/badge/platform-Linux%20%2F%20Omarchy-1793D1?logo=archlinux&logoColor=white)
![license](https://img.shields.io/badge/license-Apache--2.0-blue)

[English](README.md) · [简体中文](README.zh-CN.md) · [繁體中文](README.zh-TW.md) · **日本語**

</div>

---

## 3 つのモード

| モード | テスト内容 | 主な結果 |
| --- | --- | --- |
| 🧪 **典型テスト** `typical` | CPU、メモリ、ディスク、小ファイルの同期書き込み、持続負荷 | スループット、レイテンシ、温度 |
| 🤖 **Agent プログラミング** `agent` | 固定プロジェクトでのバグ修正、機能追加、テスト追加。デフォルトは Pi を使用 | 独立した受け入れ判定の合格率、総所要時間、ツール時間、モデルイベント |
| 🖥️ **日常テスト** `daily` | プログラミングのみ → 8 ページ＋プログラミング → ページ＋プログラミング＋更新負荷のシミュレーション | プログラミングの低速化倍率、ページ応答性の指標、CPU／メモリ／ディスク待ち |

## クイックスタート

### 1. ダウンロード

```sh
curl -L -o ~/Downloads/omarchy-lab.pyz \
  https://github.com/Charlie0113-T/omarchy_labs/releases/latest/download/omarchy-lab.pyz
```

`.pyz` は展開せずにそのまま実行できます。標準の ZIP でもあるので、`unzip -l omarchy-lab.pyz` で全ソースを確認できます。

### 2. 必要なモードを 1 行選んで実行

```sh
python3 ~/Downloads/omarchy-lab.pyz typical       # 典型テスト
python3 ~/Downloads/omarchy-lab.pyz agent --live  # Agent プログラミング（モデルを呼び出します）
python3 ~/Downloads/omarchy-lab.pyz daily         # 日常テスト
```

すべてのオプションは `python3 ~/Downloads/omarchy-lab.pyz --help` で確認できます。

## 🧩 Omarchy プラグイン

Omarchy（Quattro）では、Omarchy Lab をバーに置くこともできます。フラスコのアイコンをクリックすると、テストの開始、最新のレポートや結果フォルダーを開く、最新の結果の共有、実行中のテストの停止ができます。

<p align="center"><img src="preview.png" alt="Omarchy のバーに表示した Omarchy Lab のパネル" width="420"></p>

### インストール

```sh
omarchy plugin add https://github.com/Charlie0113-T/omarchy_labs
omarchy plugin enable io.github.charlie0113-t.omarchy-lab
```

**Setup › Plugins › Add** からも追加できます。プラグインは無効の状態でインストールされるので、先にコードを確認できます。`enable` でアイコンがバーの右側に追加されます。

### 使い方

- テストは選んだときにだけ、表示されたターミナルウィンドウで始まります。そのウィンドウを閉じるか「実行中のテストを停止」を選ぶと、きれいに停止します。テスト用ブラウザが閉じ、一時ファイルが削除され、途中までのレポートが保存されます。
- 「Agent＋自分のモデル」は、モデルを呼び出す前に Enter での確認を求めます。
- パネルはシステムの言語に従い、テスト自体はターミナルで言語を尋ねます。

### 更新と削除

```sh
omarchy plugin update io.github.charlie0113-t.omarchy-lab
omarchy plugin remove io.github.charlie0113-t.omarchy-lab
```

削除すると、プラグインを無効にしてからフォルダー `~/.config/omarchy/plugins/io.github.charlie0113-t.omarchy-lab` を削除します。`~/omarchy-lab/` の結果は残るので、不要になったら自分で削除してください。

### プラグインが変更するもの

- `~/.config/omarchy/plugins/io.github.charlie0113-t.omarchy-lab/` にインストールされます。
- 有効にすると、Omarchy 標準の `plugin enable` によって `~/.config/omarchy/shell.json` のバーのレイアウトに 1 項目が追加されます。無効化または削除すると取り除かれます。
- テスト結果は `~/omarchy-lab/` に保存され、実行中はホームディレクトリの一時フォルダーを使い、終了後に削除します。インストール時、有効化時、ログイン時に何かが実行されることはなく、プラグイン自体が `sudo` を使うこともありません。

### 依存関係

| 用途 | 必要なもの |
| --- | --- |
| すべて | Quattro シェルを備えた Omarchy、Python 3.9 以降（Omarchy に同梱） |
| 典型テスト | `fio`、`sysbench` |
| 日常テスト | Chromium または Chrome |
| Agent＋自分のモデル | 設定済みの [Pi](https://github.com/earendil-works/pi) |
| 共有ボタン | `wl-copy`、`xdg-open`、`notify-send`（Omarchy に同梱） |

## 前提条件

- Python 3.9 以降
- 典型テスト：`fio` と `sysbench`（Omarchy では `sudo pacman -S --needed fio sysbench`）
- 実 Agent：設定済みの [Pi](https://github.com/earendil-works/pi)
- 日常モード：デスクトップセッションと Chromium／Chrome

> [!IMPORTANT]
> 一般ユーザーで実行してください。**コマンド全体に `sudo` を付けないでください。**

## 🌐 言語

プロンプト、`--help`、エラー、レポートは English、简体中文、繁體中文、日本語に対応しています。

- ターミナルで `--lang` を付けずに実行すると、開始時に一度だけ言語を尋ねます。Enter でシステムの言語のまま進みます。
- `--lang en`、`zh-CN`、`zh-TW`、`ja` で言語を指定すると、質問は表示されません。`--lang auto` はシステムのロケールに従います。
- 環境変数 `OMARCHY_LAB_LANG=ja` を設定すると、毎回その言語で実行します。

```sh
python3 ~/Downloads/omarchy-lab.pyz daily --lang ja
```

テストの負荷はどの言語でも同じです。Agent へのタスク指示とブラウザのテストページ本文は言語によって変わらず、JSON のキーとステータスコードは英語のままなので、異なる言語で実行した結果もそのまま比較できます。

## 📮 結果を共有する

テストが終わるたびに、レポートディレクトリに `issue.md` が保存されます。このプロジェクト共通の形式（概要、デバイスとストレージ、結果、注意事項、フィードバック）に整えた GitHub Issue の本文で、投稿手順は選んだ言語で表示されます。

- 全員の結果を同じ形で比べられるよう、レポートは英語が正本です。他の言語で実行した場合は、同じレポートのその言語版が折りたたみ式で続きます。
- 自動でアップロードされることはありません。投稿前にファイルを確認してください。ハードウェア、カーネル、マウントの情報が含まれ、ホームディレクトリは `~` と表示されます。
- [テストレポート用の Issue テンプレート](https://github.com/Charlie0113-T/omarchy_labs/issues/new?template=test-report.md)から投稿するか、`gh issue create -R Charlie0113-T/omarchy_labs --title "…" --body-file issue.md` を実行してください。

## 🤖 Agent モード

Agent モードでは、まず固定のローカルツールチェーンのリプレイを実行し、その後に実際のタスクを実行します。

- 失敗やタイムアウトが「速い結果」として扱われることはありません。受け入れ判定は Agent の完了報告に依存しません。
- 総所要時間にはモデルとネットワークの待ち時間が含まれるため、純粋なハードウェア性能ではありません。
- `--live` を付けない場合はローカルリプレイのみで、モデルは呼び出しません。

> [!WARNING]
> デフォルトでは実タスクを 1 ラウンド、最大 10 分実行し、**モデルの利用枠を消費します**。

正式な比較では、モデルを固定して 3 ラウンド実行してください：

```sh
python3 ~/Downloads/omarchy-lab.pyz agent --live --model 'モデルの完全な ID' --rounds 3
```

## 🖥️ 日常モード

日常モードのプログラミングは固定リプレイを使い、モデルは呼び出しません。更新負荷はデフォルトで、展開とディスク同期の繰り返しによるシミュレーションです。

**実際のシステム更新＋ブラウザ＋プログラミング**を観測する場合：

```sh
python3 ~/Downloads/omarchy-lab.pyz daily --observe-update --seconds 600
```

案内が表示されたら、別のターミナルで Omarchy 標準の手順に従って更新を開始してください（[Omarchy Manual](https://omarchy.org/manual/updates/) を参照）。スクリプトは観測するだけで、更新は実行しません。

> [!TIP]
> 日常テストの間はテストダッシュボードを表示したままにし、最小化しないでください。

## 📊 結果

結果は終了時に表示され、`~/omarchy-lab/<タイムスタンプ>/` に保存されます：

```text
~/omarchy-lab/<タイムスタンプ>/
├── report.txt     # 読みやすいレポート
├── report.en.txt  # 英語版（他の言語で実行した場合）
├── issue.md       # そのまま投稿できる GitHub Issue
├── results.json   # 構造化された結果
└── samples.csv    # 毎秒のサンプル
```

| 終了コード | 意味 |
| :---: | --- |
| `0` | 実行が完了し、すべてのタスクが合格 |
| `1` | 実行が不完全、またはタスクが失敗 |
| `2` | 引数の誤り、または前提条件の不足 |

## 🛠️ ソースからビルド

ソースは [`src/`](src/) にあり、Omarchy プラグインはこれを直接実行します。配布用の `dist/omarchy-lab.pyz` をビルドしてテストを実行するには：

```sh
python3 scripts/build.py
python3 -m unittest discover -s tests
```

画面に表示する文言は [`src/i18n.py`](src/i18n.py) にまとめてあり、各メッセージの 4 言語が並んでいます。テストでは、すべてのメッセージが全言語にそろっていて、プレースホルダーが一致していることを確認します。

## ライセンス

[Apache License 2.0](LICENSE) で公開しています。

Omarchy のロゴは [omacom/omarchy](https://github.com/omacom/omarchy)（MIT ライセンス）のものです。本プロジェクトはコミュニティ製のツールで、Omarchy 公式とは関係ありません。
