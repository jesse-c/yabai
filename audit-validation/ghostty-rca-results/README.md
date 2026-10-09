# Ghostty window-size RCA capture

- `trace.jsonl`: sampled yabai window state, actual CoreGraphics bounds, and daemon events during the reproduction.
- `rca-events.txt`: relevant lines from the instrumented daemon log, including requested frames, Accessibility return codes, and window lifecycle events. Original log line numbers are preserved.
- `rca-snapshots.json`: reduced snapshots around the quarter-size reproduction.
- `show-visible-only-regression.jsonl`: the first membership-filter attempt incorrectly excluded Ghostty while it was still being unhidden; Emacs stayed full width.
- `space-membership-live.jsonl`: the corrected show path queried space membership including hidden windows. Two live hide/show cycles ended with Emacs and Ghostty in half-screen tiles.

The temporary diagnostic build was based on `786464a` (before the delayed frame-reconciliation workaround). On show, yabai tiled Ghostty windows 823 and 564. Window 823's AX frame requests returned `-25202` (`kAXErrorInvalidUIElement`), while window 564 successfully resized to a quarter-screen slot. The working signed build was restored after capture; these files contain no diagnostic source changes or binary.
