# Applied performance changes — 2026-10-01

Post-change evidence for the source and service updates described in [the measured review](../../../doc/performance-review-2026-10-01.md#applied-changes-and-verification). The parent directory retains the baseline results.

- `live.json`: running skhd confirmed to use `/bin/sh`; 25 launches per process case and 40 socket requests per case.
- `focus.json` and `focus.sample.txt`: three-second repeat of the same visible Safari-window focus workload, original/final ID 103.
- `mechanisms.json`: extracted corrected elapsed-time expression and the unchanged burst-wakeup reproduction; native fixtures remain in the temporary directory.
- `verification.json`: explicit queries in all three domains, initial/chained focus, missing-ID errors, installed binary hash, service shell and interleaved query timings. Original/final focus ID 868 during this separate check. The directional error probe was conditional on exactly one visible window and did not run; directional classification is covered by the regression tests.

Five unit tests pass (`make -C tests`); the release build (`make install`) and signature verification pass. These are command-completion measurements, not keypress-to-screen timings. Service restarts, release rebuilding and changing window counts limit causal comparisons; see the report.
