"""Performance review probes. Default modes never restart or modify the daemon.

Usage: python3 audit-validation/performance.py MODE [--output DIR]
`focus` repeatedly raises the currently focused visible window for three seconds.
Native sources are extracted from this checkout; stubbed cases are labelled.
"""
import argparse
import ctypes
import errno
import hashlib
import json
import os
from pathlib import Path
import random
import re
import shutil
import socket
import statistics
import struct
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
CLIENT = Path('/opt/homebrew/bin/yabai')


def function(path, signature):
    source = (ROOT / path).read_text()
    start = source.index(signature + '\n{')
    brace = source.index('{', start)
    depth, end = 1, brace + 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]


def summary(values):
    if not values:
        return dict(n=0, median_ms=None, p95_ms=None, max_ms=None, samples_ms=[])
    ordered = sorted(values)
    return dict(n=len(values), median_ms=statistics.median(values),
                p95_ms=ordered[max(0, int(len(values) * .95 + .999) - 1)],
                max_ms=max(values), samples_ms=values)


def request(*args, allow_failure=False):
    # Exact existing client framing, including both terminating NUL bytes.
    payload = b'\0'.join(arg.encode() for arg in args) + b'\0\0'
    started = time.perf_counter_ns()
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        sock.settimeout(5)
        sock.connect('/tmp/yabai_' + os.environ['USER'] + '.socket')
        sock.sendall(struct.pack('=i', len(payload)) + payload)
        try:
            sock.shutdown(socket.SHUT_WR)
        except OSError as error:
            # A complete request may already have been handled and closed.
            if error.errno != errno.ENOTCONN:
                raise
        chunks = []
        while chunk := sock.recv(65536):
            chunks.append(chunk)
    result = b''.join(chunks)
    if result.startswith(b'\x07') and not allow_failure:
        raise RuntimeError(result[1:].decode())
    return (time.perf_counter_ns() - started) / 1e6, result


def command(args, env=None, cwd=None):
    started = time.perf_counter_ns()
    result = subprocess.run(args, capture_output=True, timeout=10, check=True, env=env, cwd=cwd)
    return (time.perf_counter_ns() - started) / 1e6, result.stdout


def process_environment(pid):
    # Parse NUL-delimited KERN_PROCARGS2 instead of ambiguous `ps e` output.
    # Keep the environment in memory; never persist arbitrary environment values.
    libc = ctypes.CDLL(None, use_errno=True)
    mib = (ctypes.c_int * 3)(1, 49, pid)  # CTL_KERN, KERN_PROCARGS2
    size = ctypes.c_size_t(1024 * 1024)
    buf = ctypes.create_string_buffer(size.value)
    if libc.sysctl(mib, 3, buf, ctypes.byref(size), None, 0):
        raise OSError(ctypes.get_errno(), 'KERN_PROCARGS2')
    data = buf.raw[:size.value]
    argc = struct.unpack_from('=i', data)[0]
    pos = data.index(b'\0', 4) + 1  # Executable path, then padding.
    while pos < len(data) and data[pos] == 0:
        pos += 1
    for _ in range(argc):
        pos = data.index(b'\0', pos) + 1
    return dict(item.decode().split('=', 1) for item in data[pos:].split(b'\0') if b'=' in item)


def metadata():
    return dict(source=command(['git', '-c', 'core.fsmonitor=false', 'rev-parse', 'HEAD'])[1].decode().strip(),
                os=command(['sw_vers', '-productVersion'])[1].decode().strip(),
                architecture=command(['uname', '-m'])[1].decode().strip(),
                client=str(CLIENT),
                client_sha256=hashlib.sha256(CLIENT.read_bytes()).hexdigest(),
                daemon_pid=command(['pgrep', '-f', '/Users/jesse/.local/bin/yabai-fork'])[1].decode().strip(),
                debug_output=request('config', 'debug_output')[1].decode().strip(),
                animation_duration=request('config', 'window_animation_duration')[1].decode().strip(),
                observed_at=time.strftime('%Y-%m-%dT%H:%M:%S%z'))


