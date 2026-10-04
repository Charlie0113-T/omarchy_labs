"""Language selection and message catalog for Omarchy Lab.

English is the reference text. Every entry holds the same message in LANGUAGES
order: English, Simplified Chinese, Traditional Chinese, Japanese.
Only what people read is translated. Benchmark inputs, such as the agent prompt
and the browser page bodies, stay identical in every language so results remain
comparable. JSON keys and status codes also stay in English.
"""
import argparse
import contextlib
import os
import sys

LANGUAGES = ("en", "zh-CN", "zh-TW", "ja")
NAMES = {"en": "English", "zh-CN": "简体中文", "zh-TW": "繁體中文", "ja": "日本語"}
ENV_VAR = "OMARCHY_LAB_LANG"

_current = "en"
_configured = False


def normalize(value):
    """Map a language tag or POSIX locale (e.g. ja_JP.UTF-8) to a supported code."""
    tag = (value or "").strip().replace("_", "-").split(".")[0].split("@")[0].lower()
    if not tag or tag in ("c", "posix"):
        return None
    if tag in ("zh-tw", "zh-hk", "zh-mo") or tag.startswith("zh-hant"):
        return "zh-TW"
    if tag == "zh" or tag.startswith(("zh-cn", "zh-sg", "zh-hans")):
        return "zh-CN"
    if tag in ("ja", "jp") or tag.startswith("ja-"):
        return "ja"
    if tag == "en" or tag.startswith("en-"):
        return "en"
    return None


def from_environment(environ=None):
    """Follow gettext's precedence: LANGUAGE, LC_ALL, LC_MESSAGES, LANG."""
    environ = os.environ if environ is None else environ
    for name in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
        for part in environ.get(name, "").split(":"):
            code = normalize(part)
            if code:
                return code
    return None


def set_language(code):
    global _current
    if code not in LANGUAGES:
        raise ValueError(f"unsupported language: {code}")
    _current = code
    return code


def current():
    return _current


class Text(str):
    """A message shown in the current language that can be shown again in another one.

    Notes and errors are collected while a test runs, in the chosen language. The
    shared GitHub issue also needs them in English, so each message keeps its key.
    """

    def __new__(cls, key, values):
        self = super().__new__(cls, _render(key, values, _current))
        self.key, self.values = key, values
        return self

    def render(self, code):
        return _render(self.key, self.values, code)


def _render(key, values, code):
    text = MESSAGES[key][LANGUAGES.index(code)]
    return text.format(**{k: localize(v, code) for k, v in values.items()}) if values else text


def t(key, **values):
    return Text(key, values)


def localize(value, code=None):
    """Show a collected message in another language; other values pass through unchanged."""
    code = code or _current
    if isinstance(value, Text):
        return value.render(code)
    if isinstance(value, BaseException) and len(value.args) == 1 and isinstance(value.args[0], Text):
        return value.args[0].render(code)
    return value


def message(exc):
    """The message of an exception, still translatable when it came from t()."""
    return exc.args[0] if len(exc.args) == 1 and isinstance(exc.args[0], Text) else str(exc)


@contextlib.contextmanager
def using(code):
    """Render in another language temporarily, e.g. the English copy of a report."""
    global _current
    previous, _current = _current, set_language(code)
    try:
        yield
    finally:
        _current = previous


def num(value, digits=3, unit=""):
    """Format a measurement, or show "not available" instead of None."""
    return t("common.na") if value is None else f"{value:.{digits}f}{unit}"


def option_value(argv):
    """Read --lang before argparse runs, so help text and errors are localized too."""
    for i, arg in enumerate(argv):
        if arg == "--lang" and i + 1 < len(argv):
            return argv[i + 1]
        if arg.startswith("--lang="):
            return arg.split("=", 1)[1]
    return None


def parse_option(value):
    """argparse type for --lang."""
    if value.strip().lower() == "auto":
        return "auto"
    code = normalize(value)
    if not code:
        raise argparse.ArgumentTypeError(t("lang.invalid", value=value))
    return code


def add_argument(parser):
    parser.add_argument("--lang", type=parse_option, metavar="{auto,en,zh-CN,zh-TW,ja}", help=t("help.lang"))


def ask(default, input_fn=input, out=None):
    out = sys.stdout if out is None else out
    print("Language / 语言 / 語言 / 言語", file=out)
    for i, code in enumerate(LANGUAGES, 1):
        print(f"  {i}) {NAMES[code]}", file=out)
    number = LANGUAGES.index(default) + 1
    for _ in range(3):
        try:
            answer = input_fn(f"[1-{len(LANGUAGES)}, Enter = {number}] > ").strip()
        except EOFError:
            return default
        except KeyboardInterrupt:
            print(file=out)
            raise SystemExit(130)
        if not answer:
            return default
        if answer.isdigit() and 1 <= int(answer) <= len(LANGUAGES):
            return LANGUAGES[int(answer) - 1]
        code = normalize(answer)
        if code:
            return code
    return default


def setup(argv, interactive=True, environ=None, stdin=None, stdout=None):
    """Choose the language once per process: --lang, then OMARCHY_LAB_LANG, then
    an interactive question (terminal only), then the locale, then English."""
    global _configured
    if _configured:
        return _current
    _configured = True
    environ = os.environ if environ is None else environ
    stdin = sys.stdin if stdin is None else stdin
    stdout = sys.stdout if stdout is None else stdout
    detected = from_environment(environ) or "en"
    explicit = option_value(argv)
    if explicit is not None:
        # An invalid value falls back to the locale; argparse then reports it.
        return set_language(normalize(explicit) or detected)
    configured = environ.get(ENV_VAR, "")
    if configured.strip().lower() == "auto":
        return set_language(detected)
    if normalize(configured):
        return set_language(normalize(configured))
    wants_help = any(a in ("-h", "--help") for a in argv)
    if interactive and not wants_help and _is_tty(stdin) and _is_tty(stdout):
        set_language(ask(detected, out=stdout))
        print(t("lang.selected", name=NAMES[_current], code=_current), file=stdout, flush=True)
        return _current
    return set_language(detected)


def _is_tty(stream):
    try:
        return stream.isatty()
    except (AttributeError, ValueError):
        return False


