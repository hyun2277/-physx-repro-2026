"""
Object-Level 벤치마크를 GroundingDINO 자동 탐지 조건("Finetuned Grounding DINO" 열, 논문 표)으로 채점.
GT박스 조건(score_object_level.py)과 달리, 예측 박스 개수/순서가 정답과 다를 수 있어
IoU 기반 Hungarian matching으로 정렬한 뒤 category/parent/spatial 지표 + recall/precision을 계산.

원본 코드(detector, post_processing, evaluate_real_image 등)는 무수정 재사용.
카테고리별 GroundingDINO 프롬프트(cabinet/oven/dishwasher/fridge/washer)는 grounding_dino/detection.py의
detector() 함수가 이미 정의해둔 것을 그대로 사용(scene_type 인자로 자동 선택됨) — 임의로 새 프롬프트를
만들지 않음.
"""
import argparse
import glob
import os
import numpy as np
import torch
import PIL
from PIL import Image
from scipy.optimize import linear_sum_assignment
from urdformer import URDFormer
import torchvision.transforms as transforms

from utils import detection_config
from grounding_dino.detection import detector
from grounding_dino.post_processing import post_processing

from score_object_level import evaluate_parts_with_masks, evaluate_real_image

# assets 폴더명(복수형) -> detector()가 기대하는 scene_type(단수형), detection.py 원문 그대로
CATEGORY_TO_SCENE_TYPE = {
    'cabinets': 'cabinet',
    'ovens': 'oven',
    'dishwashers': 'dishwasher',
    'fridges': 'fridge',
    'washers': 'washer',
}


def normalized_to_xyxy(box, w, h):
    y0, x0, dy, dx = box
    return [x0 * w, y0 * h, (x0 + dx) * w, (y0 + dy) * h]


def iou_xyxy(a, b):
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    ix0, iy0 = max(ax0, bx0), max(ay0, by0)
    ix1, iy1 = min(ax1, bx1), min(ay1, by1)
    iw, ih = max(0.0, ix1 - ix0), max(0.0, iy1 - iy0)
    inter = iw * ih
    area_a = max(0.0, ax1 - ax0) * max(0.0, ay1 - ay0)
    area_b = max(0.0, bx1 - bx0) * max(0.0, by1 - by0)
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


def run_detection_for_category(category, image_dir, min_iou_ignore=None):
    scene_type = CATEGORY_TO_SCENE_TYPE[category]
    args = argparse.Namespace(scene_type=scene_type, image_path=image_dir)
    detection_args = detection_config(args)
    detector(scene_type, detection_args)
    label_dir = 'grounding_dino/labels'
    save_dir = f'grounding_dino/labels_filtered_auto/{category}'
    os.makedirs(save_dir, exist_ok=True)
    post_processing(label_dir, image_dir, save_dir)
    return save_dir


