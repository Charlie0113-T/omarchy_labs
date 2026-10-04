<div align="center">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/omarchy-logo-dark.svg">
  <img src="assets/omarchy-logo.svg" alt="Omarchy" width="360">
</picture>

# Omarchy Lab

**A three-mode benchmark for Linux / Omarchy: hardware, AI agent coding, and everyday multitasking**

Single `.pyz` file · Python standard library only · Runs as a normal user

![version](https://img.shields.io/badge/version-2.1-2ea44f)
![python](https://img.shields.io/badge/python-3.9%2B-3776AB?logo=python&logoColor=white)
![platform](https://img.shields.io/badge/platform-Linux%20%2F%20Omarchy-1793D1?logo=archlinux&logoColor=white)
![license](https://img.shields.io/badge/license-Apache--2.0-blue)

**English** · [简体中文](README.zh-CN.md) · [繁體中文](README.zh-TW.md) · [日本語](README.ja.md)

</div>

---

## Three modes

| Mode | What it tests | Main results |
| --- | --- | --- |
| 🧪 **Typical** `typical` | CPU, memory, disk, small-file synchronous writes, sustained load | Throughput, latency, temperature |
| 🤖 **Agent coding** `agent` | Fixing a bug, adding a feature and writing tests in a fixed project; uses Pi by default | Pass rate from independent acceptance checks, total time, tool time, model events |
| 🖥️ **Daily** `daily` | Coding alone → 8 web pages + coding → web pages + coding + simulated update load | Coding slowdown factor, page responsiveness, CPU / memory / disk wait |

## Quick start

### 1. Download

```sh
curl -L -o ~/Downloads/omarchy-lab.pyz \
  https://github.com/Charlie0113-T/omarchy_labs/raw/v2.1/omarchy-lab.pyz
```

The `.pyz` runs as is, with no unpacking. It is also a standard ZIP, so `unzip -l omarchy-lab.pyz` lists all of the source.

### 2. Run the mode you need

```sh
python3 ~/Downloads/omarchy-lab.pyz typical       # typical benchmark
python3 ~/Downloads/omarchy-lab.pyz agent --live  # agent coding (calls a model)
python3 ~/Downloads/omarchy-lab.pyz daily         # daily multitasking
```

See `python3 ~/Downloads/omarchy-lab.pyz --help` for all options.

## Requirements

- Python 3.9 or newer
- Typical mode: `fio` and `sysbench` installed (on Omarchy: `sudo pacman -S --needed fio sysbench`)
- Real agent runs: a configured [Pi](https://github.com/earendil-works/pi)
- Daily mode: a desktop session with Chromium / Chrome

> [!IMPORTANT]
> Run it as your normal user. **Do not put `sudo` in front of the command.**

## 🌐 Language

Prompts, `--help`, errors and reports are available in English, 简体中文, 繁體中文 and 日本語.

- Run it in a terminal without `--lang` and it asks once at start. Press Enter to keep your system language.
- `--lang en`, `zh-CN`, `zh-TW` or `ja` picks one and skips the question. `--lang auto` follows your system locale.
- Set `OMARCHY_LAB_LANG=ja` (for example) to use a language for every run.

```sh
python3 ~/Downloads/omarchy-lab.pyz daily --lang ja
```

The workload is the same in every language. The agent's task prompt and the body of the browser test pages never change, and JSON keys and status codes stay in English, so results from runs in different languages can be compared.

## 📮 Share your result

After every run, the tool saves `issue.md` in the report directory: a ready-to-post GitHub issue in this project's fixed format (Summary, Device and storage, Results, Notes, Feedback). It prints the steps to post it, in the language you chose.

- The report is in English first, so all shared results read the same. If you ran the test in another language, the same report follows in that language in a collapsed section.
- Nothing is uploaded automatically. Review the file before posting: it lists your hardware, kernel and mount details. Your home directory is shown as `~`.
- Post it as a [new test report issue](https://github.com/Charlie0113-T/omarchy_labs/issues/new?template=test-report.md), or with `gh issue create -R Charlie0113-T/omarchy_labs --title "…" --body-file issue.md`.

## 🤖 Agent mode

Agent mode first runs a fixed local toolchain replay, then the real task.

- A failure or timeout never counts as a fast result. Acceptance doesn't depend on the agent saying it finished.
- Total time includes model and network waits, so it is not a pure hardware score.
- Without `--live`, only the local replay runs and no model is called.

> [!WARNING]
> By default the real task runs one round of up to ten minutes and **uses your model quota**.

For a formal comparison, pin the model and run three rounds:

```sh
python3 ~/Downloads/omarchy-lab.pyz agent --live --model 'your-full-model-id' --rounds 3
```

## 🖥️ Daily mode

Coding in daily mode uses the fixed replay and never calls a model. The update load is simulated by default with repeated unpacking and disk syncs.

To observe a **real system update + browser + coding** instead:

```sh
python3 ~/Downloads/omarchy-lab.pyz daily --observe-update --seconds 600
```

When prompted, start the update in another terminal using Omarchy's own process (see the [Omarchy Manual](https://omarchy.org/manual/updates/)). The script only observes; it never runs the update for you.

> [!TIP]
> Keep the test dashboard visible during the daily run. Don't minimize it.

## 📊 Results

Results are printed when the run ends and saved under `~/omarchy-lab/<timestamp>/`:

```text
~/omarchy-lab/<timestamp>/
├── report.txt     # human-readable report
├── report.en.txt  # English copy, when you ran in another language
├── issue.md       # ready-to-post GitHub issue
├── results.json   # structured results
└── samples.csv    # per-second samples
```

| Exit code | Meaning |
| :---: | --- |
| `0` | Run completed and all tasks passed |
| `1` | Run incomplete or a task failed |
| `2` | Bad arguments or missing prerequisites |

## 🛠️ Build from source

The source lives in [`src/`](src/). To rebuild `omarchy-lab.pyz` and run the tests:

```sh
python3 scripts/build.py
python3 -m unittest discover -s tests
```

User-facing text is kept in [`src/i18n.py`](src/i18n.py), one entry per message with all four languages side by side. The tests check that every message exists in every language with the same placeholders.

## License

Released under the [Apache License 2.0](LICENSE).

The Omarchy logo comes from [omacom/omarchy](https://github.com/omacom/omarchy) (MIT license). This is a community tool and is not affiliated with Omarchy.
