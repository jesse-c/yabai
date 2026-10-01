# Performance review — 2026-10-01

The strongest measured contributor to keyboard focus lag is the shell skhd starts for each binding. With skhd's actual environment and working directory, a trivial Yabai query through fish took **157 ms median / 478 ms p95**, compared with **11 ms median / 38 ms p95** through `sh`. Two mise activations run during fish startup. This cost is paid before Yabai receives the command.

Inside Yabai, sampled focus work is dominated by synchronous macOS activation and Accessibility calls. The fork's ten-window validation scan measured about **0.085 ms median** in an extracted function using real WindowServer owner queries. The evidence does not support prioritizing that scan as the explanation for the current focus lag.

All nine existing performance findings were reviewed. Two need material corrections: P5's flush happens after each event handler, and P6's tracked titles, frames and roles are already cached. Four additional findings are recorded as P10–P13 in [AUDIT.md](../AUDIT.md).

## Applied changes and verification

The changes below were built, signed and deployed on 2026-10-01. The remaining sections record the original review and baseline measurements. Updated evidence is in [performance-results/after](../audit-validation/performance-results/after/README.md).

- **P10:** set `EnvironmentVariables.SHELL=/bin/sh` in `~/Library/LaunchAgents/com.koekeishiya.skhd.plist` and reload the agent. All 29 active binding commands passed `/bin/sh -n`. The agent's existing PATH and the user's interactive fish configuration were preserved; the restarted process environment confirms `/bin/sh`.
- **P11:** skip the preliminary AX focused-window lookup for an explicit initial numeric window selector, `window --focus ID`, and the three query domains' `--window ID` selectors. Relative selectors and commands needing the current window retain their AX lookup. Explicit queries, initial-target focus, chained focus and missing-ID errors passed live checks.
- **P12:** subtract integer timestamps before converting elapsed durations to milliseconds in resize, gesture and Cmd-Tab timing. Regression tests cover timer magnitudes through near-`UINT64_MAX` and resize/gesture/Cmd-Tab threshold boundaries. The extracted resize simulation now produces 44 updates in three seconds at every tested magnitude, with zero incorrect threshold decisions; the old seven/thirty-day cases produced 22/12.

The universal arm64/x86_64 release build used `make install` (`-O3 -DNDEBUG`; this target builds locally). It was signed with the existing `yabai-cert` identity and installed at `~/.local/bin/yabai-fork`, then the service was restarted. Its designated requirement remains `com.asmvik.yabai` with certificate leaf `eb56cfb9d4f91ba3e3733f3602fb593fb287729a`; the installed and built binaries are byte-identical, SHA-256 `7662a64964a80eff49ddc2b7e1e9f090bd15c6056e55adcf910d4c6989054916`. All five tests pass. The release build completes without warnings; the test build reports existing macOS API deprecation warnings.

| Matching workload | Before median / p95 | After median / p95 |
| --- | ---: | ---: |
| skhd shell, no-op (25 samples) | 150.82 / 472.42 ms | 5.28 / 6.69 ms |
| skhd shell, Yabai config command (25 samples) | 157.24 / 477.61 ms | 12.01 / 13.95 ms |
| Raw socket, explicit focus of the same Safari window | 8.22 / 15.02 ms (204 samples) | 5.03 / 13.82 ms (246 samples) |

The shell measurements recreate the running skhd process's environment and `/` directory. They support removing about 145 ms from this median command path. They do not measure the full keypress-to-screen interval. The focus probe preserved Safari window 103; its sampled command path contains activation, synthetic events and AX raise, without the preliminary focused-window lookup. The focus results are successive runs across a service restart and a release rebuild, so the entire timing difference cannot be attributed to the lookup change alone. Cross-window and cross-app presentation latency remains unmeasured.

An interleaved post-change query check (80 samples each) measured `query --windows id --window ID` at 0.038 ms median and the current-focus selector at 0.107 ms median. Window counts changed across the restart, so full-query measurements should not be compared as a controlled speedup. Broad queue, lifetime, coalescing and activation rewrites remain follow-up work requiring the correctness repairs and workload evidence identified in the review.

Backups are temporarily available at `/tmp/yabai-performance-changes/skhd.plist.before` and `/tmp/yabai-performance-changes/yabai-fork.before`. The first skhd bootstrap attempt hit a launchd teardown race and restored the original agent; waiting for the old process to exit allowed the reload to succeed. Reinstalling skhd's service may regenerate its plist; preserve the shell setting when doing so.

