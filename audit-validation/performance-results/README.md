# Performance review evidence

Captured on 2026-10-01 for source `70c8dc1029a01c85a6e45bcdbbc17a6a38b58c82`. Interpretation and limits are in [the performance review](../../doc/performance-review-2026-10-01.md).

| File | Workload |
| --- | --- |
| `live.json` | Complete raw-socket requests and client/shell launches. Shell processes recreate skhd's environment and verified `/` working directory. Successful and failed socket requests are recorded separately. |
| `harness.json` | Extracted validation with real owner queries; stubbed notification API and signal filter; regular-file logging; drained single-producer posting/consumption. Native harnesses use `-O3`, with a separate validator `-O0` case. |
| `focus.json` | Three seconds of same-window raw-socket focus commands on Safari, including original/final window IDs. |
| `focus.sample.txt` | macOS `sample` output taken during that focus workload. Sample counts are wall-time observations, not CPU percentages or exact stage durations. |
| `mechanisms.json` | Exact float timing expression at current and synthetic timer magnitudes, plus the extracted event worker with stubbed handlers and a nonblocking terminal wait. |
| `shell-profile.json` | Three fish startup profiles from skhd's directory. Only selected mise/config timings are retained; nested inclusive times must not be added to child times. |

Times are milliseconds unless a field explicitly ends in `_us`. Raw samples accompany aggregate values. Benchmark modes should run separately; results from different workloads/builds are not controlled speed comparisons unless the report identifies the comparison and its limits.

Reproduce with `python3 audit-validation/performance.py MODE`. Default output is a temporary directory. See the script's available modes and the report for live access requirements. Full startup profiles, arbitrary environment values, generated native sources/binaries and logging sinks stay in the temporary output directory.
