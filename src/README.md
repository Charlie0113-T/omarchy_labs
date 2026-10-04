# Omarchy Lab 2.1

Three test modes for Linux / Omarchy. Implemented using the Python standard library and run as a regular user.

Download `omarchy-lab.pyz` and run it directly—no extraction required. It is also a standard ZIP archive, so you can extract it to inspect all the source code.

## Run with one command

```sh
python3 ~/Downloads/omarchy-lab.pyz typical
python3 ~/Downloads/omarchy-lab.pyz agent --live
python3 ~/Downloads/omarchy-lab.pyz daily
```

- `typical`: Runs the existing CPU, memory, disk, small-file fsync, data verification, and sustained-load tests. Requires fio (Flexible I/O Tester) and sysbench to be installed.
- `agent --live`: Runs three fixed local coding workflow replays, followed by one real Pi coding task. Each round has a default timeout of 600 seconds.
- `daily`: Programming alone → 8 local browser tabs + programming → multiple tabs + programming + a simulated update disk workload. Each phase lasts approximately 60 seconds, with additional time for baseline measurements and initialization.

Without `--live`, agent mode only runs the fixed local replay and does not call a model.

Language: `--lang en|zh-CN|zh-TW|ja|auto`, or the `OMARCHY_LAB_LANG` environment variable. Without either, a terminal run asks at start. Only the text you read changes; the workload is identical in every language.

Live agent runs use your configured Pi account and model, consuming quota or potentially incurring charges. The temporary working directory (`cwd`) is not a permission sandbox.

`daily` requires an active desktop session and Chromium/Chrome. Keep the test dashboard tab in the new browser window visible; do not minimize it.

The script does not automatically install dependencies, run system updates, delete existing projects, or write to raw disk devices.

To install the two tools required for typical mode:

```sh
sudo pacman -S --needed fio sysbench
```

Do not run the test script with `sudo`. If dependency installation fails, follow Omarchy’s official update procedure first. Do not refresh only the package database to force installation.

## Making rigorous comparisons

1. Connect to AC power. Keep the display refresh rate, resolution, and power settings fixed, and use the same filesystem and working directory. Close unrelated tasks and let the machine return to a comparable temperature.
2. Keep the script version, Pi version, provider, full model ID, thinking setting, and extensions fixed. Three live agent rounds are recommended:

   ```sh
   python3 ~/Downloads/omarchy-lab.pyz agent --live --model 'YOUR_FULL_MODEL_ID' --rounds 3
   ```

   If you specify `--provider`, you must also specify `--model`. Set the thinking level using a model suffix supported by Pi, or set it explicitly in a custom command.
3. When comparing two configurations, alternate their running order and repeat the complete mode at least three times. Compare medians, individual runs, and acceptance pass rates, rather than only the fastest run.
4. Interpret CPU/disk benchmarks, local toolchain replay, and live agent end-to-end performance separately. Model service conditions, network conditions, prompt caching, and retries can affect live agent results.
5. Do not compare quick-mode results with full-mode results. Comparing macOS on the original Fusion Drive with Linux on a pure HDD changes both the operating system and storage configuration; differences cannot be attributed to either factor alone.

## What agent mode measures

Each round recreates the same small Python project: 162 files and 30,000 rows of fixed input data. The task includes fixing a parsing bug, implementing aggregation/filtering/quantile features, and adding a CLI and tests.

The test harness validates results using separately retained acceptance logic. The agent’s own claim that “tests passed” does not determine the final result.

The fixed replay includes reading and searching files, applying the same patch, compiling Python bytecode, running unit tests, and processing data through the CLI.

This is not a C/Rust compilation benchmark, a large JavaScript build benchmark, or an assessment covering all software development tasks. A single small task serves only as a reproducible benchmark.

Newly created files may still be in the page cache. The script does not clear system caches or claim to measure cold-start disk performance. Project generation time is recorded separately from replay task duration.

