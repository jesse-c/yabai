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

## Queued AX window notifications

Per-window minimize, deminimize and destruction subscriptions now carry the
window ID and a generation in their observer context. Callbacks only enqueue this
value; they never dereference the subscription's former window pointer. The event
thread resolves the ID and checks the generation before using or destroying a
window. Old notifications are ignored after removal, including if a different
window has reused its numeric ID. Destruction claims also happen on the event
thread, preserving notification order.

The generation counter is not allowed to wrap and reuse identities: exhausting
all 32-bit generations terminates the daemon explicitly. Both supported targets
have 64-bit pointers, which carry the combined ID and generation.

The unit regression frees a window before dispatching its queued notifications,
then inserts a replacement with the same ID and dispatches the stale notifications
again. Missing and replaced windows must be ignored without altering the new one.

## Event queue ownership and wakeups

Event nodes now use individually owned storage. Producers append under a mutex;
the consumer detaches a FIFO batch and frees each node after its handler finishes.
The old pool could wrap and overwrite still-pending events. A condition variable
signals an empty-to-nonempty transition without accumulating semaphore credits
that force repeated empty worker passes after a burst.

Storage grows with backlog; arbitrary lifecycle events are never discarded.
Allocation failure is explicit and fatal rather than silent queue corruption.
This does not bound an indefinitely stalled consumer's total memory use. Queue
initialization and event-worker thread creation now propagate failures to startup.

Regressions hold 40,000 pending events (past the old pool's overwrite threshold),
check detached-batch ownership while new events arrive, and concurrently produce
and consume 60,000 events from three threads. They verify exact counts and order
within each producer, including wakeups after the queue empties.

## Daemon request framing and socket I/O

The socket worker now assembles complete requests with nonblocking reads before
posting an owned request to the event queue. It accepts fragmented headers/bodies,
handles interrupted reads and rejects lengths outside 2–1,048,576 bytes or payloads
without the protocol's final two NUL bytes. Request data lives independently of
the event thread's temporary arena. The client also checks message size and handles
partial/interrupted writes.

The event thread generates the response in memory. The socket worker sends it
without blocking, waking immediately through a nonblocking pipe when a response
is ready. It retains each request until the event thread publishes its response;
disconnects and shutdown cannot free a still-queued context. A maximum of 32
clients, including queued commands and response writers, are admitted. Additional
connections receive a best-effort error and are closed.

Request reception and response transmission each have a one-second deadline.
The deadline does not limit command execution or time waiting in the event queue.
Response buffering adds memory proportional to response size; the event thread
still executes commands and synchronous macOS APIs serially.

Tests use a separate temporary Unix socket, never malformed requests to the live
daemon. They cover byte-at-a-time framing, signed/oversized lengths, missing
termination, idle/partial clients, another command completing within 200 ms while
a response peer does not read, response timeout and admission saturation. All 11
unit tests pass under AddressSanitizer/UndefinedBehaviorSanitizer and ThreadSanitizer.
The owner-validator and previous layout/query-preservation regressions also pass.
The existing performance harnesses were updated for the new queue/validator APIs
and pass. The extracted worker reaches one terminal wait after draining each
preloaded burst, without the old surplus semaphore passes. Its terminal wait and
handlers are stubbed; this is not a measured desktop speedup.

## Deployment and latency

The universal arm64/x86_64 release build was signed with the existing `yabai-cert`,
verified and installed at `~/.local/bin/yabai-fork`. Its SHA-256 is
`084f1d252887102e807f2b48d41234a47f0f64307350f1bba3231cf55e52c33f`.
The signing requirement matches the previous installation. After one service
restart, the daemon answered window/configuration queries with debug logging off.
The old installation is backed up at `/tmp/yabai-event-safety/yabai-fork.before`.

A read-only socket probe interleaved 100 requests per case before and after the
restart. Median config latency was 0.217 → 0.189 ms; querying the same explicit
window ID was 0.169 → 0.186 ms. These do not establish a general speedup or a
material median regression. Tail maxima varied; ID-list response size also
changed, so that case is not a controlled comparison. This is socket completion
time, not keypress-to-screen latency. [Samples and reproduction](../audit-validation/event-safety-results/README.md)
are retained.

## Remaining work

These changes address R1/R2, B1/B2/B3, P13 and the event/message worker startup
checks from the audit. Animation bounds/cancellation, unbounded fullscreen waits,
signal arena capacity and the unexplained spontaneous space-switch swap remain
open. Directional and cross-application focus presentation latency still needs
stage-level profiling. No hide/show layout restoration was added.
