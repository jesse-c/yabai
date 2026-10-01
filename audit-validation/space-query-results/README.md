# Space-query failure guard and live investigation — 2026-10-02

See [the investigation report](../../doc/space-switch-investigation-2026-10-02.md).

- `before.json` / `after.json`: extracted pre-guard and patched reconcilers with the same controlled query fixture. WindowServer, node removal, insertion checks and flushing are stubbed; real CoreFoundation arrays and the actual new query implementation are used. Modes: 0 = successful empty array, 1 = failed list copy, 2 = failed query creation, 3 = failed iterator creation, 4 = normal two-window result, 5 = all windows filtered out as minimized. The baseline reconciler comes from `70c8dc1`; its query stub deliberately discards the new success status to supply failure/empty results. This tests destructive reconciliation, not live fault injection or the old query/iterator failure behavior.
- `first-trace.json`: 60-second pre-guard observation; Safari hide/show changed placement, with 10 space-change events.
- `second-trace.json`: five-minute pre-guard observation; both captured position swaps coincide with explicit `window --swap` commands, with 16 space-change events. These observations do not resolve the earlier reported spontaneous swap.
- `live-verification.json`: signed guard deployment, healthy daemon, debug restored off, and five tracked nonfloating windows retaining cached geometry/metadata across three repeated BSP commands. This count includes hidden/unmanaged windows; it is not a count of five BSP nodes.

Reproduce the isolated fixtures with `python3 audit-validation/space-query-failure.py [--baseline]`. Record another live incident with `python3 audit-validation/space-switch-trace.py --duration 300`. Outputs default to a temporary directory; live socket/process access may require running outside the sandbox. Titles and arbitrary environment values are omitted from the saved traces.
