"""Record a bounded live trace, omitting titles and unrelated daemon commands.

Run while Yabai is active. Stop early by creating OUTPUT/stop. This temporarily
enables debug logging and restores its original setting on normal exit/error.
"""
import time,json,hashlib,re,os,argparse,tempfile
from pathlib import Path
from performance import request,command
parser=argparse.ArgumentParser(description='Record space/window events and changed geometry; restore debug output when done.')
parser.add_argument('--duration',type=float,default=60)
parser.add_argument('--output',type=Path)
args=parser.parse_args()
if not 0<args.duration<=3600: parser.error('duration must be between 0 and 3600 seconds')
out=args.output or Path(tempfile.mkdtemp(prefix='yabai-space-switch-trace-'))
out.mkdir(parents=True,exist_ok=True)
original=request('config','debug_output')[1].decode().strip()
installed=Path.home()/'.local/bin/yabai-fork'
meta={'installed_sha256':hashlib.sha256(installed.read_bytes()).hexdigest(),'daemon_pid':command(['pgrep','-f',str(installed)])[1].decode().strip(),'original_debug':original,'started_at':time.strftime('%Y-%m-%dT%H:%M:%S%z')}
log=Path('/tmp/yabai_'+os.environ['USER']+'.out.log');offset=log.stat().st_size if log.exists() else 0
snapshots=[];events=[];last=None;started=time.monotonic()
try:
 request('config','debug_output','on')
 print('Trace active; daemon '+meta['daemon_pid']+'; build '+meta['installed_sha256'][:12],flush=True)
 while time.monotonic()-started<args.duration and not (out/'stop').exists():
  stamp=round(time.monotonic()-started,3)
  r=request('query','--windows','id,pid,app,frame,space,split-type,split-child,is-visible,is-floating,is-hidden,is-minimized,has-ax-reference')[1]
  if r.startswith(b'\x07'):events.append({'t':stamp,'query_error':r[1:].decode()})
  else:
   data=json.loads(r)
   if data!=last: snapshots.append({'t':stamp,'windows':data});last=data; (out/'snapshots.json').write_text(json.dumps(snapshots,indent=2)+'\n')
  if log.exists():
   with log.open() as f:
    f.seek(offset);lines=f.readlines();offset=f.tell()
   for line in lines:
    if re.match(r'^(EVENT_HANDLER_(SPACE_CHANGED|DISPLAY_CHANGED|APPLICATION_FRONT_SWITCHED|APPLICATION_HIDDEN|APPLICATION_VISIBLE|WINDOW_(CREATED|DESTROYED|FOCUSED|MINIMIZED|DEMINIMIZED|RESIZED|MOVED)|SLS_WINDOW_DESTROYED)|validate_windows_after_focus|space_manager_set_layout_for_space|window_manager_validate_windows_on_space|window_manager_check_for_windows_on_space|window_manager_validate_and_check_for_windows_on_space|EVENT_HANDLER_DAEMON_MESSAGE: (space|window))',line):
     events.append({'t':stamp,'line':line.strip()}); (out/'events.json').write_text(json.dumps(events,indent=2)+'\n')
  time.sleep(.2)
finally:
 request('config','debug_output',original)
 (out/'trace.json').write_text(json.dumps({'metadata':meta,'snapshots':snapshots,'events':events},indent=2)+'\n')
 print('Trace saved; '+str(len(snapshots))+' changed snapshots; '+str(len(events))+' selected events; debug restored to '+original,flush=True)
