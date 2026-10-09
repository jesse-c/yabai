#!/usr/bin/env python3
"""Exercise real application-show tiling with selected and inactive native tabs."""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[2]
source = (root / 'src/event_loop.c').read_text()


def extract(signature):
    start = source.index(signature + '\n{')
    end = source.index('{', start) + 1
    depth = 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]


fixture = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#define EVENT_HANDLER(name) void EVENT_HANDLER_##name(void *context, int param1)
#define ts_alloc_list(type, n) ((type *) __builtin_alloca(sizeof(type) * ((n) ? (n) : 1)))
#define debug(...) ((void) 0)
#define VIEW_FLOAT 1
#define VIEW_IS_DIRTY 2
#define LAYER_BELOW 3
#define SIGNAL_APPLICATION_VISIBLE 4
struct application { bool is_hidden; char *name; } app = {true, "Ghostty"};
struct window { uint32_t id; uint64_t sid; bool eligible, managed; } items[3];
struct view { uint64_t sid; int layout, dirty, count; uint32_t ids[3]; void *root; } view = {.sid = 4};
struct application_space_snapshot { uint64_t sid; uint32_t *windows; int count; bool valid; };
struct { uint32_t last_window_id; } g_window_manager = {518};
struct { int unused; } g_space_manager;
static uint32_t snapshot_ids[3];
static int snapshot_count, query_count, flushes, signals, insertions;
static bool query_ok = true;
static struct application *window_manager_find_application(void *wm, int pid) { return pid == 719 ? &app : NULL; }
static struct window **window_manager_find_application_windows(void *wm, struct application *a, int *count) {
    static struct window *result[3];
    *count = 2;
    result[0] = &items[0]; result[1] = &items[1];
    return result;
}
static bool window_manager_should_manage_window(struct window *w) { return w->eligible && !app.is_hidden; }
static struct view *window_manager_find_managed_window(void *wm, struct window *w) { return w->managed ? &view : NULL; }
static uint64_t window_space(uint32_t id) {
    for (int i=0; i<2; ++i) if (items[i].id == id) return items[i].sid;
    return 0;
}
static bool space_window_list_checked(uint64_t sid, int *count, bool minimized, uint32_t **ids) {
    // The app can still be hidden when APPLICATION_VISIBLE runs.
    assert(sid==4 && minimized);
    ++query_count;
    *count=snapshot_count; *ids=snapshot_ids;
    return query_ok;
}
static struct view *space_manager_find_view(void *sm, uint64_t sid) { assert(sid==4); return &view; }
static void window_manager_adjust_layer(struct window *w, int layer) { assert(layer==LAYER_BELOW); }
static void view_add_window_node_with_insertion_point(struct view *v, struct window *w, uint32_t previous) {
    assert(previous == (insertions ? view.ids[view.count-1] : 518));
    v->ids[v->count++]=w->id; ++insertions;
}
static void window_manager_add_managed_window(void *wm, struct window *w, struct view *v) { w->managed=true; }
static void view_set_flag(struct view *v, int flag) { assert(flag==VIEW_IS_DIRTY); v->dirty=1; }
static void view_clear_flag(struct view *v, int flag) { assert(flag==VIEW_IS_DIRTY); v->dirty=0; }
static bool view_is_dirty(struct view *v) { return v->dirty; }
static bool space_is_visible(uint64_t sid) { return sid==4; }
static void window_node_flush(void *root) { ++flushes; }
static void event_signal_push(int kind, struct application *a) { assert(kind==SIGNAL_APPLICATION_VISIBLE && a==&app); ++signals; }
'''
fixture += extract('static uint64_t application_window_space_in_snapshot(struct window *window, struct application_space_snapshot *snapshots, int *snapshot_count)') + '\n'
fixture += extract('static EVENT_HANDLER(APPLICATION_VISIBLE)').replace('window_node_flush(view->root)', 'window_node_flush(NULL)') + '\n'
fixture += r'''
static void reset(void) {
    app.is_hidden=true; items[0].managed=items[1].managed=false;
    view.count=view.dirty=0;
    insertions=query_count=flushes=signals=0;
    query_ok=true;
}
int main(void) {
    // AX still tracks inactive tab 823; only selected tab 564 is on the
    // space, even while the application has not finished unhiding.
    items[0]=(struct window){.id=823,.sid=4,.eligible=true};
    items[1]=(struct window){.id=564,.sid=4,.eligible=true};
    snapshot_ids[0]=518; snapshot_ids[1]=564; snapshot_count=2;
    EVENT_HANDLER_APPLICATION_VISIBLE((void *)(intptr_t)719,0);
    assert(!app.is_hidden && !items[0].managed && items[1].managed);
    assert(view.count==1 && view.ids[0]==564 && flushes==1 && query_count==1 && signals==1);

    // Both tabs genuinely present: preserve existing insertion/batching behavior.
    reset(); snapshot_ids[2]=823; snapshot_count=3;
    EVENT_HANDLER_APPLICATION_VISIBLE((void *)(intptr_t)719,0);
    assert(items[0].managed && items[1].managed && view.count==2);
    assert(view.ids[0]==823 && view.ids[1]==564 && flushes==1 && query_count==1);

    // A failed query (or an empty successful snapshot) must not claim tiles.
    reset(); query_ok=false;
    EVENT_HANDLER_APPLICATION_VISIBLE((void *)(intptr_t)719,0);
    assert(view.count==0 && flushes==0 && signals==1 && query_count==1);
    reset(); snapshot_count=0;
    EVENT_HANDLER_APPLICATION_VISIBLE((void *)(intptr_t)719,0);
    assert(view.count==0 && flushes==0 && query_count==1);
    puts("native-tab show reconciliation regressions passed");
}
'''

with tempfile.TemporaryDirectory(prefix='yabai-native-tabs-') as tmp:
    path = Path(tmp)
    (path / 'test.c').write_text(fixture)
    subprocess.run(['xcrun', 'clang', '-g', '-O1', '-fsanitize=address,undefined',
                    str(path / 'test.c'), '-o', str(path / 'test')], check=True)
    subprocess.run([str(path / 'test')], check=True, timeout=10)