A subsequent [layout-stability patch](space-layout-stability-2026-10-01.md) was also deployed for repeated `space --layout` resets. The running binary now has SHA-256 `77649dde102a46f029acac5459f01f8cf76cba4f441242cf91f0ffcd36002238`; the performance measurements above were captured on the earlier performance-only build.

## Setup and evidence

Source: `70c8dc1029a01c85a6e45bcdbbc17a6a38b58c82`, branch `future-proof-macos-version-checks`. Machine: arm64, macOS `27.0.1`. Running daemon: `~/.local/bin/yabai-fork`, PID 32894. Its SHA-256 matched the checkout's `bin/yabai`: `320eb6bf18f770ad29e45a4d7bdc779fbc7f5b2b2a23dae9813ec06f3e307169`.

The live daemon had `debug_output=off`, `window_animation_duration=0`, and six signals for window creation/destruction in Ghostty, Preview and Terminal. There were no focus, move, resize or title signal subscriptions. Full queries returned ten windows during the earlier probes and seventeen during the final query probe. A query can include windows serialized without a tracked AX object, so its count is not automatically the validator's candidate count.

Baseline evidence is saved in [audit-validation/performance-results](../audit-validation/performance-results/live.json). The [probe script](../audit-validation/performance.py) uses the existing socket framing with complete, bounded requests. Native harnesses extract current functions and compile them in temporary directories. During the baseline review, production source, services and shell configuration were not changed and the daemon was not restarted. A three-second focus probe repeatedly raised the already focused, visible Safari window and confirmed the same window afterward.

Socket measurements include connection, queue wait, handler execution, response transmission and receipt. Process measurements also include launching the client/shell. These are elapsed wall times, not CPU times or keypress-to-visible-focus measurements. Query cases were interleaved in a fixed randomized order, with 40 samples per socket case and 25 per process case. p95 uses the nearest rank. Sampling and benchmarks were run separately.

The earlier conversation's 535 ms CLI focus outlier was not captured with a corresponding stack trace or screen observation. Its cause remains unknown. Fish startup cannot explain that particular probe because it bypassed skhd's fish shell.

## P10. Shell startup adds substantial hotkey latency

