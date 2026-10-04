# Omarchy Lab 2.2

面向 Linux / Omarchy 的三模式测试。Python 标准库实现，普通用户运行。
下载 omarchy-lab.pyz 后可直接运行，不必解压。它也是标准 ZIP，可解压查看全部源码。

## 一行运行

```sh
python3 ~/Downloads/omarchy-lab.pyz typical
python3 ~/Downloads/omarchy-lab.pyz agent --live
python3 ~/Downloads/omarchy-lab.pyz daily
```

- typical：沿用 CPU、内存、磁盘、小文件 fsync、数据校验与持续负载测试。需要 fio（Flexible I/O Tester）和 sysbench 已安装。
- agent --live：先做三轮固定本机编程回放，再运行一轮真实 Pi 编程任务；默认每轮最多 600 秒。
- daily：编程单独运行 → 8 个本地浏览器标签页＋编程 → 多标签页＋编程＋模拟更新磁盘负载。每阶段约 60 秒，另外有基线与初始化时间。

不加 --live 的 agent 模式只做固定本机回放，不调用模型。
界面语言：--lang en|zh-CN|zh-TW|ja|auto，或环境变量 OMARCHY_LAB_LANG；都不指定时，在终端开始前询问。只有显示文字随语言变化，测试负载完全相同。
真实 Agent 使用已配置的 Pi 账号与模型，会消耗额度或产生费用；临时 cwd 不是权限沙箱。
daily 需要当前桌面会话及 Chromium/Chrome。保持新窗口的测试仪表盘标签页可见，不要最小化。
脚本不会自动安装依赖、运行系统更新、删除原有工程或向原始磁盘设备写入。

如需安装典型测试的两个工具：
```sh
sudo pacman -S --needed fio sysbench
```
不要 sudo 运行测试脚本。依赖安装报错时，先按 Omarchy 官方更新流程处理，不要仅刷新包数据库来强行安装。

## 严谨比较方法

1. 插电、固定显示器刷新率/分辨率、功耗设置、同一文件系统与工作目录；关掉无关任务，让机器恢复相近温度。
2. 固定脚本版本、Pi 版本、provider、完整模型 ID、thinking 设置及扩展。推荐真实 Agent 三轮：
   `python3 ~/Downloads/omarchy-lab.pyz agent --live --model '你的完整模型ID' --rounds 3`
   如指定 --provider 必须同时指定 --model。thinking 可用 Pi 支持的模型后缀，或自定义命令显式设置。
3. 比较两套配置时交替顺序，重复完整模式至少三次；比较中位数、每轮结果与验收率，不只比较最快一次。
4. CPU/硬盘、本机工具链回放、真实 Agent 端到端速度分别解释。模型服务、网络、提示缓存和重试会影响真实 Agent 成绩。
5. 不跨 quick/正式模式比较。原 Fusion Drive 上的 macOS 与纯 HDD 上的 Linux 同时改变了系统和存储，不能归因于某一个因素。

## Agent 测什么

每轮重建同一 Python 小工程：162 个文件、30,000 行固定输入数据，任务包含解析 bug 修复、聚合/筛选/分位数功能、CLI 和测试。
由框架外部保留的验收逻辑检查结果；Agent 自己输出“测试通过”不能决定最终通过。
固定回放包括读文件/搜索、应用相同补丁、Python 字节码编译、单元测试和 CLI 数据处理。
这不是 C/Rust 编译、大型 JS 构建或涵盖所有软件任务的能力测评；单一小任务只能作为可复现基准。
新建文件可能仍在页缓存中；不清空系统缓存，不声称冷启动磁盘成绩。工程生成时间单独于回放任务耗时。

真实 Pi JSON 事件记录总耗时、首模型增量/首文字、工具完成区间、工具错误、重试及最终消息 usage。
首增量是客户端收到事件的时间，不是精确服务端首 token 时间。
工具时长不等于 CPU 时间；剩余时间没有被直接测成“云端推理时间”。
usage 只统计最终 assistant 消息，避免累计流事件重复计数；可能不含某些重试/压缩，费用字段不等于账单。
没有事件或数据不足显示未观测，不补零。超时、进程失败、验收失败都不会计为成功任务。
自定义适配器：`--agent-command '你的非交互命令及参数'`，prompt 作为最后一个参数追加，不通过 shell。
非 Pi 事件格式仍可验收代码、计总时间，但 Pi 专属事件指标会缺失。
原始日志可能含模型回复、路径或扩展输出；分享报告前自行检查。

## 日常模式和真实更新

daily 使用固定本地网页，以避免公网波动；保留浏览器默认后台标签节流。
测量可见页面 rAF 回调间隔和定时器延迟，而不是系统 FPS、鼠标输入延迟或 INP。
后台页面不冒充前台样本。阶段边界有意丢弃跨阶段批次，避免混入错误阶段；缺失/不够样本会被标记。
正式模式要求各阶段前台样本覆盖至少 60% 的阶段时长；quick 为 25%。这是采样完整性要求，不是流畅度合格线。
日常编程任务是与 Agent 模式相同的固定本机工具链回放，不消耗模型额度。
“模拟更新”仅在临时目录反复解压固定压缩包并 fsync，不涉及包管理器、升级或重启。

要观察真实更新：
```sh
python3 ~/Downloads/omarchy-lab.pyz daily --observe-update --seconds 600
```
看到提示后，在另一终端按 Omarchy 官方流程启动更新。脚本观察浏览器＋本机编程负载，记录前后包版本。
更新可能超过观察窗口；这里不把窗口时长当作完整更新用时。按 Ctrl+C 可结束观察，不会终止另一个终端的更新。
真实更新改变软件版本，不能原样反复执行，因此单独作为观察记录，不能混入可重复基准。

## 输出和中止

结束后终端打印报告；默认 `~/omarchy-lab/<时间戳>/` 保存 report.txt、results.json、samples.csv 和各模式原始记录。
临时测试工程位于 --work-dir（默认家目录）的独立新目录，退出时清理；真实 Agent 修改后的源码留在对应报告中。
用 --work-dir 指向 HDD 或 SSD 的普通目录，才能比较对应盘上的本机工作。
典型模式至少需要 8 GiB 可用空间，Agent/日常模式至少 1 GiB。输出日志另占空间。
Ctrl+C 保存部分报告并中止本次测试进程。温度达到默认 90°C 时停止，传感器不可用会明确标记。
模拟更新关闭后由框架回收；脚本从不杀用户另行启动的真实更新。
退出码 0 表示该次执行完整且任务通过，1 表示不完整或有任务失败，2 表示参数/前置条件错误。
性能快慢没有通用合格线；不要把“通过验收”理解为硬件一定健康或所有用途都流畅。

## 验证范围

已用受控工程验证验收、固定回放、Pi 事件解析、失败/中止记录、子进程回收和打包入口。
验证采用本机假 Agent 事件，不调用真实模型。当前构建环境没有可用的图形桌面 Chromium，真实浏览器端到端与用户 Pi/provider 仍需首次运行确认。

协议参考：
- https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/cli.md
- https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/json.md
- https://omarchy.org/manual/updates/