def live():
    skhd_pid = int(command(['pgrep', '-x', 'skhd'])[1])
    skhd_env = process_environment(skhd_pid)
    skhd_shell = skhd_env.get('SHELL', '/bin/bash')
    cwd_lines = command(['lsof', '-a', '-p', str(skhd_pid), '-d', 'cwd', '-Fn'])[1].decode().splitlines()
    skhd_cwd = next(line[1:] for line in cwd_lines if line.startswith('n'))
    windows = json.loads(request('query', '--windows', 'id,pid,app,is-floating,is-visible,has-focus')[1])
    cases = {
        'config': ['config', 'window_animation_duration'],
        'all_ids': ['query', '--windows', 'id'],
        'all_cached_frame': ['query', '--windows', 'id,frame'],
        'all_titles': ['query', '--windows', 'id,title'],
        'all_space_display': ['query', '--windows', 'id,space,display'],
        'all_level_sticky': ['query', '--windows', 'id,level,sub-level,opacity,is-sticky'],
        'all_properties': ['query', '--windows'],
        'focused_id': ['query', '--windows', 'id', '--window'],
    }
    samples = {name: [] for name in cases}
    errors = {name: [] for name in cases}
    sizes = {}
    rng = random.Random(20261001)
    # Warm each path, then interleave to reduce order/temperature bias.
    for args in cases.values():
        request(*args, allow_failure=True)
    for _ in range(40):
        order = list(cases)
        rng.shuffle(order)
        for name in order:
            elapsed, response = request(*cases[name], allow_failure=True)
            (errors[name] if response.startswith(b'\x07') else samples[name]).append(elapsed)
            sizes[name] = len(response)
        time.sleep(.01)
    commands = {
        'cli_version': [str(CLIENT), '--version'],
        'cli_config': [str(CLIENT), '-m', 'config', 'window_animation_duration'],
        'fork_cli_config': [str(ROOT / 'bin/yabai'), '-m', 'config', 'window_animation_duration'],
        'zsh_noop': ['/bin/zsh', '-c', ':'],
        'zsh_cli_config': ['/bin/zsh', '-c', 'exec /opt/homebrew/bin/yabai -m config window_animation_duration'],
        'sh_noop': ['/bin/sh', '-c', ':'],
        'skhd_shell_noop': [skhd_shell, '-c', ':'],
        'skhd_shell_config': [skhd_shell, '-c', 'yabai -m config window_animation_duration'],
    }
    if Path(skhd_shell).name == 'fish':
        commands['fish_no_config_noop'] = [skhd_shell, '--no-config', '-c', ':']
        commands['fish_no_config_cli'] = [skhd_shell, '--no-config', '-c', 'yabai -m config window_animation_duration']
        commands['fish_vendor_mise_disabled_noop'] = [skhd_shell, '-c', ':']
        commands['sh_cli_config'] = ['/bin/sh', '-c', 'yabai -m config window_animation_duration']
    process_samples = {name: [] for name in commands}
    for _ in range(25):
        order = list(commands)
        rng.shuffle(order)
        for name in order:
            env = {**skhd_env, 'MISE_FISH_AUTO_ACTIVATE': '0'} if name == 'fish_vendor_mise_disabled_noop' else skhd_env
            process_samples[name].append(command(commands[name], env, skhd_cwd)[0])
    return dict(metadata=metadata(), skhd_shell=skhd_shell, skhd_cwd=skhd_cwd,
                skhd_client=shutil.which('yabai', path=skhd_env.get('PATH')), windows=windows,
                socket={name: {**summary(values), 'response_bytes': sizes[name],
                               'failed_requests': summary(errors[name])}
                        for name, values in samples.items()},
                process={name: summary(values) for name, values in process_samples.items()})


