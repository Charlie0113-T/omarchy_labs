# Omarchy Lab

面向 Linux / Omarchy 的三模式性能测试，单文件 `omarchy-lab.pyz`，只依赖 Python 标准库，普通用户运行。

| 模式 | 测试内容 | 主要结果 |
| --- | --- | --- |
| 典型测试 `typical` | CPU、内存、磁盘、小文件同步写入、持续负载 | 吞吐量、延迟、温度 |
| Agent 编程 `agent` | 固定工程中的修 bug、加功能、补测试；默认使用 Pi | 独立验收通过率、总耗时、工具耗时、模型事件 |
| 日常测试 `daily` | 单独编程 → 8 个网页＋编程 → 网页＋编程＋模拟更新负载 | 编程变慢倍数、网页响应指标、CPU／内存／磁盘等待 |

## 下载

```sh
curl -L -o ~/Downloads/omarchy-lab.pyz \
  https://github.com/Charlie0113-T/omarchy_labs/raw/v2.0/omarchy-lab.pyz
```

`.pyz` 可直接运行，不必解压；它也是标准 ZIP，可以用 `unzip -l omarchy-lab.pyz` 查看全部源码。

## 运行

保存到 Downloads 后，按需要选一行运行：

```sh
python3 ~/Downloads/omarchy-lab.pyz typical
python3 ~/Downloads/omarchy-lab.pyz agent --live
python3 ~/Downloads/omarchy-lab.pyz daily
```

前置条件：

- 典型测试需已有 `fio`、`sysbench`（Omarchy 上可用 `sudo pacman -S --needed fio sysbench` 安装）。
- 真实 Agent 需要配置好的 [Pi](https://github.com/earendil-works/pi)。
- 日常模式需要桌面 Chromium／Chrome。
- 用普通用户运行，**不要给整条命令加 sudo**。

完整参数见 `python3 ~/Downloads/omarchy-lab.pyz --help`。

## Agent 模式

Agent 模式会先跑固定的本机工具链回放，再执行真实任务。

- 失败或超时不会被算成“速度快”，验收也不依赖 Agent 自称完成。
- 总耗时包含模型和网络等待，不能直接当成硬件成绩。
- 默认真实任务一轮、最多十分钟，会使用你的模型额度。
- 正式对照建议固定模型并加 `--rounds 3`：

```sh
python3 ~/Downloads/omarchy-lab.pyz agent --live --model '你的完整模型ID' --rounds 3
```

不加 `--live` 时只做本机固定回放，不调用模型。

## 日常模式

日常模式中的编程使用固定回放，不调用模型。更新负载默认模拟解压和磁盘同步；若要观察真实系统更新＋浏览器＋编程：

```sh
python3 ~/Downloads/omarchy-lab.pyz daily --observe-update --seconds 600
```

看到提示后，在另一终端按 Omarchy 自带流程启动更新（参见 [Omarchy Manual](https://omarchy.org/manual/updates/)）。脚本负责观察，不代执行更新。

日常测试期间保持测试仪表盘可见，不要最小化。

## 结果

结果自动打印，并保存在 `~/omarchy-lab/<时间戳>/`，包括 `report.txt`、JSON 和逐秒采样。

退出码：`0` 表示执行完整且任务通过，`1` 表示不完整或有任务失败，`2` 表示参数或前置条件错误。

## 许可证

[Apache License 2.0](LICENSE)