For live runs, Pi JSON events are used to record total duration, time to first model delta / first text output, execution intervals for completed tool calls, tool errors, retries, and usage from the final message.

The first-delta timestamp records when the client receives the event, not the exact server-side time to first token.

Tool duration is not CPU time. The remaining elapsed time is not directly measured “cloud inference time.”

Usage is counted only from final assistant messages to avoid double-counting cumulative streaming events. It may exclude some retries or context-compaction activity; cost fields are not billing records.

Missing events or insufficient data are reported as unobserved, rather than filled in with zero. Timeouts, process failures, and acceptance failures are never counted as successful tasks.

Custom adapters:

```sh
--agent-command 'your non-interactive command and arguments'
```

The prompt is appended as the final argument. The command is executed without a shell.

Agents that do not emit Pi-format events can still have their code checked and total runtime measured, but Pi-specific event metrics will be unavailable.

Raw logs may contain model responses, paths, or extension output. Review them before sharing reports.

## Daily mode and real updates

`daily` uses fixed local web pages to avoid public-network variability. The browser’s default background-tab throttling remains enabled.

It measures requestAnimationFrame (rAF) callback intervals and timer delays on visible pages—not system FPS, mouse input latency, or INP.

Background-page samples are not treated as foreground samples. Batches spanning phase boundaries are deliberately discarded to prevent samples from being assigned to the wrong phase. Missing or insufficient samples are flagged.

In full mode, foreground samples must cover at least 60% of each phase’s duration; in quick mode, the requirement is 25%. This is a sampling completeness requirement, not a threshold for acceptable smoothness.

The daily programming task uses the same fixed local toolchain replay as agent mode and does not consume model quota.

The “simulated update” repeatedly extracts a fixed archive and performs fsync operations inside a temporary directory. It does not invoke a package manager, upgrade packages, or reboot the system.

To observe a real update:

```sh
python3 ~/Downloads/omarchy-lab.pyz daily --observe-update --seconds 600
```

When prompted, start the update in another terminal using Omarchy’s official procedure. The script observes the browser + local programming workload and records package versions before and after the observation period.

The update may outlast the observation window. The window’s duration is not treated as the total update time. Pressing Ctrl+C ends observation without stopping the update running in the other terminal.

Real updates change software versions and cannot be repeated under identical conditions. They are therefore recorded as separate observations and must not be mixed into reproducible benchmark results.

## Output and stopping

When the run ends, the terminal prints a report. By default, `~/omarchy-lab/<timestamp>/` stores `report.txt`, `results.json`, `samples.csv`, and raw records for each mode.

Temporary test projects are created in separate new directories under `--work-dir`, which defaults to your home directory, and are cleaned up on exit. Source code modified by a live agent is retained with the corresponding report.

To compare local work on an HDD versus an SSD, point `--work-dir` to a regular directory on the relevant drive.

Typical mode requires at least 8 GiB of free space. Agent and daily modes require at least 1 GiB. Output logs consume additional space.

Ctrl+C saves a partial report and stops the current test processes. Testing stops when the temperature reaches the default limit of 90°C. Unavailable temperature sensors are explicitly reported.

The harness reaps the simulated-update process after it is stopped. The script never terminates a real update launched separately by the user.

Exit codes:

- `0`: The run completed and its tasks passed.
- `1`: The run was incomplete or one or more tasks failed.
- `2`: Invalid arguments or unmet prerequisites.

There is no universal pass threshold for performance. Passing the acceptance checks does not mean the hardware is healthy or that every workload will run smoothly.

## Validation scope

Controlled test projects have been used to validate acceptance checks, fixed replay, Pi event parsing, failure/interruption records, subprocess cleanup, and the packaged entry point.

Validation used locally simulated agent events without calling real models. The current build environment does not have Chromium available in a graphical desktop session, so real-browser end-to-end behavior and the user’s Pi/provider configuration still require confirmation during the first live run.

Protocol references:

- https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/cli.md
- https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/json.md
- https://omarchy.org/manual/updates/