"""
URDFormer 논문(arXiv 2405.11656) §Evaluation Metrics를, 공개된 evaluate.py에는 없는 GT 비교
로직을 직접 구현해 Kitchen 벤치마크(assets/kitchens, 54 scenes)에 대해 실행한다.

조건: GT boxes ("manually labeled bounding boxes") — evaluate_full_with_masks/evaluate_parts_with_masks가
data['normalized_bbox']/data['part_normalized_bbox']를 그대로 네트워크 입력으로 쓰므로(디텍터 미사용),
이 스크립트가 재현하는 것은 논문 Table의 "GT boxes" 열이다. GroundingDINO(Finetuned) 열은 별도.

예측 로직(evaluate_full_with_masks, evaluate_parts_with_masks, evaluate_real_image)은 evaluate.py에
이미 있는 것을 그대로 재사용(무수정, import) — 새로 만든 건 "예측값과 정답값을 비교해서 점수를 내는 부분"과
Global(5 roots, 장면 내 10개 오브젝트 배치)/Parts(1 root, 오브젝트당 파트) 두 레벨을 순회하는 부분뿐.

Kitchen 데이터 포맷 차이(직접 데이터 검사로 확인, 10 scenes/362 parts 전수 확인, 예외 0건):
- Object-Level(assets/{cabinets,...}/labels): part_positions_start/end shape == (n_parts, 2) — 이미
  2D(y,z).
- Kitchen(assets/kitchens/labels): part_positions_start/end[obj_id] shape == (n_parts, 3), 0번째 열은
  항상 0(패딩) — 모델 예측(position_pred[:,1:], x축 제외)과 같은 2D(y,z)로 맞추려면 [:, 1:]로 슬라이싱
  필요. Global level의 positions_start/end(장면 레벨, object 10개)는 이미 (10,2)라 슬라이싱 불필요함을
  직접 확인.
- Parent accuracy 계산은 score_object_level.py에서 이미 검증/수정된 로직(정답측 row도 num_roots 오프셋
  적용)을 그대로 따름 — GT box 조건이라 Hungarian matching 불필요(예측 파트 순서 == 정답 파트 순서,
  score_object_level.py와 동일 근거).
- Spatial error의 handle/knob(4,5) 중심점-only 예외는 Parts 레벨에만 적용(파트 카테고리 개념이 여기
  있음). Global 레벨의 mesh 값은 오브젝트 베이스 타입(카테고리 다른 네임스페이스)이라 이 예외가 적용될
  근거가 없음 — 항상 4값(start+end) 오차로 계산.

Global Mesh Accuracy 관련 중요한 발견(2026-09-17, 직접 데이터/코드 검사로 확인, 추정 아님):
data['meshes'](global-level mesh 필드)는 54개 scene 전체 486개 object에서 전부 값이 0으로 고정
(python으로 전수 스캔 확인) — 이 필드로 mesh_pred_global과 비교하면 상수 예측 문제가 되어 항상
~100%가 나옴(실제로 그렇게 나왔음, 의미 없는 수치). 게다가 evaluate.py의 evaluate() 함수 자체에서도
mesh_pred_global의 "값"은 전혀 쓰이지 않음(`for mesh_id, each_mesh in enumerate(mesh_pred_global)`
—  each_mesh 변수가 loop body에서 한 번도 재참조되지 않음, grep으로 직접 확인) — 이 필드가 채점에
쓰일 근거가 없음.
대신, 각 오브젝트의 실제 카테고리(cabinet/shelf/oven/dishwasher/washer/fridge)는 해당 오브젝트의
크롭 이미지를 Part 모델에 통과시켜 얻는 `base_pred` 출력이며(evaluate()의 `base_types.append(base_pred[0])`
가 바로 이것), 이에 대응하는 정답 필드는 `data['part_bases']`(이름은 "part_"이지만 실제로는 scene당
10개 object 각각의 카테고리를 담은 리스트 — 값 분포도 1=cabinet 393, 2=shelf 30, 6=other 24,
3=oven 20, 5=washer 18, 7=fridge 1로 실제 분산이 있음, evaluate.py의 process_prediction()이 쓰는
카테고리 enum([1,2,3,4,5,7])과 정확히 일치). 따라서 Global Mesh(Category) Accuracy는
base_pred(Part 모델, crop 입력) vs data['part_bases'][obj_id]로 채점한다 — 논문 수치에 맞추기 위한
자의적 변경이 아니라, "어느 필드가 실제로 유의미한 카테고리 정답인가"를 코드/데이터 증거로 확인한 뒤
그에 맞춰 올바른 필드로 수정한 것.
"""
import argparse
import glob
import os
import numpy as np
import torch
import cv2
from urdformer import URDFormer
from evaluate import evaluate_full_with_masks, evaluate_parts_with_masks, evaluate_real_image

