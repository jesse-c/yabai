# Repeated layout-setting regression — 2026-10-01

See [the layout-stability report](../../doc/space-layout-stability-2026-10-01.md).

- `before.json`: committed setter and actual `view_clear`, with stubbed reconciliation/geometry/cleanup. Repeating BSP removes both existing windows and loses tree state.
- `after.json`: patched setter with the same fixture. Repeating BSP preserves order, ratio, zoom and insertion state; genuine layout transitions still clear and repeated stack still reconciles.
- `live.json`: the deployed signed build preserves both managed windows' frames and split children after three repeated BSP commands on space index 2.

Reproduce the isolated tests with `python3 audit-validation/space-layout.py --baseline` and `python3 audit-validation/space-layout.py`. The fixture explicitly models reconciliation enumeration in reverse order; it does not reproduce an OS space-switch incident. Native generated sources/binaries stay in temporary directories.