COMMON = r'''
#import <Cocoa/Cocoa.h>
#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <assert.h>
#include <unistd.h>
#include <sys/mman.h>
#include <sys/wait.h>
#include <sys/socket.h>
#include <pthread.h>
#include <semaphore.h>
#include <fcntl.h>
#include <stdarg.h>
#include <regex.h>
#define TIME_FUNCTION
#define EVENT_HANDLER(x) void EVENT_HANDLER_##x(void *context,int param1)
static double now(void) { return (double)clock_gettime_nsec_np(CLOCK_MONOTONIC_RAW) / 1e6; }
'''


def native(out, name, source, args=(), optimize='-O3'):
    path = out / (name + '.m')
    path.write_text(COMMON + source)
    compile_args = ['xcrun', 'clang', optimize, '-g', '-fno-objc-arc', '-I' + str(ROOT / 'src'),
                    str(path), '-o', str(out / name), '-framework', 'Cocoa',
                    '-F/System/Library/PrivateFrameworks', '-framework', 'SkyLight']
    build = subprocess.run(compile_args, capture_output=True, text=True)
    (out / (name + '.build.log')).write_text(build.stdout + build.stderr)
    build.check_returncode()
    result = command([str(out / name), *map(str, args)])[1].decode()
    (out / (name + '.json')).write_text(result)
    return json.loads(result)