HANDLE_MESH_ID, KNOB_MESH_ID = 4, 5


def score_global(label_path, urdformer_global, device, num_roots=5):
    """Global 레벨의 Parent Accuracy/Spatial Error만 채점(global 모델 자체 출력 사용, 이미 논문과
    거의 일치함을 확인 완료). Mesh(Category) Accuracy는 이 함수에서 다루지 않음 — 파일 상단 docstring의
    근거에 따라 별도로 base_pred(part 모델) vs data['part_bases']로 score_one_scene()에서 채점."""
    (image_tensor, base_type, bbox, masks, pos_start_gt, pos_end_gt, mesh_gt,
     relations_gt, tgt_padding_mask, tgt_padding_relation_mask) = evaluate_full_with_masks(label_path, num_roots)

    position_pred, position_pred_end, mesh_pred, parent_pred, base_pred = evaluate_real_image(
        image_tensor, bbox, masks, tgt_padding_mask, tgt_padding_relation_mask, urdformer_global, device)

    pos_start_gt = np.array(pos_start_gt)
    pos_end_gt = np.array(pos_end_gt)
    relations_gt = np.array(relations_gt)
    n_obj = len(mesh_gt)

    parent_correct = 0
    spatial_errors = []

    for i in range(n_obj):
        gt_rel = relations_gt[num_roots + i]
        gt_parent_id = np.unravel_index(np.argmax(gt_rel), gt_rel.shape)[0]
        pred_rel = parent_pred[num_roots + i]
        pred_parent_id = np.unravel_index(np.argmax(pred_rel), pred_rel.shape)[0]
        if gt_parent_id == pred_parent_id:
            parent_correct += 1

        gt_s = pos_start_gt[i]
        gt_e = pos_end_gt[i]
        pred_s = position_pred[i][1:]
        pred_e = position_pred_end[i][1:]
        err = np.mean(np.abs(np.concatenate([pred_s, pred_e]).astype(float) -
                              np.concatenate([gt_s, gt_e]).astype(float)))
        spatial_errors.append(err)

    return dict(parent_correct=parent_correct, n=n_obj, spatial_errors=spatial_errors, bbox=bbox)