The running skhd process had `SHELL=/opt/homebrew/bin/fish` and working directory `/`, verified from its process environment and open directory. Its PATH resolved `yabai` to `/opt/homebrew/bin/yabai`; that client communicates with the running fork. The installed skhd documentation describes execution through `$SHELL -c`; the upstream [command launcher](https://github.com/asmvik/skhd/blob/master/src/hotkey.c) forks and executes that shell for a binding.

The probes recreated skhd's environment and `/` working directory. Arbitrary environment values were kept in memory and were not saved. The first exploratory probe used the repository as its directory and measured about 460 ms for the fish query; it is superseded by the matching-directory probe below.

| Process probe | Median | p95 | Maximum |
| --- | ---: | ---: | ---: |
| Native Yabai config query | 7.56 ms | 21.02 ms | 96.20 ms |
| fish executing `:` | 150.82 ms | 472.42 ms | 1,471.95 ms |
| fish executing Yabai config query | 157.24 ms | 477.61 ms | 723.23 ms |
| fish with `--no-config`, executing `:` | 6.35 ms | 19.43 ms | 70.24 ms |
| fish with `--no-config`, executing Yabai query | 12.31 ms | 39.53 ms | 40.51 ms |
| fish with vendor mise auto-activation disabled, executing `:` | 84.54 ms | 338.95 ms | 342.12 ms |
| `sh` executing Yabai config query | 10.96 ms | 38.30 ms | 118.74 ms |

The [startup profiles](../audit-validation/performance-results/shell-profile.json) identify two activation paths:

- `/opt/homebrew/share/fish/vendor_conf.d/mise-activate.fish` invokes mise unless `MISE_FISH_AUTO_ACTIVATE=0`.
- `~/.config/fish/config.fish:172` invokes `mise activate fish | source` outside its interactive guard.

In two normal profile runs, vendor activation took about 63 ms inclusive and user activation about 67 ms inclusive. Each included a separate `mise hook-env` call of about 48 ms. A slower profile run showed vendor activation taking 244 ms. These are nested timings: inclusive and child times must not be added together. Other startup work accounts for the remaining time.

**Recommended first change:** give the skhd service `SHELL=/bin/sh`, after checking command syntax in all active bindings. The inspected active bindings use Yabai commands and shell chaining that are portable to `sh`. This changes the shell used for bindings; the user's interactive shell can remain fish. Alternatively, remove duplicate activation and arrange for both activation paths to skip noninteractive binding shells. Disabling only vendor activation leaves the user activation cost.

The measured query comparison demonstrates about 146 ms less median elapsed time with `sh` in this workload. It does not establish a 146 ms improvement for every visible focus transition; the app and macOS work still have to run. Python launching the probe is also not a complete reproduction of skhd's keyboard event tap and fork path.

## P11. Focus commands perform several synchronous macOS calls

`handle_domain_window` first calls `window_manager_focused_window`, even for a command naming an explicit target window. That obtains the front application, requests its AX focused window, then obtains the window ID through AX. A numeric target does not bypass this preliminary work. Focus then activates the target process, posts two synthetic key-window events, and performs `kAXRaiseAction`.

The [three-second sample](../audit-validation/performance-results/focus.sample.txt) contains 567 samples in the focus command branch of the event thread:

| Stage | Samples | Share of those command samples |
| --- | ---: | ---: |
| `_SLPSSetFrontProcessWithOptions` | 223 | 39% |
| Two `SLPSPostEventRecordTo` calls | 176 | 31% |
| `AXUIElementPerformAction` | 108 | 19% |
| Preliminary focused-window lookup | 59 | 10% |

Most of these stacks wait in Mach IPC. These are sampling proportions, not exact measurements of individual calls. Other threads and idle semaphore waits are excluded from this table. The same-window raw-socket probe completed 204 commands: **8.22 ms median, 15.02 ms p95, 47.94 ms maximum**. It did not switch applications or native tabs.

The current AX focused-window read can affect both same-app and cross-app commands, matching the user's reported scope. However, no stack was captured during the earlier large cross-app outlier, so the sample does not assign that outlier to a particular call.

**Implementation candidate:** resolve explicit numeric targets before performing an unnecessary current-window lookup, preserving the fallback for commands that need current focus. Directional hotkeys still require a reliable current window. Replacing that read with `focused_window_id` needs a recovery path because notifications can be delayed or lost; this fork was built to address unreliable notifications. Also profile all activation stages before removing synthetic events or the raise action, which affect focus semantics.

The source sets a one-second AX messaging timeout on the system-wide AX object. Apple's installed `AXUIElement.h` states that this sets the timeout globally for the process. That bounds an individual AX operation, not the sum of several operations and queued work. Lowering it blindly could turn normal slow responses into failures.

## P6. Filtered queries are a measured improvement

The final live query results were:

| Raw socket request | Median | p95 |
| --- | ---: | ---: |
| Config query | 0.20 ms | 0.90 ms |
| All windows, `id` | 0.78 ms | 1.20 ms |
| All windows, `id,frame` | 0.85 ms | 1.61 ms |
| All windows, `id,title` | 1.01 ms | 2.10 ms |
| All windows, `id,space,display` | 3.68 ms | 6.73 ms |
| All windows, `id,level,sub-level,opacity,is-sticky` | 4.50 ms | 8.78 ms |
| All windows, all properties | 11.36 ms | 17.96 ms |

An all-property query cost about fifteen times the ID query in this workload and occupied the same event thread used by focus commands. Frequent full-query polling is therefore a real source of avoidable contention. The script excludes failed requests from successful distributions. All 40 final focused-window queries failed while the front app was not retrievable by Yabai, so that case supplies no successful latency estimate.

**Correction to the previous audit:** tracked window title, frame, role and subrole serialization uses cached fields. `has-focus` also compares a cached ID. Their serialization does not independently read AX for each field. Live WindowServer calls supply space/display information, levels/sublevels, sticky state, opacity and shadow information; enumeration itself also talks to WindowServer. Windows without tracked AX objects use a separate serializer, including a WindowServer title-property lookup. A focused-window selector additionally performs the AX lookup described in P11.

**Recommended change:** use existing property filters in polling clients, for example `yabai -m query --windows id,frame`, when those fields are sufficient. This is supported by measured savings and avoids introducing another cache layer. No polling client configuration was changed during this review.

## P4. Validation scales, but is inexpensive at this window count

The extracted validator used the real hash table, exact current function, owner calls to the live WindowServer, and mocked management/lifecycle helpers. All ten supplied windows were treated as managed, rather than reproducing the daemon's exact eligible set. Owners were initialized from successful live queries; no destruction or retry path ran.

| Extracted validation case | Median | Maximum |
| --- | ---: | ---: |
| Ten windows, capacity 150, `-O3` | 0.085 ms | 3.52 ms |
| Ten windows, capacity 65,536, `-O3` | 0.114 ms | 2.82 ms |
| Ten windows, capacity 150, `-O0` | 0.082 ms | 0.13 ms |
| Ten windows, capacity 65,536, `-O0` | 0.198 ms | 4.02 ms |

Different build cases ran at different times; their small median differences are not evidence that `-O0` is faster. The installed daemon's optimization flags were not inferred from these measurements.

Separate owner-call batches measured about 0.011 ms for one call, 0.085 ms for ten, 0.866 ms for 100, and 7.30 ms for 500 in the `-O3` harness. Larger batches reused the same ten IDs; they do not represent 500 unique live windows or tab scaling. Owner errors and missing-window destruction can trigger substantially different work.

**Priority:** retain the scaling concern, especially for large window sets, but reduce its priority for current hotkey lag. Fix R1/R2 before narrowing validation candidates. A delayed scan still runs on the event thread and can delay a later command; the 250 ms timer is scheduling, not a per-command 250 ms sleep.

## P12. Timestamp precision degrades drag throttling

The original drag-resize handler computed:

```c
float dt = ((float) event_time - g_mouse_state.last_moved_time)
         * (1000.0f / (float)read_os_freq());
```

Both absolute nanosecond timestamps become `float` before subtraction. The [extracted-expression reproduction](../audit-validation/performance-results/mechanisms.json) shows increasing quantization as the timestamp grows:

| Synthetic timer value | Float step | Resize updates in 3 s at 1,000 input events/s |
| --- | ---: | ---: |
| One hour | 0.262 ms | 44 |
| One day | 8.389 ms | 39 |
| Seven days | 67.109 ms | 22 |
| Thirty days | 268.435 ms | 12 |
| Integer subtraction control | — | 44 |

At seven days, a true 75 ms interval became 67.109 ms and incorrectly failed the 67.67 ms test. At thirty days, simulated update intervals ranged from 13 to 269 ms. This is a reproduced timing defect, although the long-duration cases are synthetic. At the machine's current timer magnitude, the step was only 0.524 ms; this defect does not explain current keyboard focus lag.

The gesture and Cmd-Tab timing expressions use the same pattern with larger thresholds. They were source-reviewed, but the resize fixture does not establish their precise runtime effects.

**Recommended code change:** subtract unsigned integer timestamps first, then convert the small elapsed duration. Add regression cases across timer magnitudes and threshold boundaries. Preserve the intended 67.67 ms resize throttle unless its approximately 15 updates/s policy is deliberately changed.

## P13. Event bursts leave excess semaphore wakeups

Each posted event increments the semaphore. The worker drains the entire queue before calling `sem_wait`. After draining a burst, it can still have one semaphore credit for every posted event, causing repeated empty passes through autorelease-pool creation/drain and semaphore consumption.

The exact extracted worker and posting functions reproduced this. Lifecycle handlers, signals and scratch resets were stubbed. `sem_trywait` replaced the final blocking wait so the isolated process could terminate. A control preconsumed surplus credits to model one wake notification per burst; it is not a proposed production patch.

| Preloaded burst | Current worker wait calls | Current drain median | One-token control median |
| --- | ---: | ---: | ---: |
| 1,000 events | 1,001 | 0.54 ms | 0.008 ms |
| 10,000 events | 10,001 | 3.43 ms | 0.066 ms |

These are synthetic bursts below the queue pool's pending-node overwrite threshold. The measured cost is real in the extracted mechanism but small at ordinary focus input rates. A separate drained, single-producer benchmark posted and consumed 100,000 events with retain/release in about 61 ms, approximately 0.61 microseconds/event; it excludes actual handler work and producer/consumer contention.

**Priority:** consider a race-safe notification scheme when repairing B3's queue ownership and reclamation. Do not add an unproven empty-queue test around `sem_post`; a missed wakeup is a correctness failure. Measure realistic bursts before treating these synthetic ratios as an application speedup.

## Remaining original findings

| Finding | Further check | Performance implication |
| --- | --- | --- |
| P1, logging | `debug_message` flushes stdout for every daemon request. Extracted logging to a regular file took 2.09 ms for 20,000 buffered messages and 46.41 ms for 20,000 flushed command records. | Disabled in the live daemon. Regular-file costs are small here; a blocked sink can still stall the event thread. No need to prioritize an asynchronous logger for this configuration. |
| P2, repeated AX notifications | Every eligible unchanged move event still reads AX position; unchanged resize reads position and size; title events refresh the AX title. Geometry equality is checked after these reads. | Coalescing can save AX calls, not just queue nodes. Actual burst frequency and handler tails remain unmeasured. Preserve lifecycle and fullscreen ordering. |
| P3, drag frequency | Resize throttling is 67.67 ms and occurs after dequeue. Moving has a different path; ordinary mouse movement is conditional on focus-follows-mouse. | Posting alone was cheap in the synthetic benchmark. P12 is a concrete timing defect; actual AX work and event bursts need workload measurements before adding ingress coalescing. |
| P5, signals | Flush runs after each handler. Exact extracted flush with a stubbed filter measured parent fork return about 0.49 ms for a rejection and 0.31 ms for a match; dispatcher completion about 0.91 ms for rejection, action completion about 6.26 ms for a trivial match. | Child/action completion is asynchronous and is not all daemon blocking time. Current focus commands have no matching signal subscriptions. Filtering before process creation is a candidate for subscribed but rejected creation events; semantics and parent work must be preserved. |
| P7, animation capture | Capture threads are launched together, then joined by the event thread. Animation completion also holds the animation mutex across a 20 ms JankyBorders wait when its service is found. | Animations are disabled now. Capture, joins and the conditional fixed wait need measurement in an enabled animation workload. A bounded pool can increase capture setup time; do not assume a speedup. |
| P8, display-link APIs | Deprecation is not a latency measurement. | Continue to treat this as compatibility work. |
| P9, notification refresh | Extracted scheduling/rebuild with a stubbed WindowServer API produced one refresh/1,000 IDs for a queued batch, versus 1,000 refreshes/500,500 total IDs for interleaved creates. Pure insertion/enumeration took 0.11 ms versus 1.22 ms. | Worst-case repeated enumeration is reproduced. The real notification API and live launch ordering were not measured; those could dominate. Additional scheduling delay can reduce subscriptions' timeliness. |

The P5 harness measures one subscriber and a trivial action, rather than production regex/application commands. The logging sink is a normal local file. Queue handlers and the notification API are stubbed. These limits prevent ranking their synthetic completion times directly against live focus latency.

## Recommended order

1. Use a lightweight shell for skhd, or eliminate both noninteractive mise activation paths. The matching-directory comparison provides the clearest measured benefit for the user's hotkeys.
2. Reduce fields and frequency in clients that poll full window queries. This has measured daemon work savings.
3. Fix the elapsed-time calculation in resize/gesture timing, with threshold regression cases. This is a small reproduced defect with an identified correction.
4. Address the existing request/queue/lifetime correctness problems before changing event ownership or validation scope. Then instrument focus stages, queue delay and real notification bursts. Explicit-target lookup is a focused optimization candidate; aggressive focus caching needs recovery semantics.
5. Measure animation setup and notification-refresh API costs only in workloads that exercise them. Keep display-link migration as compatibility work.

## Reproduction

Run each mode separately while the relevant daemons are running:

```sh
python3 audit-validation/performance.py live
python3 audit-validation/performance.py harness
python3 audit-validation/performance.py mechanisms
python3 audit-validation/performance.py shell-profile
python3 audit-validation/performance.py focus
```

`live` and `harness` use the Yabai socket; `harness` also queries real window owners. `mechanisms` is isolated and does not require the daemon. `shell-profile` requires the running skhd shell to be fish and profiles its noninteractive startup. `focus` raises the current visible tracked window repeatedly for three seconds and runs macOS `sample`; it aborts when the focused AX window cannot be retrieved or is not visible. It does not measure screen presentation time or native-tab transitions.

Outputs go to a fresh temporary directory unless `--output DIR` is supplied. Window titles, arbitrary process environment values and full fish startup profiles are not included in the saved repository results. Live socket access and process inspection may require running outside the Codex sandbox. The current harness relies on the reviewed source signatures and macOS private APIs.

A further [space-query failure guard and investigation](space-switch-investigation-2026-10-02.md) was deployed on October 2. The running binary is now SHA-256 `706b9617aa22047b525e75c3286284c7ddfe04b3f5449301505a5e902c9895c9`; the performance measurements above precede that guard.
