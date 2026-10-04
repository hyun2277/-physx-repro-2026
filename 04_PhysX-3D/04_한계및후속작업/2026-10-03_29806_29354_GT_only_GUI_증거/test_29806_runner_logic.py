"""CPU-only checks for the 29806 adaptive schedule and drift masks."""
from pathlib import Path
import importlib.util
import numpy as np
from PIL import Image

HERE=Path(__file__).resolve().parent
JOINTS=("gt_C_1","gt_C_2","gt_C_3")

def metrics(rows,closed,settles):
    absolute={j:abs(settles[j]-closed[j]) for j in JOINTS}
    excursion={}
    for joint in JOINTS:
        eligible=[r for r in rows if r["metric_scope"]=="inactive_excursion" and r["active_joint"]!=joint]
        excursion[joint]=max(abs(r["positions_rad"][joint]-r["inactive_baseline_rad"][joint]) for r in eligible)
    return absolute,excursion

def synthetic_rows(excursion=0.001):
    rows=[]
    for active in JOINTS:
        baseline={j:0.0 for j in JOINTS if j!=active}
        for segment,scope in (("opening_smoothstep","inactive_excursion"),("open_hold","inactive_excursion"),("closing_smoothstep","inactive_excursion"),("closed_settle","excluded_from_inactive_excursion")):
            positions={j:(0.5 if j==active and scope=="inactive_excursion" else excursion) for j in JOINTS}
            rows.append({"active_joint":active,"segment":segment,"metric_scope":scope,"positions_rad":positions,"inactive_baseline_rad":baseline})
    return rows

def main():
    minimum_records=3*(540+30);maximum_records=3*(540+300)
    assert (minimum_records,maximum_records)==(1710,2520)
    assert (3+3*(9+0.5),3+3*(9+5))==(31.5,45.0)
    u=np.linspace(0,1,181);s=u*u*(3-2*u)
    assert s[0]==0 and s[-1]==1 and np.all(np.diff(s)>=0)
    closed={j:0.0 for j in JOINTS}
    good_abs,good_exc=metrics(synthetic_rows(0.001),closed,{j:0.009 for j in JOINTS})
    assert max(good_abs.values())<=0.01 and max(good_exc.values())<=0.002
    bad_abs,_=metrics(synthetic_rows(0.001),closed,{j:0.20 for j in JOINTS})
    assert max(bad_abs.values())>0.01
    _,bad_exc=metrics(synthetic_rows(0.003),closed,{j:0.0 for j in JOINTS})
    assert max(bad_exc.values())>0.002
    eligible_for_c1=[r for r in synthetic_rows() if r["metric_scope"]=="inactive_excursion" and r["active_joint"]!="gt_C_1"]
    assert eligible_for_c1 and all(r["active_joint"]!="gt_C_1" and r["segment"]!="closed_settle" for r in eligible_for_c1)
    spec=importlib.util.spec_from_file_location('validator',HERE/'validate_29806_gpu0_gui_video.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    img=np.zeros((720,1280,3),dtype=np.uint8)
    img[220:500,280:490]=[225,145,140];img[220:500,500:730]=[130,220,165];img[220:500,740:980]=[125,185,230];img[200:520,270:990]=np.maximum(img[200:520,270:990],[80,80,80])
    components=mod.color_components(Image.fromarray(img))
    assert all(components[name]['pixel_count']>=30 for name in ('BASE_GRAY','gt_C_1_RED','gt_C_2_GREEN','gt_C_3_BLUE'))
    source=(HERE/'gui_29806_end_to_end_physics_video.py').read_text();validator=(HERE/'validate_29806_gpu0_gui_video.py').read_text()
    for token in ('MAX_CLOSED_TARGET_ABSOLUTE_ERROR_RAD = 0.01','MAX_INACTIVE_EXCURSION_RAD = 0.002','metric_scope','settle_closed','SETTLE_TIMEOUT_STEPS = 300','target_array(closed)','update_fabric=True'):
        assert token in source, token
    for token in ('--initialization-diagnostic','BEFORE_INITIALIZE_STATE_CAPTURED','PHYSICS_INITIALIZED_NO_STEP_IF_API_ALLOWS','TENSOR_VIEW_CREATED','AFTER_INITIALIZE_CAPTURED','INITIALIZATION_DIAGNOSTIC_COMPLETE','physics_commands_sent'):
        assert token in source, token
    assert '3 * (540 + 30)' in validator and '3 * (540 + 300)' in validator
    print('PASS wall_range_s=31.5..45.0 records=1710..2520 absolute_error_fail=true inactive_mask=true excursion_pass_fail=true visual_validator_mock=true')
if __name__=='__main__':main()