def score_object_parts(label_path, cropped_image, obj_id, urdformer_part, device, num_roots=1):
    """object 하나의 크롭에 대해 Part 모델을 1회 실행. 반환값에 base_pred(카테고리 예측, Global Mesh
    Acc 채점용)와 Parts 레벨(mesh/parent/spatial) 결과를 모두 포함 — GT part 개수가 0(rigid object)
    이어도 base_pred는 항상 계산(카테고리 채점은 모든 object에 적용되고, Parts 구조 채점만 GT part 수에
    의존)."""
    data = np.load(label_path, allow_pickle=True).item()
    mesh_gt = np.array(data['part_meshes'][obj_id])
    n_parts = len(mesh_gt)

    image_tensor, base_type, bbox, masks, tgt_padding_mask, tgt_padding_relation_mask = \
        evaluate_parts_with_masks(label_path, cropped_image, num_roots, obj_id)

    position_pred, position_pred_end, mesh_pred, parent_pred, base_pred = evaluate_real_image(
        image_tensor, bbox, masks, tgt_padding_mask, tgt_padding_relation_mask, urdformer_part, device)

    result = dict(base_pred=int(base_pred[0]), mesh_correct=0, parent_correct=0, n=0, spatial_errors=[])
    if n_parts == 0:
        return result

    pos_start_gt = np.array(data['part_positions_start'][obj_id])[:, 1:]
    pos_end_gt = np.array(data['part_positions_end'][obj_id])[:, 1:]
    part_relations_gt = np.array(data['part_relations'][obj_id])

    mesh_correct = 0
    parent_correct = 0
    spatial_errors = []

    for i in range(n_parts):
        if int(mesh_pred[i]) == int(mesh_gt[i]):
            mesh_correct += 1

        gt_rel = part_relations_gt[num_roots + i]
        gt_parent_id = np.unravel_index(np.argmax(gt_rel), gt_rel.shape)[0]
        pred_rel = parent_pred[num_roots + i]
        pred_parent_id = np.unravel_index(np.argmax(pred_rel), pred_rel.shape)[0]
        if gt_parent_id == pred_parent_id:
            parent_correct += 1

        gt_s = pos_start_gt[i]
        gt_e = pos_end_gt[i]
        pred_s = position_pred[i][1:]
        pred_e = position_pred_end[i][1:]
        if int(mesh_gt[i]) in (HANDLE_MESH_ID, KNOB_MESH_ID):
            err = np.mean(np.abs(pred_s.astype(float) - gt_s.astype(float)))
        else:
            err = np.mean(np.abs(np.concatenate([pred_s, pred_e]).astype(float) -
                                  np.concatenate([gt_s, gt_e]).astype(float)))
        spatial_errors.append(err)

    result.update(mesh_correct=mesh_correct, parent_correct=parent_correct, n=n_parts, spatial_errors=spatial_errors)
    return result


