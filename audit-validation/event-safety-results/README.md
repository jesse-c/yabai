# Event safety latency checks

`before.json` measures the previous signed daemon; `after.json` measures the event
ownership/request fixes. Each contains 100 interleaved raw-socket samples per
case. Debug logging was off. Both explicit-window cases use window 103. The two
runs straddle a service restart and normal desktop activity; ID-list response
sizes differ. Treat differences as a regression check with these limits, not a
controlled general speedup.

Reproduce a read-only probe:

```sh
python3 audit-validation/event-safety-performance.py --output /tmp/socket-latency.json
```

Use `--window ID` to retain a particular tracked-window target across runs.

Correctness regressions:

```sh
python3 tests/regressions/window-validation.py
make -C tests
make -C tests TEST_FLAGS='-g -O1 -fsanitize=address,undefined'
make -C tests TEST_FLAGS='-g -O1 -fsanitize=thread,undefined'
```

The unit suite includes the actual request worker on a private temporary socket.
On October 4 all 11 tests passed with AddressSanitizer/UndefinedBehaviorSanitizer
and ThreadSanitizer, and the owner-validator/layout/query-failure fixtures passed.
Malformed requests were never sent to the live daemon.

The [ASan/UBSan output](asan-tests.txt) and [TSan/UBSan output](tsan-tests.txt)
record the final regression runs. The existing `performance.py harness` and
`mechanisms` helpers have also been adapted and checked against the new APIs.
The extracted worker handles each 10/1,000/10,000-event preloaded burst before
one terminal wait; its handlers and terminal condition wait are stubbed, so this
is mechanism evidence rather than a production throughput result.
