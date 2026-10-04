#!/usr/bin/env python3
"""Run the actual validator against deterministic owner-query failures."""
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]


def extract(path, signature):
    source = (ROOT / path).read_text()
    start = source.index(signature + "\n{")
    end = source.index("{", start) + 1
    depth = 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end]


source = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define HASHTABLE_IMPLEMENTATION
#include "misc/hashtable.h"
#define debug(...) ((void)0)
typedef int CGError;
enum { kCGErrorSuccess = 0 };
struct application { int connection; } app = { 42 };
struct window {
    uint32_t id;
    uint32_t *volatile id_ptr;
    struct application *application;
    bool owner_query_retry_pending;
};
struct { struct table window; } g_window_manager;
int g_connection;
static int calls[4], failures[4], owners[4], retries, destroyed;
static unsigned long hash(void *key) { return *(uint32_t *)key; }
static int cmp(void *a, void *b) { return *(uint32_t *)a == *(uint32_t *)b; }
static struct window *window_manager_find_window(void *wm, uint32_t id) {
    return table_find(&g_window_manager.window, &id);
}
static bool window_manager_find_managed_window(void *wm, struct window *w) { return true; }
static CGError SLSGetWindowOwner(int connection, uint32_t id, int *owner) {
    ++calls[id];
    *owner = owners[id];
    return failures[id] ? 1 : kCGErrorSuccess;
}
static void schedule_window_validation(bool retry) { assert(retry); ++retries; }
static void EVENT_HANDLER_WINDOW_DESTROYED(void *context, int unused) {
    struct window *w = context;
    table_remove(&g_window_manager.window, &w->id);
    free(w);
    ++destroyed;
}
'''
source += extract("src/window.c", "bool window_claim_for_destruction(struct window *window)")
source += extract("src/event_loop.c", "static void validate_windows_after_focus(uint32_t focused_window_id, bool is_retry)")
source += r'''
static struct window *add(uint32_t id) {
    struct window *w = calloc(1, sizeof *w);
    w->id = id; w->id_ptr = &w->id; w->application = &app;
    owners[id] = app.connection;
    table_add(&g_window_manager.window, &id, w);
    return w;
}
int main(void) {
    table_init(&g_window_manager.window, 8, hash, cmp);
    struct window *a = add(1), *b = add(2);
    failures[1] = 1;
    validate_windows_after_focus(0, false);
    assert(retries == 1 && destroyed == 0);
    assert(a->owner_query_retry_pending && !b->owner_query_retry_pending);

    // B's first error and a newly discovered C must not join A's retry.
    failures[1] = 0; failures[2] = 1;
    struct window *c = add(3);
    failures[3] = 1;
    validate_windows_after_focus(0, true);
    assert(calls[1] == 2 && calls[2] == 1 && calls[3] == 0);
    assert(!a->owner_query_retry_pending && destroyed == 0);

    validate_windows_after_focus(0, false);
    assert(b->owner_query_retry_pending && c->owner_query_retry_pending);
    validate_windows_after_focus(0, true);
    assert(destroyed == 0 && retries == 2);
    assert(!b->owner_query_retry_pending && !c->owner_query_retry_pending);

    // Persistent failures preserve windows without an endless retry loop.
    validate_windows_after_focus(0, true);
    assert(calls[2] == 3 && calls[3] == 2 && retries == 2);

    // A successful mismatching owner is positive evidence for removal.
    failures[2] = 0; owners[2] = 99;
    validate_windows_after_focus(3, false);
    assert(destroyed == 1 && !window_manager_find_window(NULL, 2));
    assert(calls[3] == 2); // focused windows are excluded
    table_remove(&g_window_manager.window, &a->id); free(a);
    table_remove(&g_window_manager.window, &c->id); free(c);
    table_free(&g_window_manager.window);
    puts("window validation regressions passed");
}
'''

with tempfile.TemporaryDirectory(prefix="yabai-window-validation-") as tmp:
    path = Path(tmp)
    (path / "test.c").write_text(source)
    subprocess.run(["xcrun", "clang", "-g", "-O1", "-fsanitize=address,undefined",
                    "-I" + str(ROOT / "src"), str(path / "test.c"),
                    "-o", str(path / "test")], check=True)
    subprocess.run([str(path / "test")], check=True, timeout=10)
