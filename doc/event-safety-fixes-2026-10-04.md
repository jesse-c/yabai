# Event safety fixes — 2026-10-04

## Window-owner validation

Owner-query retry state now belongs to each tracked window. A retry scans only
windows whose own previous query failed; a newly discovered window or another
window's first error cannot inherit a scan's retry status.

A failed owner query preserves the window, including on retry. Only a successful
query reporting a different owner removes it through this recovery path. A
persistent failure does not schedule an endless retry loop; a later focus change
can initiate another check. Normal destruction notifications remain responsible
for removing closed windows when owner queries are unavailable.

`python3 tests/regressions/window-validation.py` extracts the actual validator,
uses the real hash table and runs under AddressSanitizer/UndefinedBehaviorSanitizer.
It covers independent retries, newly discovered windows, persistent errors,
focused-window exclusion and successful owner mismatches. It passed on October 4.
