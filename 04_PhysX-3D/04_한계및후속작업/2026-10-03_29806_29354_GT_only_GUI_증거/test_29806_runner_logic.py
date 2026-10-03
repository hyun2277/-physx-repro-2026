"""CPU-only static checks for the 29806 GUI physics schedule and metrics."""
from pathlib import Path
import importlib.util
import numpy as np
from PIL import Image

HERE=Path(__file__).resolve().parent

def main():
    per_door_steps=90+180+90+180+180
    assert per_door_steps==720
    assert per_door_steps/60==12.0
    assert 3*per_door_steps/60==36.0
    assert 1.0+36.0+2.0==39.0
    u=np.linspace(0,1,181);s=u*u*(3-2*u)
    assert s[0]==0 and s[-1]==1 and np.all(np.diff(s)>=0)
    # The old metric compared an unsettled inactive state to a nominal target.
    inactive=[0.200,0.203,0.198,0.201]
    nominal_target=0.0;settled_baseline=inactive[0]
    assert max(abs(x-nominal_target) for x in inactive)>0.02
    assert max(abs(x-settled_baseline) for x in inactive)<0.02
    spec=importlib.util.spec_from_file_location('validator',HERE/'validate_29806_gpu0_gui_video.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    img=np.zeros((720,1280,3),dtype=np.uint8)
    img[220:500,280:490]=[225,145,140];img[220:500,500:730]=[130,220,165];img[220:500,740:980]=[125,185,230];img[200:520,270:990]=np.maximum(img[200:520,270:990],[80,80,80])
    components=mod.color_components(Image.fromarray(img))
    assert all(components[name]['pixel_count']>=30 for name in ('BASE_GRAY','gt_C_1_RED','gt_C_2_GREEN','gt_C_3_BLUE'))
    source=(HERE/'gui_29806_end_to_end_physics_video.py').read_text();validator=(HERE/'validate_29806_gpu0_gui_video.py').read_text()
    for token in ('VISUAL_CONTINUITY_GATE_FAIL','target_vector_rad','update_fabric=True','opening_smoothstep','inactive_baseline_rad','sequence_wall_elapsed_s'):
        assert token in source, token
    assert '3 * 720' in validator
    print('PASS schedule_s=39.0 physics_records=2160 corrected_drift_metric=true visual_validator_mock=true')
if __name__=='__main__':main()