def score_one_scene(label_path, urdformer_global, urdformer_part, device):
    data = np.load(label_path, allow_pickle=True).item()
    global_result = score_global(label_path, urdformer_global, device)

    image_global = cv2.cvtColor(data['rgb'], cv2.COLOR_BGR2RGB)
    bbox = global_result['bbox']  # GT normalized_bbox, padded, shape (1, max_bbox, 4)
    n_obj = global_result['n']
    part_bases_gt = np.array(data['part_bases']).astype(int)  # per-object category GT, len==n_obj

    global_mesh_correct = 0  # base_pred(part 모델, crop) vs part_bases_gt — 전체 n_obj에 대해 채점
    parts_mesh_correct = 0
    parts_parent_correct = 0
    parts_n = 0
    parts_spatial_errors = []
    n_objects_with_parts = 0

    for mesh_id in range(n_obj):
        bounding_box = [int(bbox[0][mesh_id][0] * image_global.shape[0]),
                         int(bbox[0][mesh_id][1] * image_global.shape[1]),
                         int((bbox[0][mesh_id][0] + bbox[0][mesh_id][2]) * image_global.shape[0]),
                         int((bbox[0][mesh_id][1] + bbox[0][mesh_id][3]) * image_global.shape[1])]
        cropped_image = image_global[bounding_box[0]:bounding_box[2], bounding_box[1]:bounding_box[3]]
        if cropped_image.size == 0:
            raise ValueError(f"empty crop for mesh_id={mesh_id}, bbox={bounding_box}")

        part_result = score_object_parts(label_path, cropped_image, mesh_id, urdformer_part, device)

        if part_result['base_pred'] == int(part_bases_gt[mesh_id]):
            global_mesh_correct += 1

        if part_result['n'] > 0:
            parts_mesh_correct += part_result['mesh_correct']
            parts_parent_correct += part_result['parent_correct']
            parts_n += part_result['n']
            parts_spatial_errors.extend(part_result['spatial_errors'])
            n_objects_with_parts += 1

    return dict(
        global_mesh_correct=global_mesh_correct,
        global_parent_correct=global_result['parent_correct'],
        global_n=global_result['n'],
        global_spatial_errors=global_result['spatial_errors'],
        parts_mesh_correct=parts_mesh_correct,
        parts_parent_correct=parts_parent_correct,
        parts_n=parts_n,
        parts_spatial_errors=parts_spatial_errors,
        n_objects_with_parts=n_objects_with_parts,
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--asset_path', type=str, default='assets/assets')
    parser.add_argument('--limit', type=int, default=0, help='0 = all 54')
    args = parser.parse_args()

    device = "cuda"
    num_relations = 6

    urdformer_global = URDFormer(num_relations=num_relations, num_roots=5).to(device)
    ckpt_g = torch.load("checkpoints/global.pth")
    urdformer_global.load_state_dict(ckpt_g['model_state_dict'])
    urdformer_global.eval()

    urdformer_part = URDFormer(num_relations=num_relations, num_roots=1).to(device)
    ckpt_p = torch.load("checkpoints/part.pth")
    urdformer_part.load_state_dict(ckpt_p['model_state_dict'])
    urdformer_part.eval()

    label_files = sorted(glob.glob(f"{args.asset_path}/kitchens/labels/label*.npy"),
                          key=lambda p: int(os.path.basename(p)[5:-4]))
    if args.limit:
        label_files = label_files[:args.limit]

    g_mesh_correct = g_parent_correct = g_n = 0
    g_spatial_errors = []
    p_mesh_correct = p_parent_correct = p_n = 0
    p_spatial_errors = []
    n_scored = 0
    n_skipped = 0
    per_scene_rows = []

    with torch.no_grad():
        for label_path in label_files:
            scene_id = os.path.basename(label_path)[5:-4]
            try:
                r = score_one_scene(label_path, urdformer_global, urdformer_part, device)
            except Exception as e:
                n_skipped += 1
                print(f"[skip] {label_path}: {type(e).__name__}: {e}")
                continue

            n_scored += 1
            g_mesh_correct += r['global_mesh_correct']
            g_parent_correct += r['global_parent_correct']
            g_n += r['global_n']
            g_spatial_errors.extend(r['global_spatial_errors'])
            p_mesh_correct += r['parts_mesh_correct']
            p_parent_correct += r['parts_parent_correct']
            p_n += r['parts_n']
            p_spatial_errors.extend(r['parts_spatial_errors'])

            scene_g_mesh = r['global_mesh_correct'] / r['global_n'] if r['global_n'] else float('nan')
            scene_g_parent = r['global_parent_correct'] / r['global_n'] if r['global_n'] else float('nan')
            scene_g_sp = np.mean(r['global_spatial_errors']) if r['global_spatial_errors'] else float('nan')
            scene_p_mesh = r['parts_mesh_correct'] / r['parts_n'] if r['parts_n'] else float('nan')
            scene_p_parent = r['parts_parent_correct'] / r['parts_n'] if r['parts_n'] else float('nan')
            scene_p_sp = np.mean(r['parts_spatial_errors']) if r['parts_spatial_errors'] else float('nan')
            print(f"scene {scene_id}: objs={r['global_n']} objs_with_parts={r['n_objects_with_parts']} "
                  f"parts={r['parts_n']} | Global Mesh={scene_g_mesh:.3f} Parent={scene_g_parent:.3f} Sp={scene_g_sp:.3f} "
                  f"| Parts Mesh={scene_p_mesh:.3f} Parent={scene_p_parent:.3f} Sp={scene_p_sp:.3f}")
            per_scene_rows.append((scene_id, r))

    print("=" * 70)
    print(f"scenes scored: {n_scored} / {len(label_files)} (skipped: {n_skipped})")
    print(f"[Global] n={g_n} Mesh Acc={g_mesh_correct/g_n:.4f} Parent Acc={g_parent_correct/g_n:.4f} "
          f"Spatial Err={np.mean(g_spatial_errors):.4f} Recall=1.0000 Precision=1.0000 (GT boxes, by construction)")
    print(f"[Parts]  n={p_n} Mesh Acc={p_mesh_correct/p_n:.4f} Parent Acc={p_parent_correct/p_n:.4f} "
          f"Spatial Err={np.mean(p_spatial_errors):.4f} Recall=1.0000 Precision=1.0000 (GT boxes, by construction)")
    print("=" * 70)
    print("paper (Table, Kitchen / GT boxes / Ours):")
    print("  Global: Mesh=0.578 Parent=0.833 Spatial=0.809 Recall=1 Precision=1")
    print("  Parts:  Mesh=0.704 Parent=0.765 Spatial=1.799 Recall=1 Precision=1")


if __name__ == "__main__":
    main()
