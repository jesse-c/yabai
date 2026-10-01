"""Check failed-versus-empty space queries and reconciliation with extracted source.

WindowServer entry points, tree mutation and flushing are stubbed. No daemon access.
"""
import argparse,json,tempfile,subprocess
from pathlib import Path
from performance import ROOT,function,native


def run(out,baseline=False):
    query_signature='static uint32_t *space_window_list_for_connection_query(uint64_t *space_list, int space_count, int cid, int *count, bool include_minimized, bool *success)'
    reconciler_path='src/window_manager.c'
    if baseline:
        old=out/'baseline-window-manager.c'
        old.write_bytes(subprocess.check_output(['git','-c','core.fsmonitor=false','show','70c8dc1:src/window_manager.c'],cwd=ROOT))
        reconciler_path=str(old)
    source=r'''
#include "view.h"
#define WINDOW_MINIMIZE 4
#define VIEW_FLOAT 3
#define LAYER_NORMAL 0
#define LAYER_BELOW 1
#define debug(...) ((void)0)
struct window {uint32_t id;unsigned flags;};
struct window_manager {int unused;};
struct space_manager {int unused;};
struct window_manager g_window_manager;
int g_connection,mode,index_,validations,checks,flushes,removals;
struct window windows[2]={{.id=1},{.id=2}};
struct view view;
static struct window *window_manager_find_window(void *wm,uint32_t id){return id==1?&windows[0]:id==2?&windows[1]:NULL;}
static bool window_check_flag(struct window *window,int flag){return window->flags&flag;}
static CFArrayRef SLSCopyWindowsWithOptionsAndTags(int cid,int owner,CFArrayRef spaces,uint32_t options,uint64_t *set,uint64_t *clear){
 if(mode==1)return NULL;
 if(mode==0)return CFArrayCreate(NULL,NULL,0,&kCFTypeArrayCallBacks);
 int ids[]={1,2};CFNumberRef a=CFNumberCreate(NULL,kCFNumberIntType,&ids[0]),b=CFNumberCreate(NULL,kCFNumberIntType,&ids[1]);
 const void *items[]={a,b};CFArrayRef result=CFArrayCreate(NULL,items,2,&kCFTypeArrayCallBacks);CFRelease(a);CFRelease(b);return result;
}
static CFTypeRef SLSWindowQueryWindows(int cid,CFArrayRef list,int count){return mode==2?NULL:CFRetain(list);}
static CFTypeRef SLSWindowQueryResultCopyWindows(CFTypeRef query){index_=-1;return mode==3?NULL:CFRetain(query);}
static bool SLSWindowIteratorAdvance(CFTypeRef iterator){return ++index_<CFArrayGetCount(iterator);}
static uint64_t SLSWindowIteratorGetTags(CFTypeRef iterator){return 0;}
static uint64_t SLSWindowIteratorGetAttributes(CFTypeRef iterator){return 0;}
static uint32_t SLSWindowIteratorGetParentID(CFTypeRef iterator){return 0;}
static uint32_t SLSWindowIteratorGetWindowID(CFTypeRef iterator){int id;CFNumberGetValue(CFArrayGetValueAtIndex(iterator,index_),kCFNumberIntType,&id);return id;}
static int SLSWindowIteratorGetLevel(CFTypeRef iterator){return 0;}
#define ts_alloc_list(type,count) calloc(count,sizeof(type))
static void *ts_resize(void *p,size_t old,size_t size){return p;}
''' + function('src/misc/helpers.h','static inline CFArrayRef cfarray_of_cfnumbers(void *values, size_t size, int count, CFNumberType type)')+'\n'+function('src/space.c',query_signature)+'\n'+function('src/space.c','bool space_window_list_checked(uint64_t sid, int *count, bool include_minimized, uint32_t **window_list)')+r'''
static uint32_t *space_window_list(uint64_t sid,int *count,bool minimized){uint32_t *ids;space_window_list_checked(sid,count,minimized,&ids);return ids;}
static struct view *space_manager_find_view(struct space_manager *sm,uint64_t sid){return &view;}
uint32_t *view_find_window_list(struct view *v,int *count){*count=v->root->window_count;return v->root->window_list;}
struct window_node *view_remove_window_node(struct view *v,struct window *w){removals++;return NULL;}
static void window_manager_adjust_layer(struct window *w,int layer){}
static void window_manager_remove_managed_window(struct window_manager *wm,uint32_t id){}
static void window_manager_purify_window(struct window_manager *wm,struct window *w){}
''' + function('src/window_manager.c','static void window_manager_validate_windows_on_space(struct window_manager *wm, struct view *view, uint32_t *window_list, int window_count)')+r'''
static void window_manager_check_for_windows_on_space(struct window_manager *wm,struct view *view,uint32_t *ids,int count){checks++;free(ids);}
static bool space_is_visible(uint64_t sid){return true;}
bool view_is_dirty(struct view *v){return v->flags&VIEW_IS_DIRTY;}
void window_node_flush(struct window_node *root){flushes++;}
''' + function(reconciler_path,'void window_manager_validate_and_check_for_windows_on_space(struct space_manager *sm, struct window_manager *wm, uint64_t sid)')+r'''
int main(int argc,char **argv){
 bool baseline=argc>1;
 struct space_manager sm={0};struct window_node root={.window_count=2,.window_list={1,2}};
 view=(struct view){.sid=42,.layout=VIEW_BSP,.root=&root};
 printf("{\"baseline_reconciler\":%s,\"cases\":[",baseline?"true":"false");
 for(mode=0;mode<6;mode++){
  windows[0].flags=windows[1].flags=mode==5?WINDOW_MINIMIZE:0;
  int count=99;uint32_t *list=(void *)1;bool success=space_window_list_checked(42,&count,false,&list);
  assert(success==(mode==0||mode>=4));assert(count==(mode==4?2:0));
  assert((list!=NULL)==(mode>=4));if(list){if(mode==4)assert(list[0]==1&&list[1]==2);free(list);}
  removals=checks=flushes=0;view.flags=0;
  window_manager_validate_and_check_for_windows_on_space(&sm,&g_window_manager,42);
  bool empty=mode==0||mode==5||(baseline&&mode<4);
  assert(removals==(empty?2:0));assert(checks==(baseline||success));assert(flushes==empty);
  printf("%s{\"mode\":%d,\"query_succeeded\":%s,\"count\":%d,\"removed_nodes\":%d,\"reconciles\":%d}",mode?",":"",mode,success?"true":"false",count,removals,checks);
 }
 view.layout=VIEW_FLOAT;checks=removals=0;window_manager_validate_and_check_for_windows_on_space(&sm,&g_window_manager,42);assert(!checks&&!removals);
 printf("],\"float_layout_skips_reconciliation\":true}\n");
}
'''
    return native(out,'space-query-failure',source,args=['baseline'] if baseline else [])


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path);parser.add_argument('--baseline',action='store_true');args=parser.parse_args()
    out=args.output or Path(tempfile.mkdtemp(prefix='yabai-space-query-failure-'));out.mkdir(parents=True,exist_ok=True)
    print('Artifacts:',out,flush=True);print(json.dumps(run(out,args.baseline),indent=2))
