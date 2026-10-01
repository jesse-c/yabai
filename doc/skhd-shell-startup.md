# Avoid shell startup overhead in skhd bindings

skhd executes bindings with `$SHELL -c`. On the inspected machine this launched fish, whose vendor and user configuration each activated mise. Recreating the running agent's environment and `/` working directory measured a Yabai config command at 157 ms median / 478 ms p95. After selecting `/bin/sh` for the agent, the same workload measured 12 ms median / 14 ms p95. These are shell-and-command completion times, not keypress-to-screen latency.

Set `EnvironmentVariables.SHELL` to `/bin/sh` in `~/Library/LaunchAgents/com.koekeishiya.skhd.plist`. Preserve its existing PATH. Check that active binding commands use portable shell syntax before applying this setting. All 29 inspected commands passed `/bin/sh -n`.

The helper stages a reviewable plist or applies it with a backup and service reload:

```sh
python3 scripts/set-skhd-shell.py --output /tmp/skhd.plist
plutil -lint /tmp/skhd.plist
python3 scripts/set-skhd-shell.py --apply
```

The apply mode waits for the old process to exit and retries launchd bootstrap while teardown completes. Regenerating skhd's service can overwrite the setting; apply it again afterward. The user's interactive shell is configured independently.

Measurements and reproduction modes are in `audit-validation/performance.py` and `audit-validation/performance-results`. The live mode reads the actual skhd process environment without saving arbitrary environment values.