def score_one_image_autodetect(pred_label_path, gt_label_path, image_path, urdformer_part, device, num_roots=1):
    pred_data = np.load(pred_label_path, allow_pickle=True).item()
    gt_data = np.load(gt_label_path, allow_pickle=True).item()

    pred_boxes_norm = pred_data['part_normalized_bbox']
    gt_boxes_norm = gt_data['part_normalized_bbox']

    n_pred = len(pred_boxes_norm)
    n_gt = len(gt_boxes_norm)

    result = {
        'n_pred': n_pred, 'n_gt': n_gt, 'n_matched': 0,
        'mesh_correct': 0, 'parent_correct': 0, 'spatial_errors': [],
    }

    if n_pred == 0 or n_gt == 0:
        return result

    # IoU matrix (정규화 좌표 그대로 써도 비율은 동일하므로 w=h=1로 계산 가능)
    iou_mat = np.zeros((n_pred, n_gt))
    for i, pb in enumerate(pred_boxes_norm):
        pb_xyxy = normalized_to_xyxy(pb, 1.0, 1.0)
        for j, gb in enumerate(gt_boxes_norm):
            gb_xyxy = normalized_to_xyxy(gb, 1.0, 1.0)
            iou_mat[i, j] = iou_xyxy(pb_xyxy, gb_xyxy)

    # Hungarian matching (비용 = 1-IoU 최소화 = IoU 합 최대화)
    row_ind, col_ind = linear_sum_assignment(1.0 - iou_mat)
    matches = [(r, c) for r, c in zip(row_ind, col_ind) if iou_mat[r, c] > 0.0]
    result['n_matched'] = len(matches)

    if len(matches) == 0:
        return result

    # 예측 박스를 네트워크 입력으로 사용 (GT박스 아님 -- 이게 이 조건의 핵심)
    image = np.array(Image.open(image_path).convert("RGB"))
    image_tensor, bbox, masks, tgt_padding_mask, tgt_padding_relation_mask = evaluate_parts_with_masks(
        pred_label_path, image)
    position_pred, position_pred_end, mesh_pred, parent_pred, base_pred = evaluate_real_image(
        image_tensor, bbox, masks, tgt_padding_mask, tgt_padding_relation_mask, urdformer_part, device)

    mesh_gt = np.array(gt_data['part_meshes'])
    pos_start_gt = np.array(gt_data['part_positions_start'])
    pos_end_gt = np.array(gt_data['part_positions_end'])
    part_relations_gt = np.array(gt_data['part_relations'])

    HANDLE_MESH_ID, KNOB_MESH_ID = 4, 5

    # 버그 수정(2026-09-16, 사용자 지시로 발견): 자동탐지 조건에서는 예측 박스 순서가 정답 박스
    # 순서와 다름(GroundingDINO 탐지 순서는 정답 라벨링 순서와 무관) — 직접 샘플(test0)로 확인:
    # pred박스0(손잡이)가 pred박스2(문)를 parent로 가리키는데, pred박스2는 GT박스0(문)에 매칭되고
    # GT박스1(손잡이)의 실제 parent도 GT박스0 — 매핑하면 정확한 예측인데, "예측 인덱스"와 "정답
    # 인덱스"를 그대로 비교했더니(3 vs 1) 틀렸다고 오채점되고 있었음. 예측 parent가 가리키는 대상이
    # "예측 집합의 몇 번째 박스"인지 먼저 알아낸 뒤, 그 예측 박스가 매칭된 정답 박스 번호로 변환해서
    # 비교해야 함. parent=root(인덱스 < num_roots)는 두 집합에서 공유되는 값이라 그대로 비교해도 됨.
    pred_to_gt = {p: g for p, g in matches}

    for pred_idx, gt_idx in matches:
        if int(mesh_pred[pred_idx]) == int(mesh_gt[gt_idx]):
            result['mesh_correct'] += 1

        gt_rel = part_relations_gt[num_roots + gt_idx]
        gt_parent_raw = np.unravel_index(np.argmax(gt_rel), gt_rel.shape)[0]  # GT 공간의 인덱스

        pred_rel = parent_pred[num_roots + pred_idx]
        pred_parent_raw = np.unravel_index(np.argmax(pred_rel), pred_rel.shape)[0]  # 예측 공간의 인덱스

        if pred_parent_raw < num_roots and gt_parent_raw < num_roots:
            # 둘 다 "루트(물체 본체)"를 가리킴 -- 루트 인덱스는 두 공간에서 동일한 의미이므로 그대로 비교
            parent_ok = (pred_parent_raw == gt_parent_raw)
        elif pred_parent_raw < num_roots or gt_parent_raw < num_roots:
            # 한쪽만 루트를 가리키면 무조건 불일치
            parent_ok = False
        else:
            # 둘 다 "다른 파트"를 가리킴 -- 예측이 가리키는 예측-파트 인덱스를,
            # 그 예측-파트가 매칭된 정답-파트 인덱스로 변환한 뒤 비교
            pred_parent_part_idx = pred_parent_raw - num_roots  # 예측 집합 내 인덱스
            gt_parent_part_idx = gt_parent_raw - num_roots      # 정답 집합 내 인덱스
            mapped_gt_idx = pred_to_gt.get(pred_parent_part_idx, None)
            parent_ok = (mapped_gt_idx is not None and mapped_gt_idx == gt_parent_part_idx)

        if parent_ok:
            result['parent_correct'] += 1

        gt_start = pos_start_gt[gt_idx]
        gt_end = pos_end_gt[gt_idx]
        pred_start = position_pred[pred_idx][1:]
        pred_end = position_pred_end[pred_idx][1:]
        if int(mesh_gt[gt_idx]) in (HANDLE_MESH_ID, KNOB_MESH_ID):
            err = np.mean(np.abs(pred_start.astype(float) - gt_start.astype(float)))
        else:
            err = np.mean(np.abs(np.concatenate([pred_start, pred_end]).astype(float) -
                                  np.concatenate([gt_start, gt_end]).astype(float)))
        result['spatial_errors'].append(err)

    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--category', type=str, default='all')
    parser.add_argument('--asset_path', type=str, default='assets/assets')
    args = parser.parse_args()

    device = "cuda"
    urdformer_part = URDFormer(num_relations=6, num_roots=1)
    urdformer_part = urdformer_part.to(device)
    checkpoint = torch.load("checkpoints/part.pth")
    urdformer_part.load_state_dict(checkpoint['model_state_dict'])
    urdformer_part.eval()

    categories = list(CATEGORY_TO_SCENE_TYPE.keys()) if args.category == 'all' else [args.category]

    grand = dict(n_pred=0, n_gt=0, n_matched=0, mesh_correct=0, parent_correct=0, spatial_errors=[], n_images=0)

    with torch.no_grad():
        for cat in categories:
            image_dir = f"{args.asset_path}/{cat}/images"
            print(f"=== running GroundingDINO detection for category={cat} (scene_type={CATEGORY_TO_SCENE_TYPE[cat]}) ===")
            pred_dir = run_detection_for_category(cat, image_dir)

            label_files = sorted(glob.glob(f"{args.asset_path}/{cat}/labels/label*.npy"))
            cat_stats = dict(n_pred=0, n_gt=0, n_matched=0, mesh_correct=0, parent_correct=0, spatial_errors=[], n_images=0)

            for label_path in label_files:
                test_id = os.path.basename(label_path)[5:-4]
                image_path = f"{image_dir}/test{test_id}.jpg"
                pred_label_path = f"{pred_dir}/test{test_id}.npy"
                if not os.path.exists(image_path) or not os.path.exists(pred_label_path):
                    print(f"[skip] missing pred/image for test{test_id} in {cat}")
                    continue
                r = score_one_image_autodetect(pred_label_path, label_path, image_path, urdformer_part, device)
                for k in ('n_pred', 'n_gt', 'n_matched', 'mesh_correct', 'parent_correct'):
                    cat_stats[k] += r[k]
                cat_stats['spatial_errors'].extend(r['spatial_errors'])
                cat_stats['n_images'] += 1

            print("=" * 60)
            print(f"[AUTO-DETECT] category: {cat}")
            print(f"images: {cat_stats['n_images']}")
            print(f"n_pred_boxes: {cat_stats['n_pred']}, n_gt_boxes: {cat_stats['n_gt']}, n_matched: {cat_stats['n_matched']}")
            if cat_stats['n_gt'] > 0:
                print(f"Recall: {cat_stats['n_matched']/cat_stats['n_gt']:.4f}")
            if cat_stats['n_pred'] > 0:
                print(f"Precision: {cat_stats['n_matched']/cat_stats['n_pred']:.4f}")
            if cat_stats['n_matched'] > 0:
                print(f"Mesh(category) Accuracy (matched only): {cat_stats['mesh_correct']/cat_stats['n_matched']:.4f}")
                print(f"Parent Accuracy (matched only): {cat_stats['parent_correct']/cat_stats['n_matched']:.4f}")
                print(f"Spatial Error (matched only): {np.mean(cat_stats['spatial_errors']):.4f}")
            print("=" * 60)

            for k in ('n_pred', 'n_gt', 'n_matched', 'mesh_correct', 'parent_correct', 'n_images'):
                grand[k] += cat_stats[k]
            grand['spatial_errors'].extend(cat_stats['spatial_errors'])

    if args.category == 'all':
        print("#" * 60)
        print(f"[AUTO-DETECT] GRAND TOTAL across {categories}")
        print(f"images: {grand['n_images']}")
        print(f"n_pred_boxes: {grand['n_pred']}, n_gt_boxes: {grand['n_gt']}, n_matched: {grand['n_matched']}")
        print(f"Recall: {grand['n_matched']/grand['n_gt']:.4f}")
        print(f"Precision: {grand['n_matched']/grand['n_pred']:.4f}")
        print(f"Mesh(category) Accuracy (matched only): {grand['mesh_correct']/grand['n_matched']:.4f}")
        print(f"Parent Accuracy (matched only): {grand['parent_correct']/grand['n_matched']:.4f}")
        print(f"Spatial Error (matched only): {np.mean(grand['spatial_errors']):.4f}")
        print("#" * 60)


if __name__ == "__main__":
    main()
