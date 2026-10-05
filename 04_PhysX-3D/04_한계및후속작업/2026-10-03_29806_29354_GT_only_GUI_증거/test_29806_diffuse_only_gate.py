#!/usr/bin/env python3
"""Offline decision tests for the diffuse-only prephysics gate."""
import numpy as np
from PIL import Image
from gui_29806_common import diffuse_pixel_decision


def decide(rgb, regions, binding=True):
    hsv=np.asarray(Image.fromarray(rgb.astype(np.uint8),'RGB').convert('HSV'))
    cyan=(hsv[:,:,0]>=115)&(hsv[:,:,0]<=155)&(hsv[:,:,1]>=70)&(hsv[:,:,2]>=35)
    nonblack=rgb.max(axis=2)>10
    return diffuse_pixel_decision(int(cyan.sum()),float(nonblack.mean()),regions,binding_pass=binding)


def main():
    components={k:{'intersects_frame':True,'cyan_pixels':100,'nonblack_ratio':0.5} for k in ('BASE','gt_C_1','gt_C_2','gt_C_3')}
    cyan=np.zeros((100,100,3),dtype=np.uint8);cyan[10:90,10:90]=[31,173,235]
    assert decide(cyan,components), 'cyan must not fail because RGB door colors are absent'
    assert not decide(np.zeros_like(cyan),{k:{**v,'cyan_pixels':0,'nonblack_ratio':0.0} for k,v in components.items()}), 'black must fail'
    assert not decide(cyan,components,binding=False), 'missing binding must fail'
    off={**components,'gt_C_1':{'intersects_frame':False,'cyan_pixels':0,'nonblack_ratio':0.0}}
    assert not decide(cyan,off), 'offscreen projection must fail distinctly'
    print('DIFFUSE_ONLY_GATE_TESTS_PASS')

if __name__=='__main__': main()
