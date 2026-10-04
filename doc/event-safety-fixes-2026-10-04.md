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
