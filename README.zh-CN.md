<div align="center">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/omarchy-logo-dark.svg">
  <img src="assets/omarchy-logo.svg" alt="Omarchy" width="360">
</picture>

# Omarchy Lab

**面向 Linux / Omarchy 的三模式性能测试：硬件、AI Agent 编程、日常多任务**

单文件 `.pyz` · 仅依赖 Python 标准库 · 普通用户运行

![version](https://img.shields.io/badge/version-2.1-2ea44f)
![python](https://img.shields.io/badge/python-3.9%2B-3776AB?logo=python&logoColor=white)
![platform](https://img.shields.io/badge/platform-Linux%20%2F%20Omarchy-1793D1?logo=archlinux&logoColor=white)
![license](https://img.shields.io/badge/license-Apache--2.0-blue)

[English](README.md) · **简体中文** · [繁體中文](README.zh-TW.md) · [日本語](README.ja.md)

</div>

---

## 三种模式

| 模式 | 测试内容 | 主要结果 |
| --- | --- | --- |
| 🧪 **典型测试** `typical` | CPU、内存、磁盘、小文件同步写入、持续负载 | 吞吐量、延迟、温度 |
| 🤖 **Agent 编程** `agent` | 固定工程中的修 bug、加功能、补测试；默认使用 Pi | 独立验收通过率、总耗时、工具耗时、模型事件 |
| 🖥️ **日常测试** `daily` | 单独编程 → 8 个网页＋编程 → 网页＋编程＋模拟更新负载 | 编程变慢倍数、网页响应指标、CPU／内存／磁盘等待 |

## 快速开始

### 1. 下载

```sh
curl -L -o ~/Downloads/omarchy-lab.pyz \
  https://github.com/Charlie0113-T/omarchy_labs/raw/v2.1/omarchy-lab.pyz
```

`.pyz` 可直接运行，不必解压；它也是标准 ZIP，可以用 `unzip -l omarchy-lab.pyz` 查看全部源码。

### 2. 按需要选一行运行

```sh
python3 ~/Downloads/omarchy-lab.pyz typical       # 典型测试
python3 ~/Downloads/omarchy-lab.pyz agent --live  # Agent 编程（会调用模型）
python3 ~/Downloads/omarchy-lab.pyz daily         # 日常测试
```

完整参数见 `python3 ~/Downloads/omarchy-lab.pyz --help`。

## 前置条件

- Python 3.9 或更新版本
- 典型测试：已安装 `fio`、`sysbench`（Omarchy 上：`sudo pacman -S --needed fio sysbench`）
- 真实 Agent：已配置好的 [Pi](https://github.com/earendil-works/pi)
- 日常模式：桌面 Chromium／Chrome

> [!IMPORTANT]
> 用普通用户运行，**不要给整条命令加 `sudo`**。

## 🌐 语言

提示、`--help`、错误信息和报告支持 English、简体中文、繁體中文、日本語。

- 在终端里运行且没有加 `--lang` 时，开始前会问一次；直接按回车即沿用系统语言。
- `--lang en`、`zh-CN`、`zh-TW` 或 `ja` 直接指定语言，不再询问；`--lang auto` 跟随系统区域设置。
- 设置环境变量 `OMARCHY_LAB_LANG=zh-CN`，之后每次运行都使用该语言。

```sh
python3 ~/Downloads/omarchy-lab.pyz daily --lang zh-CN
```

各语言的测试负载完全相同：Agent 的任务提示和浏览器测试页正文不随语言变化，JSON 键名和状态码保持英文，因此不同语言跑出的结果可以直接比较。

## 🤖 Agent 模式

Agent 模式会先跑固定的本机工具链回放，再执行真实任务。

- 失败或超时不会被算成“速度快”，验收也不依赖 Agent 自称完成。
- 总耗时包含模型和网络等待，不能直接当成硬件成绩。
- 不加 `--live` 时只做本机固定回放，不调用模型。

> [!WARNING]
> 默认真实任务一轮、最多十分钟，**会使用你的模型额度**。

正式对照建议固定模型并跑三轮：

```sh
python3 ~/Downloads/omarchy-lab.pyz agent --live --model '你的完整模型ID' --rounds 3
```

## 🖥️ 日常模式

日常模式中的编程使用固定回放，不调用模型。更新负载默认模拟解压和磁盘同步。

若要观察**真实系统更新＋浏览器＋编程**：

```sh
python3 ~/Downloads/omarchy-lab.pyz daily --observe-update --seconds 600
```

看到提示后，在另一终端按 Omarchy 自带流程启动更新（参见 [Omarchy Manual](https://omarchy.org/manual/updates/)）。脚本负责观察，不代执行更新。

> [!TIP]
> 日常测试期间保持测试仪表盘可见，不要最小化。

## 📊 结果

结果自动打印，并保存在 `~/omarchy-lab/<时间戳>/`：

```text
~/omarchy-lab/<时间戳>/
├── report.txt     # 可读报告
├── results.json   # 结构化结果
└── samples.csv    # 逐秒采样
```

| 退出码 | 含义 |
| :---: | --- |
| `0` | 执行完整且任务通过 |
| `1` | 不完整或有任务失败 |
| `2` | 参数或前置条件错误 |

## 🛠️ 从源码构建

源码在 [`src/`](src/)。重新打包 `omarchy-lab.pyz` 并运行测试：

```sh
python3 scripts/build.py
python3 -m unittest discover -s tests
```

所有界面文字集中在 [`src/i18n.py`](src/i18n.py)，每条消息的四种语言并排存放；测试会检查每条消息在每种语言里都存在，且占位符一致。

## 许可证

本项目以 [Apache License 2.0](LICENSE) 发布。

Omarchy 标志来自 [omacom/omarchy](https://github.com/omacom/omarchy)（MIT 许可）。本项目是社区工具，与 Omarchy 官方无关。