def harness(out):
    ids = [w['id'] for w in json.loads(request('query', '--windows', 'id')[1])]
    validator = function('src/event_loop.c', 'static void validate_windows_after_focus(uint32_t focused_window_id, bool is_retry)')
    claim = function('src/window.c', 'bool window_claim_for_destruction(struct window *window)')
    validation = r'''
#define debug(...) ((void)0)
#define HASHTABLE_IMPLEMENTATION
#include "misc/hashtable.h"
extern int SLSMainConnectionID(void);
extern CGError SLSGetWindowOwner(int, uint32_t, int *);
struct application { int connection; };
struct window { uint32_t id; uint32_t *id_ptr; struct application *application; bool owner_query_retry_pending; };
struct { struct table window,managed; } g_window_manager;
int g_connection, destroyed;
static unsigned long hash(void *p){return *(uint32_t *)p;}
static int cmp(void *a,void *b){return *(uint32_t *)a==*(uint32_t *)b;}
static void *window_manager_find_managed_window(void *m,struct window *w){return table_find(&g_window_manager.managed,&w->id);}
static struct window *window_manager_find_window(void *m,uint32_t id){return table_find(&g_window_manager.window,&id);}
static void schedule_window_validation(bool retry){}
static void window_handle_destroyed(struct window *p){++destroyed;}
''' + claim + '\n' + validator + r'''
int main(int argc,char **argv) {
  g_connection=SLSMainConnectionID();
  int n=argc-1; struct window *ws=calloc(n,sizeof(*ws)); struct application *apps=calloc(n,sizeof(*apps));
  printf("{\"owner_batches\":[");
  int sizes[]={1,10,100,500};
  for(int s=0;s<4;s++) {
    printf("%s{\"calls\":%d,\"samples_ms\":[",s?",":"",sizes[s]);
    for(int r=0;r<50;r++){double t=now();for(int i=0;i<sizes[s];i++){int owner;assert(SLSGetWindowOwner(g_connection,atoi(argv[1+i%n]),&owner)==0);}printf("%s%.6f",r?",":"",now()-t);}
    printf("]}");
  }
  printf("],\"validation\":[");
  int caps[]={150,65536};
  for(int c=0;c<2;c++) {
    table_init(&g_window_manager.window,caps[c],hash,cmp);table_init(&g_window_manager.managed,150,hash,cmp);
    for(int i=0;i<n;i++){ws[i].id=atoi(argv[1+i]);ws[i].id_ptr=&ws[i].id;ws[i].application=&apps[i];assert(SLSGetWindowOwner(g_connection,ws[i].id,&apps[i].connection)==0);table_add(&g_window_manager.window,&ws[i].id,&ws[i]);table_add(&g_window_manager.managed,&ws[i].id,&ws[i]);}
    printf("%s{\"capacity\":%d,\"windows\":%d,\"samples_ms\":[",c?",":"",caps[c],n);
    for(int r=0;r<100;r++){double t=now();validate_windows_after_focus(0,false);printf("%s%.6f",r?",":"",now()-t);}
    printf("]}");table_free(&g_window_manager.window);table_free(&g_window_manager.managed);
  }
  printf("],\"destroyed\":%d}\n",destroyed);assert(!destroyed);
}
'''
    result = {'validation_o3': native(out, 'validation-o3', validation, ids),
              'validation_o0': native(out, 'validation-o0', validation, ids, '-O0')}
    update = function('src/event_loop.c', 'static void update_window_notifications(void)')
    schedule = function('src/event_loop.c', 'static void schedule_window_notification_update(void)')
    handler = function('src/event_loop.c', 'static EVENT_HANDLER(WINDOW_NOTIFICATIONS_UPDATE)')
    refresh = r'''
#define debug(...) ((void)0)
#define HASHTABLE_IMPLEMENTATION
#include "misc/hashtable.h"
struct window {uint32_t id;}; struct window_node {uint32_t window_order[1];};
struct {struct table window,insert_feedback;} g_window_manager;
int g_connection,g_event_loop,pending,refreshes;long total_ids;
static bool window_notification_update_pending;
enum {WINDOW_NOTIFICATIONS_UPDATE};
static bool workspace_is_macos_sequoia_or_newer(void){return true;}
static unsigned long hash(void *p){return *(uint32_t *)p;}
static int cmp(void *a,void *b){return *(uint32_t *)a==*(uint32_t *)b;}
static CGError SLSRequestNotificationsForWindows(int c,uint32_t *ids,int n){refreshes++;total_ids+=n;return 0;}
static void event_loop_post(void *q,int type,void *ctx,int param){pending++;}
''' + update + '\n' + schedule + '\n' + handler + r'''
int main(void){printf("[");int sizes[]={10,100,1000};for(int s=0;s<3;s++)for(int interleave=0;interleave<2;interleave++){
 int n=sizes[s];struct window *ws=calloc(n,sizeof(*ws));table_init(&g_window_manager.window,150,hash,cmp);refreshes=0;total_ids=0;pending=0;window_notification_update_pending=false;double t=now();
 for(int i=0;i<n;i++){ws[i].id=i+1;table_add(&g_window_manager.window,&ws[i].id,&ws[i]);schedule_window_notification_update();if(interleave){pending--;EVENT_HANDLER_WINDOW_NOTIFICATIONS_UPDATE(NULL,0);}}
 if(!interleave){assert(pending==1);pending--;EVENT_HANDLER_WINDOW_NOTIFICATIONS_UPDATE(NULL,0);}
 printf("%s{\"windows\":%d,\"interleaved\":%s,\"refreshes\":%d,\"total_ids\":%ld,\"elapsed_ms\":%.6f}",s||interleave?",":"",n,interleave?"true":"false",refreshes,total_ids,now()-t);table_free(&g_window_manager.window);free(ws);
 }printf("]\n");}
'''
    result['refresh_stubbed_api'] = native(out, 'refresh', refresh)
    logging = r'''
bool g_verbose;
#include "misc/log.h"
int main(int argc,char **argv){int saved=dup(1);assert(freopen(argv[1],"w",stdout));
 double timings[3];int n=20000;char message[]="window\0--focus\0east\0\0";
 for(int mode=0;mode<3;mode++){g_verbose=mode!=0;double t=now();for(int i=0;i<n;i++){if(mode==2)debug_message("DAEMON_MESSAGE",message);else debug("WINDOW_FOCUSED: App %d\n",i);}fflush(stdout);timings[mode]=now()-t;}
 dup2(saved,1);close(saved);printf("{\"messages\":%d,\"disabled_ms\":%.6f,\"buffered_file_ms\":%.6f,\"flushed_file_ms\":%.6f}\n",n,timings[0],timings[1],timings[2]);}
'''
    result['logging_regular_file'] = native(out, 'logging', logging, [out / 'logging-sink.txt'])
    signal_flush = function('src/event_signal.c', 'void event_signal_flush(void)')
    signals = r'''
#define debug(...) ((void)0)
#include "event_signal.h"
struct {uint64_t used;void *memory;} g_signal_storage;
struct signal *g_signal_event[SIGNAL_TYPE_COUNT];
#define buf_len(x) 1
int reject;
static bool event_signal_filter(struct event_signal *e,struct signal *s){return reject;}
''' + signal_flush + r'''
int main(void){setbuf(stdout,NULL);struct event_signal es={0};struct signal sig={0};es.type=SIGNAL_WINDOW_CREATED;g_signal_storage.memory=&es;g_signal_event[es.type]=&sig;int p[2];assert(!pipe(p));fcntl(p[0],F_SETFD,FD_CLOEXEC);char cmd[80];snprintf(cmd,sizeof(cmd),"printf x >&%d",p[1]);sig.command=cmd;
 printf("[");for(int match=0;match<2;match++){reject=!match;printf("%s{\"matching\":%s,\"samples\":[",match?",":"",match?"true":"false");for(int r=0;r<30;r++){g_signal_storage.used=sizeof(es);double t=now();event_signal_flush();double parent=now()-t;int status;assert(wait(&status)>0);assert(WIFEXITED(status)&&WEXITSTATUS(status)==0);if(match){char c;assert(read(p[0],&c,1)==1);}printf("%s{\"parent_ms\":%.6f,\"completion_ms\":%.6f}",r?",":"",parent,now()-t);}printf("]}");}printf("]\n");}
'''
    result['signal_flush_stubbed_filter'] = native(out, 'signals', signals)
    post = function('src/event_loop.c', 'void event_loop_post(struct event_loop *event_loop, enum event_type type, void *context, int param1)')
    queue_init = function('src/event_loop.c', 'static bool event_loop_init(struct event_loop *event_loop)')
    queue_take = function('src/event_loop.c', 'static struct event *event_loop_take(struct event_loop *event_loop, bool wait)')
    queue = r'''
#include "misc/log.h"
#include "event_loop.h"
''' + queue_init + '\n' + queue_take + '\n' + post + r'''
int main(void){struct event_loop q={0};assert(event_loop_init(&q));CGEventRef event=CGEventCreate(NULL);assert(event);int n=100000;printf("[");for(int retain=0;retain<2;retain++){double t=now();for(int i=0;i<n;i++){event_loop_post(&q,MOUSE_DRAGGED,retain?(void *)CFRetain(event):NULL,0);struct event *node=event_loop_take(&q,false);assert(node&&!node->next);if(retain)CFRelease(node->context);free(node);}printf("%s{\"retain_release\":%s,\"events\":%d,\"elapsed_ms\":%.6f}",retain?",":"",retain?"true":"false",n,now()-t);}printf("]\n");CFRelease(event);pthread_cond_destroy(&q.ready);pthread_mutex_destroy(&q.lock);}
'''
    result['queue_drained_single_producer'] = native(out, 'queue', queue)
    return dict(metadata=metadata(), results=result)


