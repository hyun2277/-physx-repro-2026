"""Render a short video only from logged, actual GT-only tensor-drive joint states."""
import argparse,json
from pathlib import Path
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation, FFMpegWriter

def main():
 p=argparse.ArgumentParser();p.add_argument('--report',type=Path,required=True);p.add_argument('--mp4',type=Path,required=True);p.add_argument('--poster',type=Path,required=True);a=p.parse_args()
 d=json.loads(a.report.read_text()); rows=d['records']; lo,hi=d['preflight']['limits_rad']; picks=list(range(0,len(rows),max(1,len(rows)//100)))+[len(rows)-1]
 fig,ax=plt.subplots(figsize=(10,5.625),dpi=128);ax.set_facecolor('#f5f7fb');ax.axhspan(lo,hi,color='#d9f2e6');ax.axhline(lo,color='#26734d',lw=1);ax.axhline(hi,color='#26734d',lw=1);ax.set_xlim(0,len(rows)-1);ax.set_ylim(lo-.25,hi+.25);ax.set_xlabel('physics step record');ax.set_ylabel('joint position (rad)');ax.set_title('10163 GT-only controlled-material physics drive — joint state trace\nNot an AI prediction result')
 line,=ax.plot([],[],color='#2056a8',lw=2,label='actual joint position');target,=ax.plot([],[],color='#d66a00',lw=1.4,alpha=.9,label='tensor target request');dot,=ax.plot([],[],'o',color='#2056a8',ms=6);ax.legend(loc='lower right');text=ax.text(.015,.94,'GT C-type hinge | tensor target control | PhysicsScene session layer',transform=ax.transAxes,va='top')
 xs=[];ys=[];ts=[]
 def update(i):
  end=picks[i]; xs.append(end);ys.append(rows[end]['position_rad']);ts.append(rows[end]['requested_target_rad']);line.set_data(xs,ys);target.set_data(xs,ts);dot.set_data([end],[ys[-1]]);text.set_text(f'GT-only physics state trace | record {end+1}/{len(rows)} | position={ys[-1]:.3f} rad');return line,target,dot,text
 update(len(picks)-1);a.poster.parent.mkdir(parents=True,exist_ok=True);fig.savefig(a.poster,bbox_inches='tight');
 anim=FuncAnimation(fig,update,frames=len(picks),interval=100,blit=True);a.mp4.parent.mkdir(parents=True,exist_ok=True);anim.save(a.mp4,writer=FFMpegWriter(fps=10,bitrate=900));plt.close(fig)
if __name__=='__main__':main()
