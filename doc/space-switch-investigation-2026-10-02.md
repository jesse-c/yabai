# Space-switch rearrangement investigation — 2026-10-02

The user reports another swap after the repeated-layout patch. The running daemon's hash matched the deployed patch, `77649dde102a46f029acac5459f01f8cf76cba4f441242cf91f0ffcd36002238`. Two live traces recorded window geometry, split metadata, visibility and selected events, with titles omitted. They contain 26 space-change events in total.

## Observations

The first trace recorded Safari being hidden and then shown. On hide, `APPLICATION_HIDDEN` removes Safari windows from their BSP trees and collapses the remaining layout. On show, `APPLICATION_VISIBLE` inserts them using an insertion point rather than restoring their original nodes. In this trace Safari 1414 changed from the full-height right position to the lower-left position. The user confirmed using Hide during this test. Restoring exact positions across application hide/show remains separate behavior to implement if requested.

The second trace captured swaps at 28.187 seconds and 29.280 seconds. Both followed explicit daemon commands: `window --swap south`, then `window --swap east`. The user said they thought they deliberately performed some swaps. Other recorded space switches did not produce persistent position changes in the sampled snapshots. The original spontaneous swap reported before the second trace is still unexplained; neither trace proves its cause or excludes a short transition between 200 ms samples.

Debug logging was enabled only for each trace and restored to `off`. [Evidence and reproduction](../audit-validation/space-query-results/README.md) accompany the investigation. New debug messages identify additions/removals during space reconciliation and failed-query preservation, so another incident can be attributed more directly.

## Query-failure guard

A source-confirmed destructive edge case exists independently of those observations. Space reconciliation initialized the window count to zero and treated a failed window-list query as an empty space. It could remove every existing BSP node, allowing a later successful query to reinsert windows in a different order. The list builder also did not check failed query/iterator creation before using their results.

The query implementation now reports success separately from its list/count. It initializes the public count to zero, checks list/query/iterator results and releases successfully created objects. Reconciliation preserves the existing tree on failure. Successful empty arrays and successful results filtered down to zero still reconcile as empty spaces. Existing list callers retain their pointer/count interface.

Extracted regressions cover failed list copy, failed query creation, failed iterator creation, successful empty arrays, successful filtered-empty results, normal results and floating layouts. The pre-guard reconciler removes both fixture nodes on a query failure; the patched reconciler removes none and performs no reconciliation/flush. These faults were injected into isolated stubs, never the live daemon. This is a validated guard, not proof that a query error caused the user's reported incident.

The universal release build, five unit tests and layout/query regression fixtures pass. The signed build was deployed at `~/.local/bin/yabai-fork`, SHA-256 `706b9617aa22047b525e75c3286284c7ddfe04b3f5449301505a5e902c9895c9`, byte-identical to the checkout build. The service is healthy. Three repeated BSP commands preserved all five checked tracked nonfloating windows' cached frames and metadata; several were hidden and unmanaged, so this is not a five-node BSP test. The required restart rebuilt layouts once.

The previous signed installation is backed up temporarily at `/tmp/yabai-space-switch-investigation/yabai-fork.before-query-guard`. The remaining original-stack validator retry/lifetime issues in `AUDIT.md` have not been fixed by this guard. No changes were made to the user's hide/show policy or swap bindings.