def mechanisms(out):
    event_source = (ROOT / 'src/event_loop.c').read_text()
    resize_dt = next(line.strip() for line in event_source.splitlines()
                     if 'float dt = ((float) event_time - g_mouse_state.last_moved_time)' in line
                     or 'double dt = elapsed_time_ms(g_mouse_state.last_moved_time, event_time)' in line)
    elapsed_helper = (function('src/misc/helpers.h', 'static inline double elapsed_time_ms(uint64_t begin, uint64_t end)')
                      if 'elapsed_time_ms' in resize_dt else '')
    threshold = '67.67' if elapsed_helper else '67.67f'
    timer = r'''
#include <Carbon/Carbon.h>
#include <mach/mach_time.h>
#include <math.h>
struct {uint64_t last_moved_time;} g_mouse_state;
''' + function('src/misc/helpers.h', 'static inline uint64_t read_os_timer(void)') + '\n' + function('src/misc/helpers.h', 'static inline uint64_t read_os_freq(void)') + '\n' + elapsed_helper + '\n' + r'''
static double current_dt(uint64_t event_time,uint64_t last){g_mouse_state.last_moved_time=last;
''' + resize_dt + r'''
return dt;}
int main(void){uint64_t current=read_os_timer();uint64_t bases[]={current,3600ULL*1000000000,86400ULL*1000000000,7ULL*86400*1000000000,30ULL*86400*1000000000};printf("{\"current_uptime_days\":%.6f,\"cases\":[",current/1e9/86400);
 for(int b=0;b<5;b++){uint64_t base=bases[b];float f=(float)base;double ulp=(nextafterf(f,INFINITY)-f)/1e6;int skipped=0,early=0;for(int ms=1;ms<=200;ms++){bool expected=ms>=67.67;bool actual=current_dt(base+(uint64_t)ms*1000000,base)>=67.67f;skipped+=expected&&!actual;early+=!expected&&actual;}
 int count=0,min=10000,max=0;uint64_t last=base;for(int ms=1;ms<=3000;ms++){uint64_t t=base+(uint64_t)ms*1000000;if(current_dt(t,last)>=67.67f){int gap=(t-last)/1000000;count++;if(gap<min)min=gap;if(gap>max)max=gap;last=t;}}
 printf("%s{\"uptime_days\":%.6f,\"float_step_ms\":%.6f,\"75ms_computed_ms\":%.6f,\"wrong_skip_candidates\":%d,\"wrong_accept_candidates\":%d,\"updates_in_3s\":%d,\"min_interval_ms\":%d,\"max_interval_ms\":%d}",b?",":"",base/1e9/86400,ulp,current_dt(base+75000000,base),skipped,early,count,min,max);
 }int control=0;uint64_t last=0;for(int ms=1;ms<=3000;ms++){uint64_t t=(uint64_t)ms*1000000;if((double)(t-last)/1e6>=67.67){control++;last=t;}}assert(control==44);printf("],\"integer_difference_control_updates_in_3s\":%d}\n",control);}
'''
    timer_result = native(out, 'timer-precision', timer.replace('>=67.67f', '>=' + threshold))
    post = function('src/event_loop.c', 'void event_loop_post(struct event_loop *event_loop, enum event_type type, void *context, int param1)')
    worker = function('src/event_loop.c', 'static void *event_loop_run(void *context)')
    queue_init = function('src/event_loop.c', 'static bool event_loop_init(struct event_loop *event_loop)')
    queue_take = function('src/event_loop.c', 'static struct event *event_loop_take(struct event_loop *event_loop, bool wait)')
    wakeups = r'''
#include <errno.h>
#include "misc/log.h"
#include "event_loop.h"
struct event_loop *current_q;int waits,handled;
#define profile_begin() ((void)0)
#define profile_end_and_print() ((void)0)
static void ts_reset(void){}
static void event_signal_flush(void){}
#define EVENT_TYPE_ENTRY(value) void EVENT_HANDLER_##value(void *c,int p){handled++;}
EVENT_TYPE_LIST
#undef EVENT_TYPE_ENTRY
static int audit_wait(pthread_cond_t *c,pthread_mutex_t *m){waits++;current_q->is_running=false;return 0;}
// Replace the terminal blocking wait only, allowing the harness to finish.
#define pthread_cond_wait audit_wait
''' + queue_init + '\n' + queue_take + '\n' + post + '\n' + worker + r'''
int main(void){int ns[]={10,1000,10000};printf("[");for(int x=0;x<3;x++){
 printf("%s{\"events\":%d,\"owned_condition_queue\":true,\"samples_ms\":[",x?",":"",ns[x]);
 for(int r=0;r<30;r++){struct event_loop q={0};assert(event_loop_init(&q));for(int i=0;i<ns[x];i++)event_loop_post(&q,WINDOW_FOCUSED,NULL,0);current_q=&q;waits=handled=0;double t=now();event_loop_run(&q);double elapsed=now()-t;assert(handled==ns[x]);assert(waits==1);printf("%s%.6f",r?",":"",elapsed);pthread_cond_destroy(&q.ready);pthread_mutex_destroy(&q.lock);}
 printf("],\"wait_calls\":%d}",waits);
 }printf("]\n");}
'''
    return dict(timer_precision=timer_result,
                burst_wakeup_stubbed_handlers=native(out, 'burst-wakeups', wakeups))


