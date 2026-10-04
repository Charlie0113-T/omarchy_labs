<div align="center">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/omarchy-logo-dark.svg">
  <img src="assets/omarchy-logo.svg" alt="Omarchy" width="360">
</picture>

# Omarchy Lab

**適用於 Linux / Omarchy 的三模式效能測試：硬體、AI Agent 寫程式、日常多工**

Omarchy 頂部列外掛或單一 `.pyz` 檔 · 僅依賴 Python 標準函式庫 · 以一般使用者執行

![version](https://img.shields.io/badge/version-2.2-2ea44f)
![python](https://img.shields.io/badge/python-3.9%2B-3776AB?logo=python&logoColor=white)
![platform](https://img.shields.io/badge/platform-Linux%20%2F%20Omarchy-1793D1?logo=archlinux&logoColor=white)
![license](https://img.shields.io/badge/license-Apache--2.0-blue)

[English](README.md) · [简体中文](README.zh-CN.md) · **繁體中文** · [日本語](README.ja.md)

</div>

---

## 三種模式

| 模式 | 測試內容 | 主要結果 |
| --- | --- | --- |
| 🧪 **典型測試** `typical` | CPU、記憶體、磁碟、小檔案同步寫入、持續負載 | 吞吐量、延遲、溫度 |
| 🤖 **Agent 寫程式** `agent` | 在固定專案中修 bug、加功能、補測試；預設使用 Pi | 獨立驗收通過率、總耗時、工具耗時、模型事件 |
| 🖥️ **日常測試** `daily` | 單獨寫程式 → 8 個網頁＋寫程式 → 網頁＋寫程式＋模擬更新負載 | 寫程式變慢倍數、網頁回應指標、CPU／記憶體／磁碟等待 |

## 快速開始

### 1. 下載

```sh
curl -L -o ~/Downloads/omarchy-lab.pyz \
  https://github.com/Charlie0113-T/omarchy_labs/releases/latest/download/omarchy-lab.pyz
```

`.pyz` 可直接執行，不必解壓縮；它也是標準 ZIP，可以用 `unzip -l omarchy-lab.pyz` 查看全部原始碼。

### 2. 依需要選一行執行

```sh
python3 ~/Downloads/omarchy-lab.pyz typical       # 典型測試
python3 ~/Downloads/omarchy-lab.pyz agent --live  # Agent 寫程式（會呼叫模型）
python3 ~/Downloads/omarchy-lab.pyz daily         # 日常測試
```

完整參數請見 `python3 ~/Downloads/omarchy-lab.pyz --help`。

## 🧩 Omarchy 外掛

在 Omarchy（Quattro）上，Omarchy Lab 也可以放進頂部列。點擊燒瓶圖示即可啟動測試、開啟最新報告或結果資料夾、分享最新結果，或停止正在執行的測試。

<p align="center"><img src="preview.png" alt="Omarchy 頂部列中的 Omarchy Lab 面板" width="420"></p>

### 安裝

```sh
omarchy plugin add https://github.com/Charlie0113-T/omarchy_labs
omarchy plugin enable io.github.charlie0113-t.omarchy-lab
```

也可以使用 **Setup › Plugins › Add**。外掛安裝後預設為停用，方便你先閱讀程式碼；`enable` 會把圖示放到頂部列右側。

### 使用

- 每項測試都只在你選擇後啟動，並在可見的終端機視窗中執行。關閉該視窗或選擇「停止正在執行的測試」都會乾淨地停止：測試瀏覽器會關閉、臨時檔案會刪除，並儲存部分報告。
- 「Agent + 你的模型」在呼叫模型前會要求你按 Enter 確認。
- 面板跟隨系統語言；測試本身會在終端機中詢問要使用哪種語言。

### 更新與移除

```sh
omarchy plugin update io.github.charlie0113-t.omarchy-lab
omarchy plugin remove io.github.charlie0113-t.omarchy-lab
```

移除會先停用外掛，再刪除其資料夾 `~/.config/omarchy/plugins/io.github.charlie0113-t.omarchy-lab`。`~/omarchy-lab/` 中的測試結果會保留，不再需要時可自行刪除。

### 外掛會變更什麼

- 安裝到 `~/.config/omarchy/plugins/io.github.charlie0113-t.omarchy-lab/`。
- 啟用時透過 Omarchy 內建的 `plugin enable`，在 `~/.config/omarchy/shell.json` 的頂部列配置中加入一項；停用或移除時會刪除這一項。
- 測試結果儲存在 `~/omarchy-lab/`，執行時在家目錄使用臨時資料夾，結束後刪除。安裝、啟用或登入時都不會執行任何東西，外掛本身也從不使用 `sudo`。

### 相依套件

| 用途 | 需要 |
| --- | --- |
| 全部功能 | 搭載 Quattro shell 的 Omarchy、Python 3.9+（Omarchy 已內建） |
| 典型測試 | `fio`、`sysbench` |
| 日常測試 | Chromium 或 Chrome |
| Agent + 你的模型 | 已設定好的 [Pi](https://github.com/earendil-works/pi) |
| 分享按鈕 | `wl-copy`、`xdg-open`、`notify-send`（Omarchy 已內建） |

## 前置條件

- Python 3.9 或更新版本
- 典型測試：已安裝 `fio`、`sysbench`（Omarchy 上：`sudo pacman -S --needed fio sysbench`）
- 真實 Agent：已設定好的 [Pi](https://github.com/earendil-works/pi)
- 日常模式：桌面 Chromium／Chrome

> [!IMPORTANT]
> 請以一般使用者執行，**不要在整條指令前加 `sudo`**。

## 🌐 語言

提示、`--help`、錯誤訊息與報告支援 English、简体中文、繁體中文、日本語。

- 在終端機執行且未加 `--lang` 時，開始前會詢問一次；直接按 Enter 即沿用系統語言。
- `--lang en`、`zh-CN`、`zh-TW` 或 `ja` 直接指定語言，不再詢問；`--lang auto` 跟隨系統地區設定。
- 設定環境變數 `OMARCHY_LAB_LANG=zh-TW`，之後每次執行都使用該語言。

```sh
python3 ~/Downloads/omarchy-lab.pyz daily --lang zh-TW
```

各語言的測試負載完全相同：Agent 的任務提示與瀏覽器測試頁正文不隨語言改變，JSON 鍵名與狀態碼維持英文，因此不同語言跑出的結果可以直接比較。

## 📮 分享結果

每次測試結束後，工具會在報告目錄中儲存 `issue.md`：依本專案固定格式（摘要、裝置與儲存、結果、提示、回饋）排好的 GitHub Issue 內文，並以你選擇的語言印出發佈步驟。

- 報告以英文為準，方便所有人的結果統一對照；如果你用其他語言執行，後面會附上可展開的同一份報告的該語言版本。
- 不會自動上傳任何內容。發佈前請檢查檔案：其中包含硬體、核心與掛載資訊，家目錄會顯示為 `~`。
- 用[測試報告 Issue 範本](https://github.com/Charlie0113-T/omarchy_labs/issues/new?template=test-report.md)發佈，或執行 `gh issue create -R Charlie0113-T/omarchy_labs --title "…" --body-file issue.md`。

## 🤖 Agent 模式

Agent 模式會先執行固定的本機工具鏈重播，再執行真實任務。

- 失敗或逾時不會被算成「速度快」，驗收也不依賴 Agent 自稱完成。
- 總耗時包含模型與網路等待，不能直接當成硬體成績。
- 未加 `--live` 時只做本機固定重播，不呼叫模型。

> [!WARNING]
> 預設真實任務一輪、最多十分鐘，**會使用你的模型額度**。

正式對照建議固定模型並跑三輪：

```sh
python3 ~/Downloads/omarchy-lab.pyz agent --live --model '你的完整模型ID' --rounds 3
```

## 🖥️ 日常模式

日常模式中的寫程式工作使用固定重播，不呼叫模型。更新負載預設以重複解壓縮與磁碟同步模擬。

若要觀察**真實系統更新＋瀏覽器＋寫程式**：

```sh
python3 ~/Downloads/omarchy-lab.pyz daily --observe-update --seconds 600
```

看到提示後，在另一個終端機依 Omarchy 內建流程啟動更新（參見 [Omarchy Manual](https://omarchy.org/manual/updates/)）。腳本只負責觀察，不會代為執行更新。

> [!TIP]
> 日常測試期間請讓測試儀表板保持可見，不要最小化。

## 📊 結果

結果會自動印出，並儲存在 `~/omarchy-lab/<時間戳記>/`：

```text
~/omarchy-lab/<時間戳記>/
├── report.txt     # 可讀報告
├── report.en.txt  # 英文副本（以其他語言執行時產生）
├── issue.md       # 可直接發佈的 GitHub Issue
├── results.json   # 結構化結果
└── samples.csv    # 逐秒取樣
```

| 結束碼 | 含義 |
| :---: | --- |
| `0` | 執行完整且任務通過 |
| `1` | 不完整或有任務失敗 |
| `2` | 參數或前置條件錯誤 |

## 🛠️ 從原始碼建置

原始碼位於 [`src/`](src/)，Omarchy 外掛直接執行這份原始碼。打包發佈用的 `dist/omarchy-lab.pyz` 並執行測試：

```sh
python3 scripts/build.py
python3 -m unittest discover -s tests
```

所有介面文字集中在 [`src/i18n.py`](src/i18n.py)，每則訊息的四種語言並列存放；測試會檢查每則訊息在每種語言中都存在，且佔位符一致。

## 授權

本專案以 [Apache License 2.0](LICENSE) 釋出。

Omarchy 標誌取自 [omacom/omarchy](https://github.com/omacom/omarchy)（MIT 授權）。本專案為社群工具，與 Omarchy 官方無關。
