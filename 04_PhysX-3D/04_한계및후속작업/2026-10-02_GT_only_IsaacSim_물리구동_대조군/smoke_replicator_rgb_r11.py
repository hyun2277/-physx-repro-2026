"""Three-frame documented Isaac Sim Replicator RGB smoke, GPU 1 selected directly."""
from pathlib import Path
import argparse, asyncio, json, traceback
p=argparse.ArgumentParser(); p.add_argument('--root',type=Path,required=True); p.add_argument('--out',type=Path,required=True); a=p.parse_args(); a.out.mkdir(parents=True,exist_ok=True)
from isaacsim import SimulationApp
app=SimulationApp({'headless':True,'active_cuda_gpus':[1],'physics_gpu':1,'multi_gpu':False}, experience=str(a.root/'repro-records/04_PhysX-3D/04_한계및후속작업/2026-10-02_GT_only_IsaacSim_물리구동_대조군/isaac_minimal_replicator_render_r11.kit'))
try:
 import numpy as np
 from PIL import Image
 import carb.settings
 import isaacsim.core.experimental.utils.app as app_utils
 import isaacsim.core.experimental.utils.stage as stage_utils
 import omni.replicator.core as rep
 async def run():
  await stage_utils.create_new_stage_async()
  rep.orchestrator.set_capture_on_play(False)
  carb.settings.get_settings().set('rtx/post/dlss/execMode',2)
  rep.functional.create.xform(name='World')
  rep.functional.create.dome_light(intensity=1000,parent='/World',name='DomeLight')
  cube=rep.functional.create.cube(parent='/World',name='Cube')
  rep.functional.modify.semantics(cube,{'class':'smoke_cube'},mode='add')
  camera=rep.functional.create.camera(position=(5,5,5),look_at=(0,0,0),parent='/World',name='Camera')
  rp=rep.create.render_product(camera.GetPath(),(512,512),name='SmokeRenderProduct')
  ldr=rep.annotators.get('rgb'); ldr.attach(rp)
  backend=rep.backends.get('DiskBackend'); backend.initialize(output_dir=str(a.out/'writer'))
  writer=rep.writers.get('BasicWriter'); writer.initialize(backend=backend,rgb=True); writer.attach(rp)
  for _ in range(20): await app_utils.update_app_async()
  frames=[]
  for i in range(3):
   await rep.orchestrator.step_async(rt_subframes=16)
   frames.append(np.array(ldr.get_data(),copy=True))
  await rep.orchestrator.wait_until_complete_async()
  writer.detach(); ldr.detach(); rp.destroy()
  return frames
 task=asyncio.ensure_future(run())
 for _ in range(6000):
  app.update()
  if task.done(): break
 if not task.done(): raise RuntimeError('three-frame Replicator smoke did not complete')
 frames=task.result(); rows=[]
 for i,data in enumerate(frames):
  rgb=np.asarray(data)[...,:3]
  Image.fromarray(rgb.astype(np.uint8),'RGB').save(a.out/f'annotator_rgb_{i:02d}.png')
  rows.append({'frame':i,'width':int(rgb.shape[1]),'height':int(rgb.shape[0]),'mean_rgb':rgb.astype(np.float64).mean(axis=(0,1)).tolist(),'variance':float(rgb.astype(np.float64).var()),'min':int(rgb.min()),'max':int(rgb.max())})
 writer_png=sorted((a.out/'writer').rglob('*.png'))
 if len(writer_png)<3: raise RuntimeError(f'BasicWriter wrote {len(writer_png)} PNGs, expected at least 3')
 bad=[r for r in rows if r['max']==0 or r['variance']==0]
 if bad: raise RuntimeError(f'black/constant RGB frames: {bad}')
 print('REPLICATOR_RGB_SMOKE_PASS='+json.dumps({'annotator_pngs':[str(a.out/f'annotator_rgb_{i:02d}.png') for i in range(3)],'writer_png_count':len(writer_png),'frames':rows},sort_keys=True))
except BaseException:
 traceback.print_exc(); raise
finally: app.close()