def focus(out):
    snapshot = json.loads(request('query', '--windows', 'id,pid,app,has-focus,is-visible')[1])
    focused = json.loads(request('query', '--windows', 'id,pid,app,is-visible', '--window')[1])
    if not focused['is-visible']:
        raise RuntimeError('Current AX window is not visible; focus probe aborted.')
    pid = metadata()['daemon_pid']
    sample_path = out / 'focus.sample.txt'
    sample = subprocess.Popen(['/usr/bin/sample', pid, '3', '1', '-file', str(sample_path)],
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    values = []
    started = time.perf_counter()
    while time.perf_counter() - started < 3:
        values.append(request('window', '--focus', str(focused['id']))[0])
        time.sleep(.005)
    stdout, stderr = sample.communicate(timeout=10)
    (out / 'sample.log').write_bytes(stdout + stderr)
    if sample.returncode:
        raise RuntimeError('sample failed: ' + stderr.decode())
    final = json.loads(request('query', '--windows', 'id,pid,app', '--window')[1])
    return dict(metadata=metadata(), snapshot=snapshot, original=focused, final=final,
                same_window=summary(values), sample=str(sample_path),
                limitation='Command completion, not keypress-to-screen latency; same-window raises, no space switches.')


def shell_profile(out):
    pid = int(command(['pgrep', '-x', 'skhd'])[1])
    env = process_environment(pid)
    shell = env.get('SHELL', '/bin/bash')
    if Path(shell).name != 'fish':
        raise RuntimeError('This profiling mode is specific to fish.')
    lines = command(['lsof', '-a', '-p', str(pid), '-d', 'cwd', '-Fn'])[1].decode().splitlines()
    cwd = next(line[1:] for line in lines if line.startswith('n'))
    reports = []
    for i in range(3):
        profile = out / ('fish-startup-' + str(i) + '.profile')
        elapsed, _ = command([shell, '--profile-startup', str(profile), '-c', ':'], env, cwd)
        selected = []
        for line in profile.read_text().splitlines():
            match = re.match(r'\s*(\d+)\s+(\d+)\s+(.+)', line)
            if match and ('mise activate fish | source' in match[3] or 'mise hook-env' in match[3]
                          or 'source /Users/jesse/.config/fish/config.fish' in match[3]):
                selected.append(dict(own_us=int(match[1]), inclusive_us=int(match[2]), command=match[3][:160]))
        reports.append(dict(elapsed_ms=elapsed, selected_entries=selected))
    return dict(shell=shell, cwd=cwd, profiles=reports)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['live', 'harness', 'focus', 'mechanisms', 'shell-profile'])
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    out = args.output or Path(tempfile.mkdtemp(prefix='yabai-performance-'))
    out.mkdir(parents=True, exist_ok=True)
    print('Artifacts:', out, flush=True)
    if args.mode == 'live':
        result = live()
    elif args.mode == 'harness':
        result = harness(out)
    elif args.mode == 'focus':
        result = focus(out)
    elif args.mode == 'mechanisms':
        result = mechanisms(out)
    else:
        result = shell_profile(out)
    destination = out / (args.mode + '.json')
    destination.write_text(json.dumps(result, indent=2) + '\n')
    print('Results:', destination, flush=True)
