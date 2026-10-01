# Preserve window order when reapplying a space layout

## Finding

The user reports preexisting position swaps after switching away from a space and returning. The inspected `~/.config/yabai/yabairc` registers six creation/destruction signals for Ghostty, Preview and Terminal, each executing `yabai -m space --layout bsp`. The [Ghostty workaround documentation](https://ghostty.org/docs/help/macos-tiling-wms#yabai) recommends this form for native tabs; the user's configuration extends it to the other two apps.

The command uses the space active when its asynchronous action executes. `space_manager_set_layout_for_space` previously called `view_clear` unconditionally, even if the selected space already used BSP. `view_clear` destroys the existing tree nodes and managed-window associations. Reconciliation then adds windows using WindowServer enumeration and normal insertion rules; the previous positions, split ratios and zoom can be lost. A background creation/destruction event can thus rebuild the foreground space.

This is a source-confirmed reset path and a plausible contributor to the reported swaps. The user's intermittent space-switch incident was not captured live, and the user was unsure which applications participated. The separate space-switch reconciliation and focus-owner validation paths remain relevant if swaps continue.

## Change

`space_manager_set_layout_for_space` now clears the tree only when the requested layout type differs. Repeating BSP or stack still runs window reconciliation, allowing newly added or removed windows to be handled while retaining the nodes of unchanged windows. Switching layout types retains the previous rebuild behavior. No signal configuration changes were needed. The CLI documentation describes the repeated-layout behavior; this patch applies to `space --layout`, the command used by the signals.

## Verification and deployment

[Captured results](../audit-validation/space-layout-results/README.md) and [the reproduction script](../audit-validation/space-layout.py) accompany the change. The isolated fixture extracts the actual setter and `view_clear`, uses the real view/node definitions, and stubs WindowServer reconciliation, geometry and managed-window cleanup. Its reconciliation stub enumerates B,A to demonstrate the loss of the original A,B order following a clear.

- Before: repeating BSP removed both managed nodes and lost the original order/ratio/zoom state.
- After: repeating BSP preserved order, ratio, zoom and insertion state with zero removed nodes, while still invoking reconciliation.
- Genuine BSP-to-stack and stack-to-float changes still clear. Repeated stack continues to reconcile.
- The universal release build and all five existing/regression unit tests pass. Code signing verifies with the existing `yabai-cert` requirement.
- After deployment, three live repeated BSP commands on space index 2 preserved both managed windows' cached frames, split children and stack indexes exactly. This checks the repeated command, rather than an actual switch-away/return incident.

Installed binary: `~/.local/bin/yabai-fork`, SHA-256 `77649dde102a46f029acac5459f01f8cf76cba4f441242cf91f0ffcd36002238`, identical to the signed checkout build. The service is running and queries succeed. The required restart rebuilt layouts once; subsequent repeated layout commands retained the checked arrangement.

The previous performance-only installation is backed up temporarily at `/tmp/yabai-performance-changes/yabai-fork.performance-before-space-fix`. The pre-performance installation remains at `/tmp/yabai-performance-changes/yabai-fork.before`. Temporary backups may be removed by macOS.

## Follow-up — 2026-10-02

The user reported another swap. [Further tracing](space-switch-investigation-2026-10-02.md) identified a hide/show placement change and deliberate swap commands, but did not capture the earlier unexplained incident. A separate query-failure guard was deployed; the hashes and live results above describe the earlier layout-only patch.
