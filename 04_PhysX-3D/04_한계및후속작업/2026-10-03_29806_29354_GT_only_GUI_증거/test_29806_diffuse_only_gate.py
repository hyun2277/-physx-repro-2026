#!/usr/bin/env python3
"""Offline decision tests for the diffuse-only prephysics gate."""
from pathlib import Path
import numpy as np
from PIL import Image


def decide(rgb, regions, binding=True):
    hsv=np.asarray(Image.fromarray(rgb.astype(np.uint8),'RGB').convert('HSV'))
    cyan=(hsv[:,:,0]>=115)&(hsv[:,:,0]<=155)&(hsv[:,:,1]>=70)&(hsv[:,:,2]>=35)
    nonblack=rgb.max(axis=2)>10
    region_ok=all(r['intersects_frame'] and r['cyan_pixels']>=5 and r['nonblack_ratio']>=0.001 for r in regions.values())
    return binding and int(cyan.sum())>=30 and float(nonblack.mean())>=0.001 and region_ok


def main():
    components={k:{'intersects_frame':True,'cyan_pixels':100,'nonblack_ratio':0.5} for k in ('BASE','gt_C_1','gt_C_2','gt_C_3')}
    cyan=np.zeros((100,100,3),dtype=np.uint8);cyan[10:90,10:90]=[31,173,235]
    assert decide(cyan,components), 'cyan must not fail because RGB door colors are absent'
    assert not decide(np.zeros_like(cyan),{k:{**v,'cyan_pixels':0,'nonblack_ratio':0.0} for k,v in components.items()}), 'black must fail'
    assert not decide(cyan,components,binding=False), 'missing binding must fail'
    off={**components,'gt_C_1':{'intersects_frame':False,'cyan_pixels':0,'nonblack_ratio':0.0}}
    assert not decide(cyan,off), 'offscreen projection must fail distinctly'
    source=Path(__file__).with_name('gui_29806_end_to_end_physics_video.py').read_text()
    assert 'raise_on_fail=not args.diffuse_only_material_diagnostic' in source
    assert 'DIFFUSE_ONLY_PREPHYSICS_INVALID' in source
    assert source.index('DIFFUSE_ONLY_PREPHYSICS_INVALID') < source.index('SimulationManager.initialize_physics()')
    assert 'active_schedule_started":False' in source and 'recorder_started":False' in source
    print('DIFFUSE_ONLY_GATE_TESTS_PASS')

if __name__=='__main__': main()