MESSAGES = {
    # Language selection
    "lang.selected": (
        "Language: {name}. Add --lang {code} to skip this question next time.",
        "语言：{name}。下次加上 --lang {code} 即可跳过这一步。",
        "語言：{name}。下次加上 --lang {code} 即可略過這一步。",
        "言語：{name}。次回は --lang {code} を付けるとこの質問を省略できます。"),
    "lang.invalid": (
        "unsupported language {value!r}; choose auto, en, zh-CN, zh-TW or ja",
        "不支持的语言 {value!r}；可选 auto、en、zh-CN、zh-TW、ja",
        "不支援的語言 {value!r}；可選 auto、en、zh-CN、zh-TW、ja",
        "対応していない言語です {value!r}。auto、en、zh-CN、zh-TW、ja から選んでください"),

    # Shared values
    "common.na": ("N/A", "无数据", "無資料", "データなし"),
    "common.not_observed": ("not observed", "未观测", "未觀測", "未観測"),
    "common.pass": ("PASS", "通过", "通過", "合格"),
    "common.fail": ("FAIL", "未通过", "未通過", "不合格"),

    # Command-line help
    "help.lang": (
        "language for prompts and reports: en, zh-CN, zh-TW, ja, or auto (follow the system locale). "
        "Without it, a terminal run asks at start. Also settable with OMARCHY_LAB_LANG.",
        "提示与报告的语言：en、zh-CN、zh-TW、ja，或 auto（跟随系统区域设置）。"
        "不指定时，在终端中会于开始时询问。也可用环境变量 OMARCHY_LAB_LANG 设置。",
        "提示與報告的語言：en、zh-CN、zh-TW、ja，或 auto（跟隨系統地區設定）。"
        "未指定時，在終端機中會於開始時詢問。也可用環境變數 OMARCHY_LAB_LANG 設定。",
        "プロンプトとレポートの言語：en、zh-CN、zh-TW、ja、または auto（システムのロケールに従う）。"
        "指定しない場合、ターミナルでは開始時に選択を求めます。環境変数 OMARCHY_LAB_LANG でも設定できます。"),
    "help.lab_description": (
        "Omarchy Lab {version}: typical, agent, daily. Run as your normal Linux user.\n\n"
        "python3 omarchy-lab.pyz typical\n"
        "python3 omarchy-lab.pyz agent                         # local replay; no LLM\n"
        "python3 omarchy-lab.pyz agent --live                  # ONE real Pi task\n"
        "python3 omarchy-lab.pyz agent --live --model MODEL --rounds 3\n"
        "python3 omarchy-lab.pyz daily                         # local browser + programming\n"
        "python3 omarchy-lab.pyz daily --observe-update        # observe a user-run update\n\n"
        "The temporary working directory is NOT a security sandbox for an external agent.\n"
        "Live mode uses your existing agent login/settings and can incur provider charges.\n"
        "No model call happens without --live. No mode launches a real system update.",
        "Omarchy Lab {version}：typical、agent、daily。请用普通 Linux 用户运行。\n\n"
        "python3 omarchy-lab.pyz typical\n"
        "python3 omarchy-lab.pyz agent                         # 本机回放，不调用模型\n"
        "python3 omarchy-lab.pyz agent --live                  # 一次真实 Pi 任务\n"
        "python3 omarchy-lab.pyz agent --live --model MODEL --rounds 3\n"
        "python3 omarchy-lab.pyz daily                         # 本地浏览器＋编程\n"
        "python3 omarchy-lab.pyz daily --observe-update        # 观察你自己启动的更新\n\n"
        "临时工作目录不是外部 Agent 的安全沙箱。\n"
        "--live 使用你现有的 Agent 登录与设置，可能产生服务商费用。\n"
        "不加 --live 不会调用模型。任何模式都不会启动真实系统更新。",
        "Omarchy Lab {version}：typical、agent、daily。請以一般 Linux 使用者執行。\n\n"
        "python3 omarchy-lab.pyz typical\n"
        "python3 omarchy-lab.pyz agent                         # 本機重播，不呼叫模型\n"
        "python3 omarchy-lab.pyz agent --live                  # 一次真實 Pi 任務\n"
        "python3 omarchy-lab.pyz agent --live --model MODEL --rounds 3\n"
        "python3 omarchy-lab.pyz daily                         # 本機瀏覽器＋程式設計\n"
        "python3 omarchy-lab.pyz daily --observe-update        # 觀察你自行啟動的更新\n\n"
        "臨時工作目錄不是外部 Agent 的安全沙箱。\n"
        "--live 使用你現有的 Agent 登入與設定，可能產生服務商費用。\n"
        "不加 --live 不會呼叫模型。任何模式都不會啟動真實的系統更新。",
        "Omarchy Lab {version}：typical、agent、daily。一般の Linux ユーザーで実行してください。\n\n"
        "python3 omarchy-lab.pyz typical\n"
        "python3 omarchy-lab.pyz agent                         # ローカルリプレイ、モデル呼び出しなし\n"
        "python3 omarchy-lab.pyz agent --live                  # 実際の Pi タスクを 1 回\n"
        "python3 omarchy-lab.pyz agent --live --model MODEL --rounds 3\n"
        "python3 omarchy-lab.pyz daily                         # ローカルブラウザ＋プログラミング\n"
        "python3 omarchy-lab.pyz daily --observe-update        # 自分で開始した更新を観測\n\n"
        "一時作業ディレクトリは外部 Agent 用のセキュリティサンドボックスではありません。\n"
        "--live は既存の Agent のログインと設定を使うため、プロバイダーの料金が発生する場合があります。\n"
        "--live を付けない限りモデルは呼び出しません。どのモードも実際のシステム更新は行いません。"),
    "help.live": (
        "agent mode: explicitly run a real agent; by default only the fixed local replay runs",
        "agent模式明确运行真实Agent；默认只测本机固定回放",
        "agent 模式：明確執行真實 Agent；預設只測本機固定重播",
        "agent モード：実 Agent を明示的に実行します。デフォルトではローカル固定リプレイのみ"),
    "help.agent_command": (
        "custom non-interactive command (split with shlex, no shell); the fixed prompt is appended as the last argument",
        "自定义非交互命令（shlex拆分，不经shell）；固定prompt追加为最后一个参数",
        "自訂非互動指令（以 shlex 拆分，不經 shell）；固定 prompt 會附加為最後一個參數",
        "カスタムの非対話コマンド（shlex で分割、シェルを経由しない）。固定プロンプトを最後の引数として追加します"),
    "help.model": (
        "model for the default Pi adapter; pin it for formal comparisons",
        "默认Pi适配器的模型，正式对照应固定",
        "預設 Pi 轉接器使用的模型，正式對照時應固定",
        "デフォルトの Pi アダプターで使うモデル。正式な比較では固定してください"),
    "help.provider": (
        "provider for the default Pi adapter; pin it for formal comparisons",
        "默认Pi适配器的provider，正式对照应固定",
        "預設 Pi 轉接器使用的 provider，正式對照時應固定",
        "デフォルトの Pi アダプターで使う provider。正式な比較では固定してください"),
    "help.rounds": (
        "live agent rounds, default 1; every round may consume quota",
        "真实Agent轮数，默认1；每轮都可能消耗额度",
        "真實 Agent 輪數，預設 1；每輪都可能消耗額度",
        "実 Agent のラウンド数（デフォルト 1）。各ラウンドで利用枠を消費する可能性があります"),
    "help.timeout": (
        "time limit per live agent round in seconds, 60..1800",
        "每轮真实Agent秒数上限，60..1800",
        "每輪真實 Agent 的秒數上限，60..1800",
        "実 Agent 1 ラウンドあたりの制限時間（秒）、60..1800"),
    "help.seconds": (
        "length of each daily phase in seconds, default 60; update observation default 600",
        "日常每阶段时长（秒），默认60；更新观察默认600",
        "日常模式每階段時長（秒），預設 60；更新觀察預設 600",
        "daily の各フェーズの長さ（秒、デフォルト 60）。更新観測のデフォルトは 600"),
    "help.tabs": (
        "number of browser tabs in daily mode, default 8",
        "日常模式的浏览器标签页数，默认8",
        "日常模式的瀏覽器分頁數，預設 8",
        "daily モードのブラウザタブ数（デフォルト 8）"),
    "help.observe_update": (
        "daily mode: only observe a real update that you start yourself; never runs the update",
        "日常模式只观察你另行启动的真实更新，不自动执行更新",
        "日常模式只觀察你另外啟動的真實更新，不會自動執行更新",
        "daily モード：自分で開始した実際の更新を観測するだけで、更新は実行しません"),
    "help.quick": (
        "shortened validation, not a formal result; cannot be combined with --live",
        "缩短验证，非正式成绩；不可与--live同用",
        "縮短的驗證，非正式成績；不可與 --live 同時使用",
        "短縮した検証で正式な結果ではありません。--live とは併用できません"),
    "help.bench_quick": (
        "about half a minute of flow validation; not comparable with formal results",
        "约半分钟的流程验证；不能与正式成绩比较",
        "約半分鐘的流程驗證；不能與正式成績比較",
        "約 30 秒の流れの確認。正式な結果とは比較できません"),
    "help.work_dir": (
        "directory for test files, default your home directory; existing files there are never touched",
        "测试文件所在目录，默认家目录；不会触碰该目录原有文件",
        "測試檔案所在目錄，預設為家目錄；不會動到該目錄原有的檔案",
        "テストファイルを置くディレクトリ（デフォルトはホーム）。既存のファイルには触れません"),
    "help.output_dir": (
        "report directory, default {path}",
        "报告目录，默认 {path}",
        "報告目錄，預設 {path}",
        "レポートの保存先（デフォルト {path}）"),
    "help.stop_temp": (
        "CPU sampled temperature stop line, default 90°C",
        "CPU采样温度停止线，默认90°C",
        "CPU 取樣溫度停止線，預設 90°C",
        "CPU サンプリング温度の停止ライン（デフォルト 90°C）"),
    "help.bench_description": (
        "Omarchy Bench {version} (typical mode): repeatable CPU, memory, disk, small-file and sustained-load tests "
        "using ordinary temporary files only.\n\n"
        "Run as your normal user. Needs Python >= 3.9, sysbench, fio (Jens Axboe's), findmnt and lsblk.\n"
        "Install on Omarchy: sudo pacman -S --needed fio sysbench\n"
        "--quick is a reduced smoke test; its results must not be compared with full runs.",
        "Omarchy Bench {version}（典型测试）：只用普通临时文件，可重复地测试 CPU、内存、磁盘、小文件和持续负载。\n\n"
        "用普通用户运行。需要 Python >= 3.9、sysbench、fio（Jens Axboe 的版本）、findmnt 和 lsblk。\n"
        "Omarchy 上安装：sudo pacman -S --needed fio sysbench\n"
        "--quick 是精简的流程验证，结果不能与正式测试比较。",
        "Omarchy Bench {version}（典型測試）：只使用一般臨時檔案，可重複地測試 CPU、記憶體、磁碟、小檔案與持續負載。\n\n"
        "以一般使用者執行。需要 Python >= 3.9、sysbench、fio（Jens Axboe 的版本）、findmnt 與 lsblk。\n"
        "在 Omarchy 上安裝：sudo pacman -S --needed fio sysbench\n"
        "--quick 是精簡的流程驗證，結果不能與正式測試比較。",
        "Omarchy Bench {version}（typical モード）：通常の一時ファイルだけを使い、CPU、メモリ、ディスク、小ファイル、"
        "持続負荷を再現可能な形でテストします。\n\n"
        "一般ユーザーで実行してください。Python >= 3.9、sysbench、fio（Jens Axboe 版）、findmnt、lsblk が必要です。\n"
        "Omarchy でのインストール：sudo pacman -S --needed fio sysbench\n"
        "--quick は簡易的な流れの確認で、結果は正式な実行と比較できません。"),

    # Argument and environment errors
    "err.linux_user": (
        "Run this on Linux/Omarchy as your normal user; do not sudo the whole script.",
        "请在Linux/Omarchy中用普通用户运行，不要sudo整份脚本。",
        "請在 Linux/Omarchy 中以一般使用者執行，不要用 sudo 執行整份腳本。",
        "Linux/Omarchy 上で一般ユーザーとして実行してください。スクリプト全体を sudo で実行しないでください。"),
    "err.agent_only": (
        "--live and agent settings only apply to agent mode. Daily mode uses the repeatable local programming task.",
        "--live / Agent设置仅用于agent模式。日常默认使用可重复的本机编程任务。",
        "--live / Agent 設定僅用於 agent 模式。日常模式預設使用可重複的本機程式設計任務。",
        "--live と Agent 設定は agent モード専用です。daily モードは再現可能なローカルのプログラミングタスクを使います。"),
    "err.observe_daily_only": (
        "--observe-update only applies to daily mode.",
        "--observe-update仅用于daily模式。",
        "--observe-update 僅用於 daily 模式。",
        "--observe-update は daily モード専用です。"),
    "err.quick_live": (
        "--quick never makes real model calls; remove --quick to run --live explicitly.",
        "--quick不发起真实模型调用；请去掉--quick再明确运行--live。",
        "--quick 不會發出真實的模型呼叫；請移除 --quick 再明確執行 --live。",
        "--quick では実際のモデル呼び出しを行いません。--live を実行するには --quick を外してください。"),
    "err.custom_model": (
        "With a custom command, put the model settings directly in --agent-command.",
        "自定义命令请把模型设置直接写进--agent-command。",
        "使用自訂指令時，請把模型設定直接寫進 --agent-command。",
        "カスタムコマンドを使う場合は、モデル設定を --agent-command に直接書いてください。"),
    "err.needs_live": (
        "Agent settings also require --live; the default replay never calls an agent.",
        "Agent设置需要同时指定--live；默认回放不会调用Agent。",
        "Agent 設定需要同時指定 --live；預設重播不會呼叫 Agent。",
        "Agent 設定には --live も必要です。デフォルトのリプレイは Agent を呼び出しません。"),
    "err.provider_model": (
        "--provider also requires --model.",
        "--provider需要同时指定--model。",
        "--provider 需要同時指定 --model。",
        "--provider には --model の指定も必要です。"),
    "err.timeout_range": (
        "--timeout must be 60..1800 seconds.",
        "--timeout范围60..1800秒。",
        "--timeout 範圍為 60..1800 秒。",
        "--timeout は 60..1800 秒の範囲で指定してください。"),
    "err.seconds_range": (
        "--seconds must be 2..1800.",
        "--seconds范围2..1800。",
        "--seconds 範圍為 2..1800。",
        "--seconds は 2..1800 の範囲で指定してください。"),
    "err.plain_dir": (
        "The test directory must be an ordinary directory.",
        "测试目录必须是普通文件目录。",
        "測試目錄必須是一般的檔案目錄。",
        "テストディレクトリは通常のディレクトリである必要があります。"),
    "err.space_1g": (
        "At least 1 GiB of free space is required.",
        "至少需要1GiB可用空间。",
        "至少需要 1GiB 可用空間。",
        "少なくとも 1GiB の空き容量が必要です。"),
    "err.locked": (
        "Another test is already running in the same directory.",
        "已有同目录测试在运行。",
        "已有同目錄的測試在執行。",
        "同じディレクトリで別のテストが実行中です。"),
    "err.linux_only": (
        "This script only runs on Linux/Omarchy.",
        "这份脚本仅用于 Linux/Omarchy。",
        "這份腳本僅用於 Linux/Omarchy。",
        "このスクリプトは Linux/Omarchy 専用です。"),
    "err.no_root": (
        "Run as your normal user; do not sudo the whole script. Use sudo only to install dependencies.",
        "请用普通用户运行，不要 sudo 整份脚本；sudo 只用于安装依赖。",
        "請以一般使用者執行，不要用 sudo 執行整份腳本；sudo 只用於安裝相依套件。",
        "一般ユーザーで実行してください。スクリプト全体を sudo で実行しないでください。sudo は依存パッケージのインストールにだけ使います。"),
    "err.python": (
        "Python 3.9 or newer is required.",
        "需要 Python 3.9 或更新版本。",
        "需要 Python 3.9 或更新版本。",
        "Python 3.9 以降が必要です。"),
    "err.missing": (
        "Missing {tools}. Install first: sudo pacman -S --needed fio sysbench util-linux; "
        "if that fails, use Omarchy's own update process.",
        "缺少 {tools}。先安装：sudo pacman -S --needed fio sysbench util-linux；失败时使用 Omarchy 自带更新流程。",
        "缺少 {tools}。請先安裝：sudo pacman -S --needed fio sysbench util-linux；失敗時請使用 Omarchy 內建的更新流程。",
        "{tools} がありません。先にインストールしてください：sudo pacman -S --needed fio sysbench util-linux。"
        "失敗する場合は Omarchy 標準の更新手順を使ってください。"),
    "err.fio_wrong": (
        "fio must be Jens Axboe's fio, not the Python Fiona command of the same name; sysbench must also work.",
        "fio 必须是 Jens Axboe 的 fio，不是 Python Fiona 的同名命令；sysbench 也必须可用。",
        "fio 必須是 Jens Axboe 的 fio，而不是 Python Fiona 的同名指令；sysbench 也必須可用。",
        "fio は Jens Axboe の fio である必要があります（Python の Fiona に含まれる同名コマンドではありません）。sysbench も使える状態にしてください。"),
    "err.work_dir": (
        "--work-dir must be an existing directory on an ordinary disk.",
        "--work-dir 必须是普通磁盘上的现有目录。",
        "--work-dir 必須是一般磁碟上的既有目錄。",
        "--work-dir には通常のディスク上にある既存のディレクトリを指定してください。"),
    "err.mount_unknown": (
        "Cannot determine the mount source of the test directory; stopping to avoid testing the wrong device.",
        "无法确定测试目录挂载来源，停止以免测错设备。",
        "無法確定測試目錄的掛載來源，停止以免測錯裝置。",
        "テストディレクトリのマウント元を特定できません。誤ったデバイスを測定しないよう停止します。"),
    "err.fs_invalid": (
        "The current mount is not an ordinary filesystem usable for a local disk comparison: {mount}",
        "当前挂载不是可用于本机磁盘对照的普通文件系统：{mount}",
        "目前的掛載不是可用於本機磁碟對照的一般檔案系統：{mount}",
        "現在のマウントは、ローカルディスクの比較に使える通常のファイルシステムではありません：{mount}"),
    "err.space_bench": (
        "Not enough free space: formal mode needs at least 8GiB, quick validation at least 512MiB.",
        "可用空间不足：正式模式至少保留8GiB，快速验证至少512MiB。",
        "可用空間不足：正式模式至少保留 8GiB，快速驗證至少 512MiB。",
        "空き容量が不足しています。正式モードには 8GiB 以上、クイック検証には 512MiB 以上が必要です。"),
    "err.bench_locked": (
        "Another run of this test is already in progress; wait for it to finish.",
        "已有另一轮本测试正在运行；请等其结束。",
        "已有另一輪本測試正在執行；請等待其結束。",
        "このテストの別の実行が進行中です。終了するまでお待ちください。"),

    # Run status shared by agent and daily modes
    "run.banner": (
        "Omarchy Lab {version}: {mode}\nReport directory: {out}",
        "Omarchy Lab {version}：{mode}\n报告目录：{out}",
        "Omarchy Lab {version}：{mode}\n報告目錄：{out}",
        "Omarchy Lab {version}：{mode}\nレポートの保存先：{out}"),
    "run.interrupted": (
        "The test was stopped; the saved results do not count as a complete run.",
        "测试被中止；已保存结果不能视为完整的一轮。",
        "測試被中止；已儲存的結果不能視為完整的一輪。",
        "テストが中断されました。保存済みの結果は完全な 1 回分とは見なせません。"),

    # Agent mode
    "agent.progress": (
        "Agent running for {elapsed:.0f}s; tool completion events: {tools}",
        "Agent 已运行 {elapsed:.0f}s，工具完成事件 {tools}",
        "Agent 已執行 {elapsed:.0f}s，工具完成事件 {tools}",
        "Agent 実行中 {elapsed:.0f}s、ツール完了イベント {tools}"),
    "agent.output_too_large": (
        "Agent output exceeded 32MiB; stopping and keeping the logs.",
        "Agent 输出超过32MiB，停止并保留日志。",
        "Agent 輸出超過 32MiB，停止並保留日誌。",
        "Agent の出力が 32MiB を超えたため停止しました。ログは保存されています。"),
    "agent.replay_round": (
        "Local toolchain replay {n}",
        "本机工具链回放 {n}",
        "本機工具鏈重播 {n}",
        "ローカルツールチェーンのリプレイ {n}"),
    "agent.command_missing": (
        "Agent command not found. The default needs Pi, logged in with a model configured; or pass --agent-command.",
        "找不到 Agent 命令。默认需要已登录并配置好模型的 Pi；也可传 --agent-command。",
        "找不到 Agent 指令。預設需要已登入並設定好模型的 Pi；也可以傳入 --agent-command。",
        "Agent コマンドが見つかりません。デフォルトでは、ログイン済みでモデルを設定した Pi が必要です。--agent-command で指定することもできます。"),
    "agent.live_banner": (
        "Live agent: {rounds} round(s), up to {timeout}s each. Uses your existing account/model and may consume quota or incur charges.",
        "真实 Agent：{rounds}轮；每轮最多{timeout}s。使用现有账号/模型，可能消耗额度或产生费用。",
        "真實 Agent：{rounds} 輪；每輪最多 {timeout}s。使用現有帳號／模型，可能消耗額度或產生費用。",
        "実 Agent：{rounds} ラウンド、各ラウンド最大 {timeout}s。既存のアカウント／モデルを使うため、利用枠を消費したり料金が発生したりする場合があります。"),
    "agent.sandbox_note": (
        "The temporary working directory is not a permission sandbox; the task only asks the agent to modify the test project.",
        "临时工作目录不是权限沙箱；任务仅要求修改测试工程。",
        "臨時工作目錄不是權限沙箱；任務只要求修改測試專案。",
        "一時作業ディレクトリは権限サンドボックスではありません。タスクはテスト用プロジェクトの変更だけを指示しています。"),
    "agent.replay_median": (
        "Local fixed toolchain replay: median {median:.3f}s, n={n}, per round [{values}]",
        "本机固定工具链回放：中位 {median:.3f}s，n={n}，各轮 [{values}]",
        "本機固定工具鏈重播：中位數 {median:.3f}s，n={n}，各輪 [{values}]",
        "ローカル固定ツールチェーンのリプレイ：中央値 {median:.3f}s、n={n}、各ラウンド [{values}]"),
    "agent.replay_passed": (
        "Local replay passed: {passed}/{total}",
        "本机回放成功：{passed}/{total}",
        "本機重播成功：{passed}/{total}",
        "ローカルリプレイ成功：{passed}/{total}"),
    "agent.live_passed": (
        "Live agent passed acceptance: {passed}/{total}",
        "真实 Agent 验收成功：{passed}/{total}",
        "真實 Agent 驗收成功：{passed}/{total}",
        "実 Agent 受け入れ判定合格：{passed}/{total}"),
    "agent.round_incomplete": (
        "Round {i}: {status}; the invocation record is incomplete and a request may have been sent; do not treat it as zero usage.",
        "第{i}轮：{status}，缺少完整调用记录，可能已发出请求；不视为零消耗。",
        "第 {i} 輪：{status}，缺少完整的呼叫紀錄，可能已送出請求；不視為零消耗。",
        "ラウンド {i}：{status}。呼び出し記録が不完全で、リクエストが送信された可能性があります。消費ゼロとは見なしません。"),
    "agent.round_line": (
        "Round {i}: {status}, end-to-end {wall:.2f}s, acceptance {passed}",
        "第{i}轮：{status}，端到端 {wall:.2f}s，验收 {passed}",
        "第 {i} 輪：{status}，端到端 {wall:.2f}s，驗收 {passed}",
        "ラウンド {i}：{status}、エンドツーエンド {wall:.2f}s、受け入れ判定 {passed}"),
    "agent.model": (
        "Model: {models}",
        "模型：{models}",
        "模型：{models}",
        "モデル：{models}"),
    "agent.model_unknown": (
        "not confirmed from events; see the command and local settings",
        "未从事件确认；参见命令与本机设置",
        "未從事件確認；請參閱指令與本機設定",
        "イベントから確認できず。コマンドとローカル設定を参照"),
    "agent.first_delta": (
        "First model delta / first text: {delta} / {text}",
        "首模型增量/首文字：{delta} / {text}",
        "首個模型增量／首段文字：{delta} / {text}",
        "最初のモデル増分／最初のテキスト：{delta} / {text}"),
    "agent.tool_union": (
        "Union of paired tool intervals: {union}; remaining unattributed: {remaining}",
        "已配对工具区间并集：{union}；其余未归因：{remaining}",
        "已配對工具區間聯集：{union}；其餘未歸因：{remaining}",
        "対になったツール区間の和集合：{union}、残りの未帰属時間：{remaining}"),
    "agent.tool_counts": (
        "Tool completions/errors/retries: {counts}",
        "工具完成/错误/重试：{counts}",
        "工具完成／錯誤／重試：{counts}",
        "ツール完了／エラー／リトライ：{counts}"),
    "agent.live_no_result": (
        "Live agent mode was requested, but there is no complete invocation result. Check each round's invocation.json "
        "to see whether a request was sent; do not treat it as zero usage.",
        "已请求真实Agent模式，但没有完整调用结果；是否发出请求请查看各轮 invocation.json，不能视为零消耗。",
        "已要求真實 Agent 模式，但沒有完整的呼叫結果；是否已送出請求請查看各輪的 invocation.json，不能視為零消耗。",
        "実 Agent モードが要求されましたが、完全な呼び出し結果がありません。リクエストが送信されたかどうかは各ラウンドの "
        "invocation.json を確認してください。消費ゼロとは見なせません。"),
    "agent.no_model": (
        "No model was called in this run. The local replay above is not an autonomous agent coding result; add --live to run a real agent.",
        "本轮没有调用模型。上述本机回放不是 Agent 自主编程成绩；加 --live 才运行真实 Agent。",
        "本輪沒有呼叫模型。上述本機重播不是 Agent 自主寫程式的成績；加上 --live 才會執行真實 Agent。",
        "今回はモデルを呼び出していません。上記のローカルリプレイは Agent の自律的なプログラミング結果ではありません。実 Agent を動かすには --live を付けてください。"),
    "agent.note_e2e": (
        "End-to-end time includes the model, network, agent orchestration and tool execution; it is not a pure hardware score.",
        "端到端时间包含模型、网络、Agent编排和工具执行；不能当作纯硬件成绩。",
        "端到端時間包含模型、網路、Agent 編排與工具執行；不能當作純硬體成績。",
        "エンドツーエンド時間にはモデル、ネットワーク、Agent のオーケストレーション、ツール実行が含まれます。純粋なハードウェア性能の結果ではありません。"),
    "agent.note_first_output": (
        "First output is not the first token, and tool event durations are not CPU time. Missing events mean not observed; they are never filled with zeros.",
        "首输出不等于首token；工具事件时长也不等于CPU计算时长。缺少事件即未观测，不补零冒充。",
        "首個輸出不等於首個 token；工具事件時長也不等於 CPU 運算時間。缺少事件即為未觀測，不以零值冒充。",
        "最初の出力は最初のトークンと同じではなく、ツールイベントの所要時間も CPU 時間ではありません。イベントが欠けている場合は未観測とし、ゼロで埋めることはしません。"),
    "agent.note_rounds": (
        "Each live round rebuilds the project and starts a new session; model caching and service load can still vary. "
        "For formal comparisons, pin provider/model/thinking/versions and run at least 3 rounds.",
        "真实任务每轮重建工程/新会话；模型缓存、服务负载仍可能变化。正式比较固定provider/model/thinking/版本，至少3轮。",
        "真實任務每輪都會重建專案並開啟新工作階段；模型快取與服務負載仍可能變化。正式比較請固定 provider/model/thinking/版本，至少 3 輪。",
        "実タスクはラウンドごとにプロジェクトを再構築し、新しいセッションで実行します。それでもモデルのキャッシュやサービス負荷は変動し得ます。"
        "正式な比較では provider／model／thinking／バージョンを固定し、少なくとも 3 ラウンド実行してください。"),

    # Daily mode
    "daily.phase1": (
        "Daily phase 1: programming workload alone",
        "日常阶段 1：编程工作单独运行",
        "日常階段 1：單獨執行程式設計工作",
        "日常フェーズ 1：プログラミング作業のみ"),
    "daily.open_browser": (
        "Opening a separate browser test window; keep the test dashboard tab in front.",
        "打开独立浏览器测试窗口；保持测试仪表盘标签页在前台。",
        "開啟獨立的瀏覽器測試視窗；請讓測試儀表板分頁保持在前景。",
        "専用のブラウザテストウィンドウを開きます。テストダッシュボードのタブを前面に表示したままにしてください。"),
    "daily.observe_banner": (
        "Observing multi-tab browsing + programming for at least the next {seconds}s. Start the update in another terminal "
        "using Omarchy's official process. This script will not start or stop the update.",
        "观察接下来至少 {seconds}s 的多标签＋编程：请在另一终端按 Omarchy 官方流程更新。脚本不会启动或中止更新。",
        "觀察接下來至少 {seconds}s 的多分頁＋程式設計：請在另一個終端機依 Omarchy 官方流程更新。腳本不會啟動或中止更新。",
        "これから少なくとも {seconds}s、複数タブ＋プログラミングを観測します。別のターミナルで Omarchy の公式手順に従って更新を開始してください。"
        "このスクリプトが更新を開始・中止することはありません。"),
    "daily.pacman_failed": (
        "At least one pacman package-list query failed, so package changes before/after the update cannot be confirmed; "
        "this must not be read as zero changes.",
        "至少一次 pacman 包清单查询失败，无法确认更新前后包版本变化；不能解释为零变化。",
        "至少一次 pacman 套件清單查詢失敗，無法確認更新前後的套件版本變化；不能解讀為沒有變化。",
        "pacman のパッケージ一覧取得が少なくとも 1 回失敗したため、更新前後のパッケージ変更を確認できません。変更ゼロとは解釈しないでください。"),
    "daily.phase2": (
        "Daily phase 2: multiple tabs + the same programming workload",
        "日常阶段 2：多标签页＋同一编程工作",
        "日常階段 2：多分頁＋相同的程式設計工作",
        "日常フェーズ 2：複数タブ＋同じプログラミング作業"),
    "daily.phase3": (
        "Daily phase 3: multiple tabs + programming + update-like unpack/disk-sync load (simulated)",
        "日常阶段 3：多标签页＋编程＋更新式解压/同步磁盘负载（模拟）",
        "日常階段 3：多分頁＋程式設計＋類更新的解壓縮／磁碟同步負載（模擬）",
        "日常フェーズ 3：複数タブ＋プログラミング＋更新風の展開／ディスク同期負荷（シミュレーション）"),
    "daily.sim_not_stopped": (
        "The simulated load did not finish within 15 seconds; termination was requested, so it cannot count as a complete load result.",
        "模拟负载未在15秒内正常结束；已请求终止，不能作为完整负载成绩。",
        "模擬負載未在 15 秒內正常結束；已要求終止，不能作為完整的負載成績。",
        "シミュレーション負荷が 15 秒以内に正常終了しませんでした。終了を要求したため、完全な負荷結果としては扱えません。"),
    "daily.sim_not_reaped": (
        "The simulated load did not finish within 15 seconds and its process has still not been reaped; "
        "its separate temporary directory is kept. This cannot count as a complete load result.",
        "模拟负载未在15秒内正常结束，进程仍未回收，保留其独立临时目录；不能作为完整负载成绩。",
        "模擬負載未在 15 秒內正常結束，處理程序仍未回收，保留其獨立的臨時目錄；不能作為完整的負載成績。",
        "シミュレーション負荷が 15 秒以内に終了せず、プロセスもまだ回収されていないため、専用の一時ディレクトリを残します。"
        "完全な負荷結果としては扱えません。"),
    "daily.sim_no_result": (
        "The simulated load did not return a complete result: {error}",
        "模拟负载没有返回完整结果：{error}",
        "模擬負載沒有回傳完整結果：{error}",
        "シミュレーション負荷から完全な結果が返されませんでした：{error}"),
    "daily.sim_exit": (
        "The simulated load exited abnormally: {code}",
        "模拟负载异常退出：{code}",
        "模擬負載異常結束：{code}",
        "シミュレーション負荷が異常終了しました：{code}"),
    "daily.browser_insufficient": (
        "{phase}: not enough visible-page samples; no valid browser responsiveness result.",
        "{phase} 可见页面样本不足；没有有效浏览器响应成绩。",
        "{phase} 可見頁面樣本不足；沒有有效的瀏覽器回應成績。",
        "{phase}：表示中ページのサンプルが不足しています。有効なブラウザ応答性の結果はありません。"),
    "daily.browser_coverage_low": (
        "{phase}: foreground sampling covered {ratio:.0%}, below this framework's measurement-validity requirement of "
        "{minimum:.0%}; keep the test page visible.",
        "{phase} 前台采样覆盖 {ratio:.0%}，低于本框架测量有效性要求 {minimum:.0%}；请保持测试页可见。",
        "{phase} 前景取樣涵蓋 {ratio:.0%}，低於本框架的量測有效性要求 {minimum:.0%}；請讓測試頁保持可見。",
        "{phase}：フォアグラウンドのサンプリング率は {ratio:.0%} で、このフレームワークの測定有効性要件 {minimum:.0%} を下回っています。"
        "テストページを表示したままにしてください。"),
    "daily.browser_key": (
        "Browser {key}: {value}",
        "浏览器 {key}: {value}",
        "瀏覽器 {key}: {value}",
        "ブラウザ {key}: {value}"),
    "daily.browser_exited": (
        "The browser exited before measurement finished.",
        "浏览器在测量完成前退出。",
        "瀏覽器在量測完成前結束。",
        "測定完了前にブラウザが終了しました。"),
    "daily.sim_no_files": (
        "The simulated load did not unpack and sync any file, so it is not a valid update-like unpack load.",
        "模拟负载未完成任何文件的解压同步，不能记为有效的更新式解压负载。",
        "模擬負載沒有完成任何檔案的解壓縮同步，不能記為有效的類更新解壓縮負載。",
        "シミュレーション負荷はどのファイルの展開・同期も完了していないため、有効な更新風の展開負荷とは見なせません。"),
    "daily.browser_cleanup_failed": (
        "Test browser cleanup failed: {error}",
        "测试浏览器清理失败：{error}",
        "測試瀏覽器清理失敗：{error}",
        "テスト用ブラウザの後片付けに失敗しました：{error}"),
    "daily.browser_incomplete": (
        "Browser observation incomplete.",
        "浏览器观测不完整。",
        "瀏覽器觀測不完整。",
        "ブラウザの観測が不完全です。"),
    "daily.measurement_note": (
        "The browser reports in batches about once per second; batches spanning a phase boundary are excluded, and a final "
        "unreported batch may be missing. Preparation/recovery periods are listed separately. Formal phases need foreground "
        "samples for at least 60% of the phase (25% with --quick); this is a measurement-coverage rule, not a performance pass mark.",
        "浏览器约每1秒批量回传；阶段交界批次被排除，末尾未回传批次可能缺失。准备/恢复时段单列。正式阶段须至少60%时段取得前台样本"
        "（quick为25%）；这是测量覆盖规则，不是性能及格线。",
        "瀏覽器約每 1 秒批次回傳；跨階段的批次會被排除，最後尚未回傳的批次可能遺失。準備／恢復時段另外列出。正式階段須在至少 60% 的時段"
        "取得前景樣本（quick 為 25%）；這是量測涵蓋規則，不是效能及格線。",
        "ブラウザは約 1 秒ごとにまとめて報告します。フェーズ境界をまたぐバッチは除外され、最後の未送信バッチは欠ける場合があります。"
        "準備・回復の時間帯は別に記録します。正式フェーズでは時間の 60% 以上（quick は 25%）でフォアグラウンドのサンプルが必要です。"
        "これは測定カバレッジの規則であり、性能の合格ラインではありません。"),
    "daily.phase_line": (
        "{phase}: median of passing tasks {median}, acceptance {passed}/{cycles}, relative to programming alone {ratio}",
        "{phase}: 成功任务中位 {median}，验收 {passed}/{cycles}，相对单独运行 {ratio}",
        "{phase}: 成功任務中位數 {median}，驗收 {passed}/{cycles}，相對單獨執行 {ratio}",
        "{phase}: 成功タスクの中央値 {median}、受け入れ判定 {passed}/{cycles}、単独実行比 {ratio}"),
    "daily.browser_header": (
        "Browser foreground metrics (details in daily-results.json):",
        "浏览器前台指标（详细结果见daily-results.json）：",
        "瀏覽器前景指標（詳細結果見 daily-results.json）：",
        "ブラウザのフォアグラウンド指標（詳細は daily-results.json）："),
    "daily.browser_line": (
        "{label}: {status} | rAF p95 {raf} | timer lateness p95 {timer}",
        "{label}: {status} | rAF p95 {raf} | 定时器延迟p95 {timer}",
        "{label}: {status} | rAF p95 {raf} | 計時器延遲 p95 {timer}",
        "{label}: {status} | rAF p95 {raf} | タイマー遅延 p95 {timer}"),
    "daily.note_raf": (
        "Only rAF intervals/timer lateness on visible pages are counted; this is not system FPS, mouse input latency or INP.",
        "仅统计可见页面的rAF间隔/定时器延迟；不是系统FPS、鼠标输入延迟或INP。",
        "僅統計可見頁面的 rAF 間隔／計時器延遲；不是系統 FPS、滑鼠輸入延遲或 INP。",
        "集計対象は表示中ページの rAF 間隔／タイマー遅延のみです。システム FPS、マウス入力遅延、INP ではありません。"),
    "daily.note_fixture": (
        "The fixed local page load excludes internet latency, extensions and real website scripts; background tabs keep the browser's default throttling.",
        "固定本地网页负载不包括公网延迟、扩展或真实网站脚本；后台标签页保留浏览器默认节流。",
        "固定本機網頁負載不包含網際網路延遲、擴充功能或真實網站腳本；背景分頁保留瀏覽器預設的節流。",
        "固定のローカルページ負荷には、インターネット遅延、拡張機能、実際の Web サイトのスクリプトは含まれません。"
        "バックグラウンドタブにはブラウザ既定のスロットリングが適用されたままです。"),
    "daily.real_update_note": (
        "This run was a real-update observation window: the script did not run the update, so it is not a repeatable benchmark.",
        "本轮为真实更新观察窗口：脚本未执行更新，不能当作可重复跑分。",
        "本輪為真實更新觀察時段：腳本未執行更新，不能當作可重複的跑分。",
        "今回は実際の更新の観測期間です。スクリプトは更新を実行していないため、再現可能なベンチマークではありません。"),
    "daily.packages_changed": (
        "Observed package version records: {added} added, {removed} removed.",
        "观察到包版本记录新增 {added}，移除 {removed}。",
        "觀察到套件版本紀錄新增 {added}，移除 {removed}。",
        "観測したパッケージバージョン記録：追加 {added}、削除 {removed}。"),
    "daily.packages_unknown": (
        "Package version changes: not observed; the package query did not succeed.",
        "包版本变化：未观测，包查询没有成功。",
        "套件版本變化：未觀測，套件查詢沒有成功。",
        "パッケージバージョンの変化：未観測（パッケージ照会に失敗）。"),
    "daily.sim_phase_note": (
        "Phase 3 is a simulated update-like local load; no packages were upgraded. Do not report it as real system update time.",
        "第三阶段是更新式本地负载模拟，没有升级软件包；不能把该成绩写成真实系统更新时间。",
        "第三階段是類更新的本機負載模擬，沒有升級套件；不能把這項成績寫成真實的系統更新時間。",
        "フェーズ 3 は更新風のローカル負荷のシミュレーションで、パッケージは更新していません。この結果を実際のシステム更新時間として扱わないでください。"),

    # Report shared by agent and daily modes
    "report.config": (
        "Machine: {machine} | {cpu} | {kernel}",
        "配置：{machine} | {cpu} | {kernel}",
        "配置：{machine} | {cpu} | {kernel}",
        "構成：{machine} | {cpu} | {kernel}"),
    "report.dir": (
        "Directory: {work_dir} | Mount: {mount}",
        "目录：{work_dir} | 挂载：{mount}",
        "目錄：{work_dir} | 掛載：{mount}",
        "ディレクトリ：{work_dir} | マウント：{mount}"),
    "report.cpu_peak": (
        "CPU sampled peak: {peak:.1f}°C",
        "CPU采样峰值：{peak:.1f}°C",
        "CPU 取樣峰值：{peak:.1f}°C",
        "CPU サンプリング最高温度：{peak:.1f}°C"),
    "report.no_sensor": (
        "CPU temperature: no sensor readable; temperature stop protection is unavailable.",
        "CPU温度：未读到传感器，温度停止保护不可用。",
        "CPU 溫度：讀不到感測器，溫度停止保護無法使用。",
        "CPU 温度：センサーを読み取れません。温度による停止保護は使えません。"),
    "report.mem_swap": (
        "Minimum available memory: {mem:.0f}MiB; maximum swap used: {swap:.0f}MiB",
        "最少可用内存：{mem:.0f}MiB；最高交换占用：{swap:.0f}MiB",
        "最低可用記憶體：{mem:.0f}MiB；最高置換空間使用量：{swap:.0f}MiB",
        "最小空きメモリ：{mem:.0f}MiB、最大スワップ使用量：{swap:.0f}MiB"),
    "report.phase_samples": (
        "System samples per phase (about 1 Hz; short phases may have no valid samples):",
        "各阶段系统采样（约1Hz，短阶段可能没有有效样本）：",
        "各階段系統取樣（約 1Hz，短階段可能沒有有效樣本）：",
        "フェーズ別のシステムサンプル（約 1Hz、短いフェーズでは有効なサンプルがない場合あり）："),
    "report.phase_sample_line": (
        "{label}: n={n}, mean CPU {cpu}, mean iowait {wait}",
        "{label}: n={n}，CPU均值 {cpu}，iowait均值 {wait}",
        "{label}: n={n}，CPU 平均 {cpu}，iowait 平均 {wait}",
        "{label}: n={n}、CPU 平均 {cpu}、iowait 平均 {wait}"),
    "report.notes_header": ("Notes:", "注意：", "注意：", "注意："),
    "report.note_no_score": (
        "There is no overall score; a fast task that fails acceptance still counts as a failure.",
        "无综合总分；快但未通过验收的任务仍算失败。",
        "無綜合總分；速度快但未通過驗收的任務仍算失敗。",
        "総合スコアはありません。速くても受け入れ判定に不合格のタスクは失敗として扱います。"),
    "report.note_storage": (
        "When changing storage, keep the same system/tool/task versions; an original Fusion Drive macOS vs pure-HDD Linux "
        "is not a single-variable comparison.",
        "改变存储时保留同一系统/工具/任务版本；原Fusion Drive macOS与纯HDD Linux不是单变量对照。",
        "更換儲存裝置時請保持相同的系統／工具／任務版本；原本 Fusion Drive 上的 macOS 與純 HDD 上的 Linux 不是單一變數的對照。",
        "ストレージを変える場合は、システム／ツール／タスクのバージョンを揃えてください。元の Fusion Drive 上の macOS と HDD のみの Linux の比較は、"
        "単一変数の比較ではありません。"),
    "report.note_quick": (
        "--quick only validates the flow; do not draw performance conclusions from it.",
        "quick仅验证流程，不用于性能结论。",
        "quick 僅驗證流程，不用於效能結論。",
        "quick は流れの確認用です。性能の結論には使わないでください。"),
    "report.path": (
        "Report: {path}",
        "报告：{path}",
        "報告：{path}",
        "レポート：{path}"),

    # Typical mode (Omarchy Bench)
    "mon.temp_stop": (
        "CPU temperature reached {temp:.1f}°C, hitting this script's {limit}°C stop line (not a hardware fault diagnosis).",
        "CPU 温度达到 {temp:.1f}°C，触发本脚本 {limit}°C 停止线（不是硬件故障诊断）。",
        "CPU 溫度達到 {temp:.1f}°C，觸發本腳本的 {limit}°C 停止線（不是硬體故障診斷）。",
        "CPU 温度が {temp:.1f}°C に達し、このスクリプトの停止ライン {limit}°C に到達しました（ハードウェア故障の診断ではありません）。"),
    "mon.failed": (
        "Monitor failed; the test was stopped: {error}",
        "监测器失败，测试已停止：{error}",
        "監測器失敗，測試已停止：{error}",
        "モニターが失敗したため、テストを停止しました：{error}"),
    "base.timeout": (
        "{phase} exceeded {timeout}s; stopping the test. See the raw logs.",
        "{phase} 超过 {timeout}s，停止测试；见 raw 日志。",
        "{phase} 超過 {timeout}s，停止測試；請見 raw 日誌。",
        "{phase} が {timeout}s を超えたため、テストを停止しました。raw ログを参照してください。"),
    "base.in_progress": (
        "In progress: {elapsed:.0f}s",
        "进行中：{elapsed:.0f}s",
        "進行中：{elapsed:.0f}s",
        "実行中：{elapsed:.0f}s"),
    "base.failed": (
        "{phase} failed (exit {code}): {output}",
        "{phase} 失败 (exit {code})：{output}",
        "{phase} 失敗 (exit {code})：{output}",
        "{phase} が失敗しました (exit {code})：{output}"),
    "base.sysbench_cpu": (
        "Could not parse sysbench CPU output; refusing to produce a fake score.",
        "无法解析 sysbench CPU 输出；不能生成虚假分数。",
        "無法解析 sysbench CPU 輸出；不能產生虛假分數。",
        "sysbench の CPU 出力を解析できません。偽のスコアは出しません。"),
    "base.mem_parse": (
        "Could not parse sysbench memory output.",
        "无法解析 sysbench 内存输出。",
        "無法解析 sysbench 記憶體輸出。",
        "sysbench のメモリ出力を解析できません。"),
    "base.fio_json": (
        "fio did not return valid JSON for a successful run: {error}. No fallback to cached I/O.",
        "fio 未返回成功的有效 JSON：{error}。没有退回缓存 I/O。",
        "fio 未回傳成功的有效 JSON：{error}。不會退回快取 I/O。",
        "fio が成功時の有効な JSON を返しませんでした：{error}。キャッシュ I/O へのフォールバックはしません。"),
    "base.fio_percentile": (
        "fio is missing nanosecond latency percentiles; check the raw output.",
        "fio 缺少纳秒延迟百分位；查看原始输出。",
        "fio 缺少奈秒延遲百分位數；請查看原始輸出。",
        "fio にナノ秒単位のレイテンシのパーセンタイルがありません。raw 出力を確認してください。"),
    "base.seq_write_len": (
        "Sequential write length mismatch; not a complete disk sample.",
        "顺序写入长度不符，不能视为完整磁盘样本。",
        "循序寫入長度不符，不能視為完整的磁碟樣本。",
        "シーケンシャル書き込みの長さが一致しないため、完全なディスクサンプルとは見なせません。"),
    "base.smallfiles_start": (
        "{phase}: {count} 4KiB files, fsync after each",
        "{phase}：{count} 个 4KiB 文件，逐个 fsync",
        "{phase}：{count} 個 4KiB 檔案，逐一 fsync",
        "{phase}：4KiB ファイル {count} 個、1 個ごとに fsync"),
    "base.smallfiles_timeout": (
        "Small-file task exceeded 180s; keeping the incomplete report.",
        "小文件任务超过 180s；保留未完成报告。",
        "小檔案任務超過 180s；保留未完成的報告。",
        "小ファイルのタスクが 180s を超えました。未完了のレポートを残します。"),
    "label.cpu_single": ("CPU single-thread", "CPU 单线程", "CPU 單執行緒", "CPU シングルスレッド"),
    "label.cpu_threads": ("CPU {threads} threads", "CPU {threads} 线程", "CPU {threads} 執行緒", "CPU {threads} スレッド"),
    "label.memory": (
        "128MiB sequential memory read",
        "128MiB 顺序内存读",
        "128MiB 循序記憶體讀取",
        "128MiB シーケンシャルメモリ読み取り"),
    "label.seq_write": (
        "Sequential write (incl. final sync and startup)",
        "顺序写（含末次同步及启动耗时）",
        "循序寫入（含最後同步與啟動耗時）",
        "シーケンシャル書き込み（最終同期と起動時間を含む）"),
    "label.seq_read": (
        "Sequential read 1MiB QD1",
        "顺序读 1MiB QD1",
        "循序讀取 1MiB QD1",
        "シーケンシャル読み取り 1MiB QD1"),
    "label.rand_iops": (
        "4KiB random read QD1",
        "4KiB 随机读 QD1",
        "4KiB 隨機讀取 QD1",
        "4KiB ランダム読み取り QD1"),
    "label.rand_lat": (
        "Random-read completion latency {suffix}",
        "随机读完成延迟 {suffix}",
        "隨機讀取完成延遲 {suffix}",
        "ランダム読み取り完了レイテンシ {suffix}"),
    "label.smallfiles": (
        "Create + sync {count} small files",
        "{count} 个小文件创建＋同步",
        "{count} 個小檔案建立＋同步",
        "小ファイル {count} 個の作成＋同期"),
    "bench.step1": (
        "[1/6] Idle baseline (stop using the machine; close downloads, updates and other agent tasks)",
        "[1/6] 空闲基线（请停止操作，关闭下载、更新和其他 agent 任务）",
        "[1/6] 閒置基準（請停止操作，關閉下載、更新與其他 agent 任務）",
        "[1/6] アイドル時のベースライン（操作を止め、ダウンロード、更新、他の agent タスクを閉じてください）"),
    "bench.step2": (
        "[2/6] CPU warm-up, single thread and all available threads",
        "[2/6] CPU 预热、单线程和全部可用线程",
        "[2/6] CPU 預熱、單執行緒與全部可用執行緒",
        "[2/6] CPU ウォームアップ、シングルスレッドと利用可能な全スレッド"),
    "bench.step3": (
        "[3/6] Sequential memory read over a 128MiB working set",
        "[3/6] 128MiB 工作区顺序内存读取",
        "[3/6] 128MiB 工作區循序記憶體讀取",
        "[3/6] 128MiB 作業領域でのシーケンシャルメモリ読み取り"),
    "bench.step4": (
        "[4/6] Disk: ordinary temporary file, direct I/O, QD1",
        "[4/6] 磁盘：普通临时文件，direct I/O，QD1",
        "[4/6] 磁碟：一般臨時檔案，direct I/O，QD1",
        "[4/6] ディスク：通常の一時ファイル、direct I/O、QD1"),
    "bench.step5": (
        "[5/6] Small-file synchronous writes",
        "[5/6] 小文件同步写入",
        "[5/6] 小檔案同步寫入",
        "[5/6] 小ファイルの同期書き込み"),
    "bench.step6": (
        "[6/6] Sustained CPU load and recovery",
        "[6/6] 持续 CPU 负载与恢复观察",
        "[6/6] 持續 CPU 負載與恢復觀察",
        "[6/6] 持続的な CPU 負荷と回復の観察"),
    "note.baseline_busy": (
        "Median baseline CPU busy >10%; background load present. Re-run when idle.",
        "基线 CPU 忙碌度中位数 >10%；存在背景负载，建议空闲后重跑。",
        "基準 CPU 忙碌度中位數 >10%；有背景負載，建議閒置後重跑。",
        "ベースラインの CPU 使用率の中央値が 10% を超えています。バックグラウンド負荷があるため、アイドル状態で再実行することをおすすめします。"),
    "note.no_temp": (
        "CPU temperature not readable: temperature protection is unavailable and cooling cannot be judged.",
        "未读取到 CPU 温度：温度保护不可用，不能判断散热表现。",
        "未讀取到 CPU 溫度：溫度保護無法使用，無法判斷散熱表現。",
        "CPU 温度を読み取れません。温度保護は使えず、冷却性能も判断できません。"),
    "note.sustained_drop": (
        "Throughput at the end of the sustained load was below 90% of the early part; judge it together with temperature, "
        "frequency and background tasks. This alone does not prove throttling.",
        "持续负载末段吞吐低于早段 90%；需结合温度、频率和背景任务判断，不能仅据此认定降频。",
        "持續負載末段吞吐量低於前段的 90%；需結合溫度、頻率與背景任務判斷，不能僅憑此認定降頻。",
        "持続負荷の終盤のスループットが序盤の 90% を下回りました。温度、周波数、バックグラウンドタスクと合わせて判断してください。"
        "これだけでスロットリングとは断定できません。"),
    "note.throttle": (
        "Kernel thermal_throttle counters increased; at least one hardware-reported thermal limit event occurred in this run.",
        "内核 thermal_throttle 计数增加；本轮至少观察到一次硬件报告的热限制事件。",
        "核心 thermal_throttle 計數增加；本輪至少觀察到一次硬體回報的熱限制事件。",
        "カーネルの thermal_throttle カウンターが増加しました。今回、ハードウェアが報告した熱制限イベントが少なくとも 1 回発生しています。"),
    "note.swap": (
        "Swap-in/out happened during the test; check memory pressure and background tasks.",
        "测试期间发生换入/换出；检查内存压力及后台任务。",
        "測試期間發生置換進出；請檢查記憶體壓力與背景任務。",
        "テスト中にスワップイン／アウトが発生しました。メモリ逼迫とバックグラウンドタスクを確認してください。"),
    "note.kernel_log": (
        "Kernel log access may be incomplete; this cannot be used to claim there were no kernel errors.",
        "内核日志权限可能不完整；不能据此声称没有内核错误。",
        "核心日誌權限可能不完整；不能據此宣稱沒有核心錯誤。",
        "カーネルログへのアクセス権が不完全な可能性があります。これをもってカーネルエラーがなかったとは言えません。"),
    "note.spread": (
        "{label}: range/median is {spread:.1f}% (hint threshold 15%, not a significance test); consider re-running.",
        "{label} 极差/中位数为 {spread:.1f}%（提示阈值15%，不是显著性检验）；建议复测。",
        "{label} 全距／中位數為 {spread:.1f}%（提示門檻 15%，不是顯著性檢定）；建議重測。",
        "{label}：範囲／中央値が {spread:.1f}% です（目安のしきい値は 15%、有意性検定ではありません）。再測定をおすすめします。"),
    "note.virtual_fs": (
        "Quick validation ran on a virtual/non-local filesystem; none of the numbers represent the target machine.",
        "快速验证运行在虚拟/非本机磁盘文件系统；所有数值不能代表目标机器。",
        "快速驗證執行在虛擬／非本機磁碟的檔案系統上；所有數值都不能代表目標機器。",
        "クイック検証は仮想／ローカル以外のファイルシステム上で実行されました。どの数値も対象マシンを代表しません。"),
    "note.other_mount": (
        "The test directory is not on the same mount device as the system root; this is not a root-partition disk result.",
        "测试目录与系统根目录不在同一挂载设备；这不是根分区磁盘成绩。",
        "測試目錄與系統根目錄不在同一個掛載裝置上；這不是根分割區的磁碟成績。",
        "テストディレクトリはシステムのルートと同じマウントデバイス上にありません。ルートパーティションのディスク結果ではありません。"),
    "bench.profile_quick": (
        "quick validation (not for performance comparison)",
        "快速验证（不能作性能对照）",
        "快速驗證（不能作效能對照）",
        "クイック検証（性能比較には使えません）"),
    "bench.profile_full": (
        "formal test: median of three rounds",
        "正式测试：三轮中位数",
        "正式測試：三輪中位數",
        "正式テスト：3 ラウンドの中央値"),
    "bench.status": (
        "Status: {status} | Duration {minutes:.1f} min",
        "状态：{status} | 用时 {minutes:.1f} 分钟",
        "狀態：{status} | 耗時 {minutes:.1f} 分鐘",
        "状態：{status} | 所要時間 {minutes:.1f} 分"),
    "bench.cpu": (
        "CPU: {cpu} | Available logical threads {threads}",
        "CPU：{cpu} | 可用逻辑线程 {threads}",
        "CPU：{cpu} | 可用邏輯執行緒 {threads}",
        "CPU：{cpu} | 利用可能な論理スレッド {threads}"),
    "bench.memory": (
        "Memory: {gib:.2f} GiB",
        "内存：{gib:.2f} GiB",
        "記憶體：{gib:.2f} GiB",
        "メモリ：{gib:.2f} GiB"),
    "bench.mount": (
        "Test mount: {source} ({fstype})",
        "测试挂载：{source} ({fstype})",
        "測試掛載：{source} ({fstype})",
        "テスト対象のマウント：{source} ({fstype})"),
    "bench.medium_rotational": ("HDD/rotational", "HDD/旋转介质", "HDD／旋轉媒體", "HDD／回転型"),
    "bench.medium_solid": ("non-rotational", "非旋转介质", "非旋轉媒體", "非回転型"),
    "bench.disk": (
        "Underlying device: {name} | {model} | {medium}",
        "底层设备：{name} | {model} | {medium}",
        "底層裝置：{name} | {model} | {medium}",
        "基盤デバイス：{name} | {model} | {medium}"),
    "bench.disk_unknown": (
        "Underlying physical disk: unknown (could not be detected automatically); see the lsblk/findmnt data in results.json.",
        "底层物理盘：未知（未能自动确认），见 results.json 的 lsblk/findmnt 信息。",
        "底層實體磁碟：未知（無法自動確認），請見 results.json 的 lsblk/findmnt 資訊。",
        "基盤の物理ディスク：不明（自動判定できませんでした）。results.json の lsblk/findmnt 情報を参照してください。"),
    "bench.method": (
        "Method: direct I/O; 1 process/QD1; disk window {mib:.0f} MiB; CPU max-prime=20000",
        "方法：direct I/O；1进程/QD1；磁盘窗口 {mib:.0f} MiB；CPU max-prime=20000",
        "方法：direct I/O；1 個處理程序／QD1；磁碟範圍 {mib:.0f} MiB；CPU max-prime=20000",
        "方法：direct I/O、1 プロセス／QD1、ディスク範囲 {mib:.0f} MiB、CPU max-prime=20000"),
    "bench.table_header": (
        "Metric | Median | Per-round values | Range/median",
        "指标 | 中位数 | 每轮原值 | 极差/中位数",
        "指標 | 中位數 | 每輪原值 | 全距／中位數",
        "指標 | 中央値 | 各ラウンドの値 | 範囲／中央値"),
    "bench.no_temp": (
        "CPU temperature: not observed",
        "CPU 温度：未观测到",
        "CPU 溫度：未觀測到",
        "CPU 温度：未観測"),
    "bench.phase_temp": (
        "{phase}: median {median:.1f}°C / max {max:.1f}°C",
        "{phase}: 中位 {median:.1f}°C / 最高 {max:.1f}°C",
        "{phase}: 中位數 {median:.1f}°C / 最高 {max:.1f}°C",
        "{phase}: 中央値 {median:.1f}°C / 最高 {max:.1f}°C"),
    "bench.sustained": (
        "Sustained CPU last 30s / early 30s throughput: {ratio:.1f}% (early part excludes the first 10s; not a standalone throttling criterion)",
        "持续CPU末30s/早段30s吞吐：{ratio:.1f}%（早段排除首10s；非单独降频判据）",
        "持續 CPU 末 30s／前段 30s 吞吐量：{ratio:.1f}%（前段排除首 10s；不能單獨作為降頻判據）",
        "持続 CPU の終盤 30s／序盤 30s のスループット：{ratio:.1f}%（序盤は最初の 10s を除外。これだけではスロットリングの判定基準になりません）"),
    "bench.crc": (
        "Temporary data verification: {value}",
        "临时数据校验：{value}",
        "臨時資料校驗：{value}",
        "一時データの検証：{value}"),
    "bench.crc_pass": (
        "PASS (limited sample, not full-drive health)",
        "通过（有限样本，不代表整盘健康）",
        "通過（有限樣本，不代表整顆磁碟健康）",
        "合格（限られたサンプル。ディスク全体の健全性ではありません）"),
    "bench.not_done": ("not completed", "未完成", "未完成", "未完了"),
    "bench.swap": (
        "Swap page changes: {deltas}",
        "交换页变化：{deltas}",
        "置換頁變化：{deltas}",
        "スワップページの変化：{deltas}"),
    "bench.tips_header": ("Notes:", "提示：", "提示：", "補足："),
    "bench.tip_percentile": (
        "Random-read p95/p99 is the median of each round's completion-latency percentile, not a percentile over all I/O combined.",
        "随机读p95/p99是各轮完成延迟百分位的中位数，不是合并全部I/O后的百分位。",
        "隨機讀取 p95/p99 是各輪完成延遲百分位數的中位數，不是合併全部 I/O 後的百分位數。",
        "ランダム読み取りの p95/p99 は各ラウンドの完了レイテンシのパーセンタイルの中央値であり、全 I/O をまとめたパーセンタイルではありません。"),
    "bench.tip_direct_io": (
        "direct I/O reduces OS page-cache effects; the disk firmware cache is not disabled. Results include filesystem/encryption/CoW overhead.",
        "direct I/O减少OS页缓存影响；未禁用磁盘固件缓存。结果包含文件系统/加密/CoW开销。",
        "direct I/O 減少 OS 頁面快取的影響；未停用磁碟韌體快取。結果包含檔案系統／加密／CoW 的額外負擔。",
        "direct I/O で OS のページキャッシュの影響を減らしていますが、ディスクのファームウェアキャッシュは無効化していません。"
        "結果にはファイルシステム／暗号化／CoW のオーバーヘッドが含まれます。"),
    "bench.tip_window": (
        "The default 2GiB file only covers a local address range; this is not a whole-drive seek, capacity or health test.",
        "默认2GiB文件仅覆盖局部地址；不是整盘寻道、容量或健康测试。",
        "預設 2GiB 檔案僅涵蓋局部位址；不是整顆磁碟的尋軌、容量或健康測試。",
        "デフォルトの 2GiB ファイルは一部のアドレス範囲しか対象にしません。ディスク全体のシーク、容量、健全性のテストではありません。"),
    "bench.tip_memory": (
        "The memory read is a sequential-throughput microbenchmark, not a RAM correctness/stability test.",
        "内存读是顺序吞吐微测试，不是RAM正确性/稳定性测试。",
        "記憶體讀取是循序吞吐量微測試，不是 RAM 正確性／穩定性測試。",
        "メモリ読み取りはシーケンシャルスループットのマイクロベンチマークであり、RAM の正確性／安定性テストではありません。"),
    "bench.tip_sustained": (
        "The 2-minute sustained CPU load is a short observation; it cannot prove thermal equilibrium or long-term stability, "
        "and 1 Hz sampling can miss short peaks.",
        "2分钟持续CPU负载是短时观察，不能证明热平衡或长期稳定性；每秒采样可能漏掉短峰值。",
        "2 分鐘持續 CPU 負載是短時間觀察，不能證明熱平衡或長期穩定性；每秒取樣可能漏掉短暫峰值。",
        "2 分間の持続 CPU 負荷は短時間の観察であり、熱平衡や長期安定性は証明できません。毎秒のサンプリングでは短いピークを見逃す場合があります。"),
    "bench.tip_no_score": (
        "No overall score. These microbenchmarks cannot be turned directly into desktop smoothness, compile speed or an OS improvement percentage.",
        "无总分。不能由这组微测试直接推导桌面流畅度、编译速度或OS提升百分比。",
        "無總分。不能由這組微測試直接推導桌面流暢度、編譯速度或 OS 提升百分比。",
        "総合スコアはありません。これらのマイクロベンチマークから、デスクトップの快適さ、コンパイル速度、OS による改善率を直接導くことはできません。"),
    "bench.tip_not_verified": (
        "Not verified automatically: GPU frame times, cold boot to usable, sleep/wake, Bluetooth, sound, external APFS drives.",
        "未自动验证：GPU帧时间、冷启动到可操作、睡眠唤醒、蓝牙、声音、外接APFS盘。",
        "未自動驗證：GPU 影格時間、冷開機到可操作、睡眠喚醒、藍牙、聲音、外接 APFS 磁碟。",
        "自動では検証していないもの：GPU フレーム時間、コールドブートから操作可能になるまで、スリープ／復帰、Bluetooth、サウンド、外付け APFS ディスク。"),
    "bench.tip_same_conditions": (
        "Comparisons need the same script/tool versions, configuration, display settings, background tasks and temperature conditions.",
        "对照需保持脚本/工具版本、配置、显示设置、背景任务及温度条件一致。",
        "對照時需保持腳本／工具版本、設定、顯示設定、背景任務及溫度條件一致。",
        "比較する際は、スクリプト／ツールのバージョン、設定、ディスプレイ設定、バックグラウンドタスク、温度条件を揃えてください。"),
    "bench.tip_fusion": (
        "If the original macOS ran on a Fusion Drive, comparing it with pure-HDD Linux is not an OS-only comparison.",
        "原macOS若是Fusion Drive，与纯HDD Linux并非仅更换OS的对照。",
        "原本的 macOS 若在 Fusion Drive 上，與純 HDD 的 Linux 並非只更換 OS 的對照。",
        "元の macOS が Fusion Drive 上で動いていた場合、HDD のみの Linux との比較は OS だけを変えた比較ではありません。"),
    "bench.boot_header": (
        "systemd record for this boot (not power-button-to-usable-desktop time):",
        "本次开机 systemd 记录（不等于按电源到桌面可操作）：",
        "本次開機 systemd 紀錄（不等於按下電源到桌面可操作的時間）：",
        "今回の起動の systemd 記録（電源ボタンからデスクトップ操作可能までの時間ではありません）："),
    "bench.not_obtained": ("not available", "未获得", "未取得", "取得できず"),
    "bench.out": (
        "Output directory: {path}",
        "输出目录：{path}",
        "輸出目錄：{path}",
        "出力ディレクトリ：{path}"),
    "bench.start_quick": ("quick validation", "快速验证", "快速驗證", "クイック検証"),
    "bench.start_full": (
        "formal test, usually about 8–15 minutes",
        "正式测试，通常约8–15分钟",
        "正式測試，通常約 8–15 分鐘",
        "正式テスト（通常 8〜15 分程度）"),
    "bench.start_info": (
        "Test directory: {target}\nMount source: {source} ({fstype})\nOutput: {out}",
        "测试目录：{target}\n挂载来源：{source} ({fstype})\n输出：{out}",
        "測試目錄：{target}\n掛載來源：{source} ({fstype})\n輸出：{out}",
        "テストディレクトリ：{target}\nマウント元：{source} ({fstype})\n出力：{out}"),
    "bench.physical_disk": (
        "Physical disk: {name} | {model} | ROTA={rota}",
        "物理盘：{name} | {model} | ROTA={rota}",
        "實體磁碟：{name} | {model} | ROTA={rota}",
        "物理ディスク：{name} | {model} | ROTA={rota}"),
    "bench.private_dir": (
        "Reads and writes only inside a private temporary directory, cleaned up at the end. Ctrl+C stops the test and keeps the results so far.",
        "只在私有临时目录读写；结束自动清理。Ctrl+C 可中止并保留已取得结果。",
        "只在私有臨時目錄讀寫；結束後自動清理。Ctrl+C 可中止並保留已取得的結果。",
        "読み書きは専用の一時ディレクトリ内だけで行い、終了時に自動で削除します。Ctrl+C で中止でき、それまでの結果は保存されます。"),
    "bench.interrupted": (
        "Stopped by the user/system; incomplete results cannot count as a complete test.",
        "用户/系统中止；不完整结果不能作为完整测试。",
        "使用者／系統中止；不完整的結果不能作為完整測試。",
        "ユーザー／システムにより中止されました。不完全な結果は完全なテストとは見なせません。"),

    # Daily browser pages and session
    "page.title.0": ("Project docs", "项目文档", "專案文件", "プロジェクト資料"),
    "page.title.1": ("API reference", "API 参考", "API 參考", "API リファレンス"),
    "page.title.2": ("Code editor", "代码编辑", "程式碼編輯", "コード編集"),
    "page.title.3": ("Build log", "构建记录", "建置紀錄", "ビルドログ"),
    "page.title.4": ("Data table", "数据表格", "資料表格", "データ表"),
    "page.title.5": ("Product notes", "产品说明", "產品說明", "製品説明"),
    "page.title.6": ("Test results", "测试结果", "測試結果", "テスト結果"),
    "page.title.7": ("Daily load monitor", "日常负载监测", "日常負載監測", "日常負荷モニター"),
    "page.heading": (
        "{title} · Fixed local page {n}/{total}",
        "{title} · 本地固定页面 {n}/{total}",
        "{title} · 本機固定頁面 {n}/{total}",
        "{title} · ローカル固定ページ {n}/{total}"),
    "page.phase": ("Phase:", "阶段：", "階段：", "フェーズ："),
    "page.preparing": ("preparing", "准备中", "準備中", "準備中"),
    "page.waiting": ("waiting for sampling", "等待采样", "等待取樣", "サンプリング待ち"),
    "page.keep_visible": (
        "Keep the test window visible. This records page callback intervals and timer lateness; these numbers are not desktop FPS or real input latency.",
        "请保持测试窗口可见。记录页面回调间隔和定时器延迟；这些数值不是桌面 FPS 或真实输入延迟。",
        "請讓測試視窗保持可見。記錄頁面回呼間隔與計時器延遲；這些數值不是桌面 FPS 或真實的輸入延遲。",
        "テストウィンドウを表示したままにしてください。ページのコールバック間隔とタイマー遅延を記録します。これらの値はデスクトップの FPS や実際の入力遅延ではありません。"),
    "page.sampling": ("sampling locally", "本地采样中", "本機取樣中", "ローカルでサンプリング中"),
    "page.no_response": ("sampling service not responding", "采样服务未响应", "取樣服務未回應", "サンプリングサービスが応答しません"),
    "browser.need_display": (
        "The daily browser test needs a logged-in, visible desktop; this script will not fall back to a headless test.",
        "日常浏览器测试需要已登录的可见桌面；本脚本不会退回 headless 测试。",
        "日常瀏覽器測試需要已登入且可見的桌面；本腳本不會退回 headless 測試。",
        "daily のブラウザテストには、ログイン済みで表示中のデスクトップが必要です。このスクリプトは headless テストに切り替えません。"),
    "browser.not_found": (
        "Chromium/Chrome not found; install Chromium, then retry daily mode.",
        "未找到 Chromium/Chrome；请先安装 Chromium 后重试日常模式。",
        "找不到 Chromium/Chrome；請先安裝 Chromium 再重試日常模式。",
        "Chromium/Chrome が見つかりません。Chromium をインストールしてから daily モードをやり直してください。"),
    "browser.no_root": (
        "The browser test must run as a normal user; --no-sandbox will not be used.",
        "浏览器测试必须由普通用户运行；不会使用 --no-sandbox。",
        "瀏覽器測試必須由一般使用者執行；不會使用 --no-sandbox。",
        "ブラウザテストは一般ユーザーで実行する必要があります。--no-sandbox は使いません。"),
    "browser.exited": (
        "Chromium exited after starting; see daily-browser.stderr.log.",
        "Chromium 启动后退出；见 daily-browser.stderr.log。",
        "Chromium 啟動後結束；請見 daily-browser.stderr.log。",
        "Chromium が起動後に終了しました。daily-browser.stderr.log を参照してください。"),
    "browser.partial": (
        "The browser only reported samples from {loaded}/{tabs} pages; this cannot count as a complete multi-tab test.",
        "浏览器只收到 {loaded}/{tabs} 个页面的采样；不能作为完整多标签测试。",
        "瀏覽器只收到 {loaded}/{tabs} 個頁面的取樣；不能作為完整的多分頁測試。",
        "ブラウザから届いたサンプルは {loaded}/{tabs} ページ分だけです。完全な複数タブテストとは見なせません。"),
    "browser.not_visible": (
        "No test page reported being visible; keep the test browser window open on a visible desktop.",
        "测试页面均未报告可见；请在可见桌面保持测试浏览器窗口打开。",
        "所有測試頁面都未回報為可見；請在可見的桌面上保持測試瀏覽器視窗開啟。",
        "表示中と報告したテストページがありません。表示中のデスクトップでテスト用ブラウザウィンドウを開いたままにしてください。"),
    "browser.note_fixture": (
        "Fixed local page scenario; it does not represent arbitrary real websites, and no remote web resources are loaded.",
        "固定本地网页场景，不代表任意真实网站；未加载远程网页资源。",
        "固定本機網頁情境，不代表任意真實網站；未載入遠端網頁資源。",
        "固定のローカルページによるシナリオで、実際の任意の Web サイトを代表するものではありません。リモートの Web リソースは読み込みません。"),
    "browser.note_raf": (
        "rAF is the callback before a page repaint; it is not the display's actual presented frame time, nor Hyprland desktop FPS.",
        "rAF 是页面重绘前回调；不是显示器实际呈现帧时间，也不是 Hyprland 桌面 FPS。",
        "rAF 是頁面重繪前的回呼；不是顯示器實際呈現的影格時間，也不是 Hyprland 桌面 FPS。",
        "rAF はページ再描画前のコールバックです。ディスプレイに実際に表示されたフレーム時間でも、Hyprland デスクトップの FPS でもありません。"),
    "browser.note_timer": (
        "timer is how late a 100ms timer fires past its scheduled interval; it is not user input latency/INP.",
        "timer 指 100ms 定时器超过计划间隔的延迟；不是用户输入延迟/INP。",
        "timer 指 100ms 計時器超過預定間隔的延遲；不是使用者輸入延遲／INP。",
        "timer は 100ms タイマーが予定間隔からどれだけ遅れたかを示します。ユーザー入力遅延／INP ではありません。"),
    "browser.note_throttling": (
        "Background pages keep the browser's default throttling; only visible periods are summarized, and batches at phase boundaries are discarded.",
        "后台页面保留浏览器默认节流；只汇总可见时段，阶段交界批次丢弃。",
        "背景頁面保留瀏覽器預設的節流；只彙總可見時段，跨階段的批次會被捨棄。",
        "バックグラウンドのページにはブラウザ既定のスロットリングが適用されたままです。集計は表示中の時間帯のみで、フェーズ境界のバッチは破棄します。"),
    "browser.note_network": (
        "The browser itself may do background networking; launch flags reduce background requests, but no firewall guarantees it is offline.",
        "浏览器自身可能执行后台联网；启动参数减少后台请求，但没有用防火墙保证离线。",
        "瀏覽器本身可能進行背景連線；啟動參數會減少背景請求，但沒有用防火牆保證離線。",
        "ブラウザ自体がバックグラウンドで通信する場合があります。起動オプションでバックグラウンド通信を減らしていますが、ファイアウォールでオフラインを保証してはいません。"),
    "browser.note_batches": (
        "Samples are reported in batches of about 1 second; an unreported final batch or batches lost to network failures cannot be recovered.",
        "采样以约1秒批次回传；未回传的末批和网络失败批次不能还原。",
        "取樣以約 1 秒的批次回傳；未回傳的最後批次與網路失敗的批次無法還原。",
        "サンプルは約 1 秒ごとのバッチで送信されます。未送信の最後のバッチや通信失敗したバッチは復元できません。"),
    "browser.not_reaped": (
        "Test browser process not yet reaped",
        "测试浏览器进程仍未回收",
        "測試瀏覽器處理程序仍未回收",
        "テスト用ブラウザのプロセスがまだ回収されていません"),
    "browser.group_alive": (
        "Test browser process group still has processes that have not exited",
        "测试浏览器进程组仍有未退出的进程",
        "測試瀏覽器處理程序群組仍有未結束的處理程序",
        "テスト用ブラウザのプロセスグループに終了していないプロセスが残っています"),
    "sim.space": (
        "The update-like load simulation needs at least 128 MiB of free space",
        "更新式负载模拟需要至少 128 MiB 可用空间",
        "類更新負載模擬需要至少 128 MiB 可用空間",
        "更新風の負荷シミュレーションには 128 MiB 以上の空き容量が必要です"),

    # Shared GitHub issue (fixed format). Table headers are pipe-separated columns.
    "issue.summary": ("Summary", "摘要", "摘要", "概要"),
    "issue.run": (
        "Omarchy Lab {version} · mode `{mode}` · status **{status}**",
        "Omarchy Lab {version} · 模式 `{mode}` · 状态 **{status}**",
        "Omarchy Lab {version} · 模式 `{mode}` · 狀態 **{status}**",
        "Omarchy Lab {version} · モード `{mode}` · 状態 **{status}**"),
    "issue.quick": (
        "quick run, not comparable with full runs",
        "快速验证，不能与正式测试比较",
        "快速驗證，不能與正式測試比較",
        "クイック実行（正式な実行とは比較不可）"),
    "issue.language": (
        "Run language: {name} · started {started}",
        "运行语言：{name} · 开始于 {started}",
        "執行語言：{name} · 開始於 {started}",
        "実行言語：{name} · 開始 {started}"),
    "issue.device": ("Device and storage", "设备与存储", "裝置與儲存", "デバイスとストレージ"),
    "issue.device_header": ("Item | Value", "项目 | 值", "項目 | 值", "項目 | 値"),
    "issue.model": ("Model", "型号", "型號", "機種"),
    "issue.cpu": ("CPU", "CPU", "CPU", "CPU"),
    "issue.memory": ("Memory", "内存", "記憶體", "メモリ"),
    "issue.kernel": ("Kernel", "内核", "核心", "カーネル"),
    "issue.omarchy": ("Omarchy version", "Omarchy 版本", "Omarchy 版本", "Omarchy のバージョン"),
    "issue.test_dir": ("Test directory", "测试目录", "測試目錄", "テストディレクトリ"),
    "issue.filesystem": ("Filesystem", "文件系统", "檔案系統", "ファイルシステム"),
    "issue.fs_value": ("{fstype} on {source}", "{fstype}，位于 {source}", "{fstype}，位於 {source}", "{source} 上の {fstype}"),
    "issue.mount_options": ("Mount options", "挂载选项", "掛載選項", "マウントオプション"),
    "issue.disk": ("Physical disk", "物理磁盘", "實體磁碟", "物理ディスク"),
    "issue.disk_unknown": (
        "unknown (not detected automatically)",
        "未知（未能自动识别）",
        "未知（無法自動識別）",
        "不明（自動検出できず）"),
    "issue.rotational": ("rotational (HDD)", "旋转介质（HDD）", "旋轉媒體（HDD）", "回転型（HDD）"),
    "issue.solid": ("non-rotational (SSD/flash)", "非旋转介质（SSD/闪存）", "非旋轉媒體（SSD／快閃記憶體）", "非回転型（SSD／フラッシュ）"),
    "issue.results": ("Results", "结果", "結果", "結果"),
    "issue.daily_header": (
        "Scenario | Median of passing tasks | Acceptance | Relative time | Mean iowait",
        "场景 | 成功任务中位数 | 验收 | 相对耗时 | iowait 均值",
        "情境 | 成功任務中位數 | 驗收 | 相對耗時 | iowait 平均",
        "シナリオ | 成功タスクの中央値 | 受け入れ判定 | 相対時間 | iowait 平均"),
    "issue.browser_header": (
        "Browser phase | Status | rAF p95 | Timer lateness p95",
        "浏览器阶段 | 状态 | rAF p95 | 定时器延迟 p95",
        "瀏覽器階段 | 狀態 | rAF p95 | 計時器延遲 p95",
        "ブラウザのフェーズ | 状態 | rAF p95 | タイマー遅延 p95"),
    "issue.rounds_header": (
        "Round | Status | End-to-end | Acceptance | Model | First text | Tools done/errors/retries",
        "轮次 | 状态 | 端到端 | 验收 | 模型 | 首文字 | 工具 完成/错误/重试",
        "輪次 | 狀態 | 端到端 | 驗收 | 模型 | 首段文字 | 工具 完成／錯誤／重試",
        "ラウンド | 状態 | エンドツーエンド | 受け入れ判定 | モデル | 最初のテキスト | ツール 完了／エラー／リトライ"),
    "issue.notes": ("Notes from the run", "运行中的提示", "執行中的提示", "実行中の注意事項"),
    "issue.none": ("No notes", "没有提示", "沒有提示", "注意事項はありません"),
    "issue.feedback": ("Feedback / questions", "反馈 / 问题", "回饋／問題", "フィードバック／質問"),
    "issue.feedback_hint": (
        "<!-- Optional: what you noticed, questions or ideas. Delete this section if you have none. -->",
        "<!-- 可选：你观察到的情况、问题或建议。没有的话可以删掉这一节。 -->",
        "<!-- 選填：你觀察到的情況、問題或建議。沒有的話可以刪掉這一節。 -->",
        "<!-- 任意：気づいたこと、質問、アイデアなど。なければこの節を削除してください。 -->"),
    "phase.programming-alone": ("Programming alone", "单独编程", "單獨寫程式", "プログラミングのみ"),
    "phase.tabs-programming": ("Browser tabs + programming", "多标签页＋编程", "多分頁＋寫程式", "複数タブ＋プログラミング"),
    "phase.tabs-programming-update-sim": (
        "Tabs + programming + simulated update",
        "多标签页＋编程＋模拟更新",
        "多分頁＋寫程式＋模擬更新",
        "複数タブ＋プログラミング＋更新シミュレーション"),
    "phase.real-update-observation": ("Real update observation", "真实更新观察", "真實更新觀察", "実際の更新の観測"),
    "phase.browser-idle": ("Browser idle", "浏览器空闲", "瀏覽器閒置", "ブラウザ待機"),

    # Guidance printed after each run
    "share.header": (
        "Share this result on GitHub (optional; nothing is uploaded automatically)",
        "在 GitHub 分享本次结果（可选；不会自动上传任何内容）",
        "在 GitHub 分享本次結果（選填；不會自動上傳任何內容）",
        "この結果を GitHub で共有する（任意。自動でアップロードされることはありません）"),
    "share.saved": (
        "A ready-to-post report in the project's fixed format is saved at: {path}",
        "已按项目的固定格式生成可直接发布的报告：{path}",
        "已依專案的固定格式產生可直接發佈的報告：{path}",
        "プロジェクト共通の形式で、そのまま投稿できるレポートを保存しました：{path}"),
    "share.languages": (
        "It is in English, followed by the same report in {name} in a collapsed section.",
        "报告以英文为准，后面附有可展开的{name}版本。",
        "報告以英文為準，後面附有可展開的{name}版本。",
        "レポートは英語が正本で、その後ろに折りたたみ式の{name}版が付いています。"),
    "share.review": (
        "Review it first: it lists your hardware, kernel and mount details. Remove anything you don't want to publish.",
        "发布前请先检查：其中包含你的硬件、内核和挂载信息，不想公开的内容请删掉。",
        "發佈前請先檢查：其中包含你的硬體、核心與掛載資訊，不想公開的內容請刪除。",
        "投稿前に内容を確認してください。ハードウェア、カーネル、マウントの情報が含まれます。公開したくない部分は削除してください。"),
    "share.open": (
        "Open a new issue (the title is filled in) and paste the whole file as the description:",
        "打开新 Issue（标题已填好），把整个文件内容粘贴为正文：",
        "開啟新 Issue（標題已填好），把整個檔案內容貼上作為內文：",
        "新しい Issue を開き（タイトルは入力済み）、ファイル全体を本文に貼り付けてください："),
    "share.copy": (
        "Copy the file to the clipboard: {command}",
        "复制文件内容到剪贴板：{command}",
        "複製檔案內容到剪貼簿：{command}",
        "ファイルをクリップボードにコピー：{command}"),
    "share.gh": (
        "Or post it with GitHub CLI: {command}",
        "或者用 GitHub CLI 直接发布：{command}",
        "或者用 GitHub CLI 直接發佈：{command}",
        "または GitHub CLI で投稿：{command}"),
    "share.attach": (
        "Optional: drag {file} into the issue to attach the full report.",
        "可选：把 {file} 拖进 Issue，附上完整报告。",
        "選填：把 {file} 拖進 Issue，附上完整報告。",
        "任意：{file} を Issue にドラッグすると、完全なレポートを添付できます。"),
    "share.failed": (
        "Could not prepare the GitHub issue text: {error}. Your results are saved.",
        "无法生成 GitHub Issue 文本：{error}。测试结果已保存。",
        "無法產生 GitHub Issue 文字：{error}。測試結果已儲存。",
        "GitHub Issue 用のテキストを作成できませんでした：{error}。結果は保存されています。"),
}
