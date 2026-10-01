"""Reproduce repeated-layout resets without touching the running daemon.

Extracts the real space-layout setter and view_clear. WindowServer reconciliation,
geometry updates and managed-window cleanup are stubbed and counted.
"""
import argparse
import json
from pathlib import Path
import subprocess
import tempfile
from performance import ROOT, function, native

SIGNATURE = 'void space_manager_set_layout_for_space(struct space_manager *sm, uint64_t sid, enum view_type layout)'


def extract(text, signature):
    start = text.index(signature + '\n{')
    brace = text.index('{', start)
    depth, end = 1, brace + 1
    while depth:
        depth += (text[end] == '{') - (text[end] == '}')
        end += 1
    return text[start:end]


def run(out, baseline):
    setter = (extract(subprocess.check_output(['git', '-c', 'core.fsmonitor=false', 'show', '70c8dc1:src/space_manager.c']).decode(), SIGNATURE)
              if baseline else function('src/space_manager.c', SIGNATURE))
    source = r'''
#include "view.h"
struct space_manager {struct view *view;};
struct {int removed;} g_window_manager;
static int reconciles, updates;
static struct view *space_manager_find_view(struct space_manager *sm,uint64_t sid){assert(sm->view->sid==sid);return sm->view;}
static void window_manager_remove_managed_window(void *wm,uint32_t wid){assert(wid);g_window_manager.removed++;}
void insert_feedback_destroy(struct window_node *node){}
static void window_node_destroy(struct window_node *node){
 if(node->left)window_node_destroy(node->left);
 if(node->right)window_node_destroy(node->right);
 for(int i=0;i<node->window_count;i++)window_manager_remove_managed_window(&g_window_manager,node->window_list[i]);
 free(node);
}
void view_update(struct view *view){updates++;}
''' + function('src/view.c', 'void view_clear(struct view *view)') + r'''
static void window_manager_validate_and_check_for_windows_on_space(struct space_manager *sm,void *wm,uint64_t sid){
 reconciles++;
 // Enumeration supplies B,A. A reset rebuilds in this order; an existing tree is retained.
 struct window_node *root=sm->view->root;
 if(!root->left&&!root->window_count){
  if(sm->view->layout==VIEW_BSP){
   root->left=calloc(1,sizeof(*root));root->right=calloc(1,sizeof(*root));
   root->left->window_count=root->right->window_count=1;
   root->left->window_list[0]=2;root->right->window_list[0]=1;
  }else{root->window_count=2;root->window_list[0]=2;root->window_list[1]=1;}
 }
}
''' + setter + r'''
int main(int argc,char **argv){
 bool baseline=argc>1;
 struct window_node root={0};root.left=calloc(1,sizeof(root));root.right=calloc(1,sizeof(root));
 root.left->window_count=root.right->window_count=1;
 root.left->window_list[0]=1;root.right->window_list[0]=2;
 root.ratio=.37f;root.split=SPLIT_X;root.left->zoom=&root;
 struct view view={.sid=42,.layout=VIEW_BSP,.root=&root,.insertion_point=1};
 struct space_manager sm={.view=&view};
 space_manager_set_layout_for_space(&sm,42,VIEW_BSP);
 bool preserved=root.left->window_list[0]==1&&root.right->window_list[0]==2&&root.ratio==.37f&&root.left->zoom==&root&&view.insertion_point==1;
 printf("{\"baseline\":%s,\"same_bsp_preserved_order_ratio_zoom_insertion\":%s,\"reconciles_after_same_bsp\":%d,\"removed_after_same_bsp\":%d",baseline?"true":"false",preserved?"true":"false",reconciles,g_window_manager.removed);
 assert(reconciles==1);assert(preserved==!baseline);
 int before=g_window_manager.removed;
 space_manager_set_layout_for_space(&sm,42,VIEW_STACK);
 assert(view.layout==VIEW_STACK&&!root.left&&root.window_count==2&&g_window_manager.removed==before+2&&reconciles==2);
 before=g_window_manager.removed;
 space_manager_set_layout_for_space(&sm,42,VIEW_STACK);
 assert(root.window_count==2&&reconciles==3);
 assert(g_window_manager.removed==before+(baseline?2:0));
 space_manager_set_layout_for_space(&sm,42,VIEW_FLOAT);
 assert(view.layout==VIEW_FLOAT&&!root.left&&root.window_count==0&&reconciles==3);
 printf(",\"bsp_to_stack_clears\":true,\"same_stack_reconciles\":true,\"stack_to_float_clears_without_reconcile\":true}\n");
}
'''
    return native(out, 'space-layout', source, args=['baseline'] if baseline else [])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', action='store_true', help='Use the pre-change setter from 70c8dc1')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    out = args.output or Path(tempfile.mkdtemp(prefix='yabai-space-layout-'))
    out.mkdir(parents=True, exist_ok=True)
    print('Artifacts:', out, flush=True)
    print(json.dumps(run(out, args.baseline), indent=2))
