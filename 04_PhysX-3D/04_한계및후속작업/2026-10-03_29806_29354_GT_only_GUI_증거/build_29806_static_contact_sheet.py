"""Build a small six-view sheet; does not infer human-visible cabinet correctness."""
import argparse, hashlib, json
from pathlib import Path
from PIL import Image, ImageDraw, ImageStat

p=argparse.ArgumentParser(); p.add_argument('--run-dir',type=Path,required=True); a=p.parse_args()
report=json.loads((a.run_dir/'static_mapping_gate.json').read_text())
rows=[]; thumbs=[]
for camera in report['camera']['candidates']:
    path=Path(camera['capture']); image=Image.open(path).convert('RGB'); stats=ImageStat.Stat(image)
    thumb=image.copy(); thumb.thumbnail((640,360)); thumbs.append((camera['label'],thumb))
    rows.append({'label':camera['label'],'path':str(path),'bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'size':list(image.size),'rgb_mean':stats.mean,'rgb_stddev':stats.stddev,'completely_black':max(x[1] for x in image.getextrema())==0})
w=max(x.width for _,x in thumbs); h=max(x.height for _,x in thumbs)+32
sheet=Image.new('RGB',(w*2,h*3),(20,20,20)); draw=ImageDraw.Draw(sheet)
for i,(label,image) in enumerate(thumbs):
    x=(i%2)*w; y=(i//2)*h; sheet.paste(image,(x,y+32)); draw.text((x+8,y+8),label,fill=(255,255,255))
sheet_path=a.run_dir/'29806_static_six_view_contact_sheet.png'; sheet.save(sheet_path)
result={'status':'AUTOMATION_CAPTURES_READY_HUMAN_COMPONENT_CHECK_REQUIRED','physics_started':False,'simulation_steps':0,'views':rows,'contact_sheet':{'path':str(sheet_path),'bytes':sheet_path.stat().st_size,'sha256':hashlib.sha256(sheet_path.read_bytes()).hexdigest()},'human_checks':['gray base visible','red gt_C_1 door visible','green gt_C_2 door visible','blue gt_C_3 door visible','three doors occupy distinct positions and match GT source geometry']}
(a.run_dir/'static_capture_validation.json').write_text(json.dumps(result,indent=2)+'\n')
raise SystemExit(0 if all(not r['completely_black'] for r in rows) else 2)
