#!/usr/bin/env python3
"""Set skhd's binding shell without changing the user's interactive shell.

By default, write a staged LaunchAgent to a supplied output path. --apply backs
up and replaces the existing agent, waits for skhd to exit, then reloads it.
"""
import argparse
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import time


def bootstrap_agent(agent):
    for _ in range(10):
        result = subprocess.run(['launchctl', 'bootstrap', f'gui/{os.getuid()}', str(agent)], capture_output=True)
        if result.returncode == 0:
            return
        time.sleep(.2)
    raise RuntimeError(result.stderr.decode().strip())


def reload_agent(agent, old_pid):
    subprocess.run(['launchctl', 'bootout', f'gui/{os.getuid()}/com.koekeishiya.skhd'], check=True)
    deadline = time.monotonic() + 10
    while old_pid:
        try:
            os.kill(old_pid, 0)
        except ProcessLookupError:
            break
        if time.monotonic() >= deadline:
            raise RuntimeError('Old skhd process did not exit')
        time.sleep(.1)
    # launchd may still be completing teardown after the process exits.
    bootstrap_agent(agent)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--agent', type=Path, default=Path.home() / 'Library/LaunchAgents/com.koekeishiya.skhd.plist')
    parser.add_argument('--output', type=Path, help='Write a staged plist without reloading the service')
    parser.add_argument('--apply', action='store_true', help='Back up, replace and reload the LaunchAgent')
    args = parser.parse_args()
    if bool(args.output) == args.apply:
        parser.error('Choose exactly one of --output or --apply')
    original = args.agent.read_bytes()
    data = plistlib.loads(original)
    if data.get('Label') != 'com.koekeishiya.skhd':
        parser.error('Expected the com.koekeishiya.skhd LaunchAgent')
    data.setdefault('EnvironmentVariables', {})['SHELL'] = '/bin/sh'
    staged = plistlib.dumps(data, sort_keys=False)
    if args.output:
        args.output.write_bytes(staged)
        print(args.output)
        return
    backup = args.agent.with_name(args.agent.name + '.before-shell-' + time.strftime('%Y%m%d-%H%M%S'))
    if backup.exists():
        raise FileExistsError(backup)
    shutil.copy2(args.agent, backup)
    pid_result = subprocess.run(['pgrep', '-x', 'skhd'], capture_output=True, text=True)
    pids = pid_result.stdout.split()
    if len(pids) > 1:
        raise RuntimeError('Multiple skhd processes found; inspect the service before reloading')
    old_pid = int(pids[0]) if pids else None
    temporary = args.agent.with_name(args.agent.name + '.new')
    temporary.write_bytes(staged)
    shutil.copymode(args.agent, temporary)
    os.replace(temporary, args.agent)
    try:
        reload_agent(args.agent, old_pid)
    except Exception:
        args.agent.write_bytes(original)
        loaded = subprocess.run(['launchctl', 'print', f'gui/{os.getuid()}/com.koekeishiya.skhd'], capture_output=True)
        if loaded.returncode:
            bootstrap_agent(args.agent)
        raise
    print(f'skhd uses /bin/sh; backup: {backup}')


if __name__ == '__main__':
    main()
