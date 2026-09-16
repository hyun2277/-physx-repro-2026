"""
진단 전용 스크립트(score_kitchen.py를 수정하지 않음) — Kitchen Global Spatial Error 잔여 차이의
원인 후보 중 하나(축 선택 모호성)가 실제로 오차 크기에 얼마나 영향을 주는지 정량적으로 확인.
논문 수치에 맞추기 위해 채점 스크립트를 바꾸는 것이 아니라, "축 선택에 따라 오차가 얼마나 민감한가"
를 사실로서 기록하기 위한 목적. 어떤 조합이 논문과 가장 가깝든 그것을 채택하지 않는다.
"""
import glob
import os
import numpy as np
import torch
from urdformer import URDFormer
from evaluate import evaluate_full_with_masks, evaluate_real_image

device = "cuda"
urdformer_global = URDFormer(num_relations=6, num_roots=5).to(device)
ckpt = torch.load("checkpoints/global.pth")
urdformer_global.load_state_dict(ckpt['model_state_dict'])
urdformer_global.eval()

files = sorted(glob.glob("assets/assets/kitchens/labels/label*.npy"),
               key=lambda p: int(os.path.basename(p)[5:-4]))

variants = {
    'drop_x(idx1,2)_CURRENT': (1, 2),
    'drop_y(idx0,2)': (0, 2),
    'drop_z(idx0,1)': (0, 1),
}
errors = {k: [] for k in variants}
per_axis_abs_err = {0: [], 1: [], 2: []}  # raw per-axis abs error (x,y,z), pooled start+end

with torch.no_grad():
    for label_path in files:
        (image_tensor, base_type, bbox, masks, pos_start_gt, pos_end_gt, mesh_gt,
         relations_gt, tgt_padding_mask, tgt_padding_relation_mask) = evaluate_full_with_masks(label_path, 5)
        position_pred, position_pred_end, mesh_pred, parent_pred, base_pred = evaluate_real_image(
            image_tensor, bbox, masks, tgt_padding_mask, tgt_padding_relation_mask, urdformer_global, device)

        pos_start_gt = np.array(pos_start_gt)
        pos_end_gt = np.array(pos_end_gt)
        n_obj = len(mesh_gt)

        for i in range(n_obj):
            gt_s = pos_start_gt[i].astype(float)
            gt_e = pos_end_gt[i].astype(float)
            full_s = position_pred[i].astype(float)   # 3 axes
            full_e = position_pred_end[i].astype(float)

            for name, (a0, a1) in variants.items():
                pred_s = full_s[[a0, a1]]
                pred_e = full_e[[a0, a1]]
                err = np.mean(np.abs(np.concatenate([pred_s, pred_e]) - np.concatenate([gt_s, gt_e])))
                errors[name].append(err)

            # per-axis diagnostic: compare each predicted axis independently against BOTH gt columns
            # and record the smaller of the two (best-case alignment) - purely descriptive, not used
            # to pick a convention.
            for ax in range(3):
                d_start = min(abs(full_s[ax] - gt_s[0]), abs(full_s[ax] - gt_s[1]))
                d_end = min(abs(full_e[ax] - gt_e[0]), abs(full_e[ax] - gt_e[1]))
                per_axis_abs_err[ax].append((d_start + d_end) / 2)

print("=" * 70)
print(f"scenes: {len(files)}")
for name, errs in errors.items():
    print(f"{name}: mean spatial error = {np.mean(errs):.4f}  (n={len(errs)})")
print("-" * 70)
print("paper (Kitchen, GT boxes, Global, Spatial Err, Ours): 0.809")
print("=" * 70)
print("per-axis best-case alignment diagnostic (lower = this axis's values are closer to *some* GT column):")
for ax, name in [(0, 'x'), (1, 'y'), (2, 'z')]:
    print(f"  axis {name}: mean best-case abs diff = {np.mean(per_axis_abs_err[ax]):.4f}")
