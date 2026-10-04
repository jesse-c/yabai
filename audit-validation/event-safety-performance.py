#!/usr/bin/env python3
"""Read-only socket latency probe for the event/request ownership changes."""
import argparse
import hashlib
import json
from pathlib import Path
import random
import time

from performance import request, summary

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--output", type=Path, required=True)
parser.add_argument("--window", type=int, help="Use the same tracked window as the baseline")
args = parser.parse_args()
window = args.window or json.loads(request("query", "--windows", "id", "--window")[1])["id"]
cases = {
    "config": ("config", "debug_output"),
    "explicit_window_id": ("query", "--windows", "id", "--window", str(window)),
    "all_ids": ("query", "--windows", "id"),
}
samples = {name: [] for name in cases}
response_sizes = {}
for values in cases.values():
    request(*values)
rng = random.Random(20261004)
for _ in range(100):
    order = list(cases)
    rng.shuffle(order)
    for name in order:
        elapsed, response = request(*cases[name])
        samples[name].append(elapsed)
        response_sizes[name] = len(response)
    time.sleep(.002)
binary = Path.home() / ".local/bin/yabai-fork"
result = {
    "observed_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    "daemon_binary_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
    "debug_output": request("config", "debug_output")[1].decode().strip(),
    "window_id": window,
    "socket": {name: {**summary(values), "response_bytes": response_sizes[name]}
               for name, values in samples.items()},
}
args.output.parent.mkdir(parents=True, exist_ok=True)
args.output.write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps({"window_id": window,
                  "socket": {name: {key: value for key, value in values.items()
                                     if key != "samples_ms"}
                             for name, values in result["socket"].items()}}, indent=2))
