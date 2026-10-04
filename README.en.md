<div align="center">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/omarchy-logo-dark.svg">
  <img src="assets/omarchy-logo.svg" alt="Omarchy" width="360">
</picture>

# Omarchy Lab

**A three-mode benchmark for Linux / Omarchy: hardware, AI agent coding, and everyday multitasking**

Single `.pyz` file · Python standard library only · Runs as a normal user

![version](https://img.shields.io/badge/version-2.0-2ea44f)
![python](https://img.shields.io/badge/python-3-3776AB?logo=python&logoColor=white)
![platform](https://img.shields.io/badge/platform-Linux%20%2F%20Omarchy-1793D1?logo=archlinux&logoColor=white)
![license](https://img.shields.io/badge/license-Apache--2.0-blue)

[简体中文](README.md) · **English**

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
  https://github.com/Charlie0113-T/omarchy_labs/raw/v2.0/omarchy-lab.pyz
```

The `.pyz` runs as is, with no unpacking. It is also a standard ZIP, so `unzip -l omarchy-lab.pyz` shows all of the source.

### 2. Run the mode you need

```sh
python3 ~/Downloads/omarchy-lab.pyz typical       # typical benchmark
python3 ~/Downloads/omarchy-lab.pyz agent --live  # agent coding (calls a model)
python3 ~/Downloads/omarchy-lab.pyz daily         # daily multitasking
```

See `python3 ~/Downloads/omarchy-lab.pyz --help` for all options.

## Requirements

- Typical mode: `fio` and `sysbench` installed (on Omarchy: `sudo pacman -S --needed fio sysbench`)
- Real agent runs: a configured [Pi](https://github.com/earendil-works/pi)
- Daily mode: a desktop session with Chromium / Chrome

> [!IMPORTANT]
> Run it as your normal user. **Do not put `sudo` in front of the command.**

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
├── results.json   # structured results
└── samples.csv    # per-second samples
```

| Exit code | Meaning |
| :---: | --- |
| `0` | Run completed and all tasks passed |
| `1` | Run incomplete or a task failed |
| `2` | Bad arguments or missing prerequisites |

> [!NOTE]
> The report text and `--help` option descriptions are currently in Chinese.

## License

Released under the [Apache License 2.0](LICENSE).

The Omarchy logo comes from [omacom/omarchy](https://github.com/omacom/omarchy) (MIT license). This is a community tool and is not affiliated with Omarchy.
