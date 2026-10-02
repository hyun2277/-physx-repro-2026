"""Render a short video exclusively from the actual logged 29806 GT-only tensor-drive state trace."""
import argparse, json
from pathlib import Path
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation, FFMpegWriter

def main():
 p=argparse.ArgumentParser();p.add_argument('--report',type=Path,required=True);p.add_argument('--mp4',type=Path,required=True);p.add_argument('--poster',type=Path,required=True);a=p.parse_args()
 d=json.loads(a.report.read_text()); names=d['preflight']['dof_names']; limits=d['preflight']['limits_rad']; rows=d['all_records']; picks=list(range(0,len(rows),max(1,len(rows)//100)))+[len(rows)-1]
 fig,axs=plt.subplots(3,1,figsize=(10,7.4),dpi=128,sharex=True); fig.patch.set_facecolor('#f5f7fb')
 lines=[]; targets=[]; dots=[]; texts=[]
 for ax,name in zip(axs,names):
  lo,hi=limits[name]; ax.set_facecolor('#f5f7fb');ax.axhspan(lo,hi,color='#d9f2e6');ax.axhline(lo,color='#26734d',lw=1);ax.axhline(hi,color='#26734d',lw=1);ax.set_ylim(lo-.25,hi+.25);ax.set_ylabel(f'{name}\nrad')
  line,=ax.plot([],[],color='#2056a8',lw=1.7,label='actual state'); target,=ax.plot([],[],color='#d66a00',lw=1.1,label='tensor target'); dot,=ax.plot([],[],'o',color='#2056a8',ms=4); text=ax.text(.012,.91,'',transform=ax.transAxes,va='top',fontsize=8)
  lines.append(line);targets.append(target);dots.append(dot);texts.append(text)
 axs[0].legend(loc='lower right',fontsize=8);axs[-1].set_xlabel('actual physics step record'); fig.suptitle('29806 GT-only controlled-material physics drive — three joint state traces\nNot an AI prediction result; no USD target writes or transform animation',fontsize=12)
 hist={n:{'x':[],'p':[],'t':[]} for n in names}
 def update(i):
  end=picks[i]; r=rows[end]
  for ax,name,line,target,dot,text in zip(axs,names,lines,targets,dots,texts):
   h=hist[name];h['x'].append(end);h['p'].append(r['positions_rad'][name]);h['t'].append(r['requested_target_rad'] if r['active_dof']==name else float('nan'))
   line.set_data(h['x'],h['p']);target.set_data(h['x'],h['t']);dot.set_data([end],[h['p'][-1]]);text.set_text(f'actual={h["p"][-1]:.3f} rad | active={r["active_dof"]}')
  axs[-1].set_xlim(0,len(rows)-1);return [*lines,*targets,*dots,*texts]
 update(len(picks)-1);a.poster.parent.mkdir(parents=True,exist_ok=True);fig.savefig(a.poster,bbox_inches='tight');anim=FuncAnimation(fig,update,frames=len(picks),interval=100,blit=False);a.mp4.parent.mkdir(parents=True,exist_ok=True);anim.save(a.mp4,writer=FFMpegWriter(fps=10,bitrate=1000));plt.close(fig)
if __name__=='__main__':main()
