"""
URDFormer 논문(arXiv 2405.11656) §Evaluation Metrics에 설명된 채점 방법(category accuracy,
parent accuracy, spatial error)을, 공개된 evaluate.py에는 빠져 있는 비교 로직을 직접 구현해
Object-Level 벤치마크(assets/{category}, ground-truth 박스를 입력으로 사용)에 대해 실행한다.

- 예측 로직(evaluate_real_image, evaluate_parts_with_masks)은 demo.py/evaluate.py에 이미 있는
  것을 그대로 재사용(무수정) — 새로 만든 건 "예측값과 정답값을 비교해서 점수를 내는 부분"뿐.
- 입력 박스가 정답(ground-truth) 박스이므로(논문의 "manually labeled bounding boxes" 조건과 동일
  하게, GroundingDINO 탐지 없이 정답 박스를 그대로 네트워크 입력으로 사용), 예측 파트와 정답 파트가
  이미 같은 인덱스로 1:1 정렬되어 있어 별도 Hungarian matching이 필요 없음(논문 §Evaluation Metrics의
  "먼저 IoU로 정렬해야 한다"는 절차는 GroundingDINO 조건에서만 필요, 이 스크립트가 재현하는 GT-box
  조건에서는 해당 없음 — 이는 평가 조건의 성격상 당연한 것이며 지어낸 단순화가 아님).
"""
import argparse
import numpy as np
import torch
import PIL
from PIL import Image
from urdformer import URDFormer
import torchvision.transforms as transforms


def image_transform():
    normalize = transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
    return transforms.Compose([transforms.Resize(224), transforms.ToTensor(), normalize])


def evaluate_parts_with_masks(data_path, cropped_image):
    max_bbox = 32
    data = np.load(data_path, allow_pickle=True).item()
    img_pil = PIL.Image.fromarray(cropped_image).resize((224, 224))
    img_transform = image_transform()
    image_tensor = img_transform(img_pil)

    bbox = []
    resized_mask = []
    for boxid, each_bbox in enumerate(data['part_normalized_bbox']):
        bbox.append(each_bbox)
        resized_mask.append(np.zeros((14, 14)))
    padded_bbox = np.zeros((max_bbox, 4))
    padded_bbox[:len(bbox)] = bbox
    padded_masks = np.zeros((max_bbox, 14, 14))
    padded_masks[:len(resized_mask)] = resized_mask

    tgt_padding_mask = torch.ones([max_bbox])
    tgt_padding_mask[:len(bbox)] = 0.0
    tgt_padding_mask = tgt_padding_mask.bool()

    num_roots = 1
    tgt_padding_relation_mask = torch.ones([max_bbox + num_roots])
    tgt_padding_relation_mask[:len(bbox) + num_roots] = 0.0
    tgt_padding_relation_mask = tgt_padding_relation_mask.bool()

    return image_tensor, np.array([padded_bbox]), np.array([padded_masks]), tgt_padding_mask, tgt_padding_relation_mask


def evaluate_real_image(image_tensor, bbox, masks, tgt_padding_mask, tgt_padding_relation_mask, urdformer, device):
    rgb_input = image_tensor.float().to(device).unsqueeze(0)
    bbox_input = torch.tensor(bbox).float().to(device).unsqueeze(0)
    masks_input = torch.tensor(masks).float().to(device).unsqueeze(0)

    tgt_padding_mask_inv = torch.logical_not(tgt_padding_mask)
    tgt_padding_mask_inv = torch.tensor(tgt_padding_mask_inv).to(device).unsqueeze(0)

    tgt_padding_relation_mask_inv = torch.logical_not(tgt_padding_relation_mask)
    tgt_padding_relation_mask_inv = torch.tensor(tgt_padding_relation_mask_inv).to(device).unsqueeze(0)

    position_x_pred, position_y_pred, position_z_pred, position_x_end_pred, position_y_end_pred, position_z_end_pred, mesh_pred, parent_cls, base_pred = urdformer(
        rgb_input, bbox_input, masks_input, 2)

    position_pred_x = position_x_pred[tgt_padding_mask_inv].argmax(dim=1)
    position_pred_y = position_y_pred[tgt_padding_mask_inv].argmax(dim=1)
    position_pred_z = position_z_pred[tgt_padding_mask_inv].argmax(dim=1)
    position_pred_x_end = position_x_end_pred[tgt_padding_mask_inv].argmax(dim=1)
    position_pred_y_end = position_y_end_pred[tgt_padding_mask_inv].argmax(dim=1)
    position_pred_z_end = position_z_end_pred[tgt_padding_mask_inv].argmax(dim=1)
    mesh_pred = mesh_pred[tgt_padding_mask_inv].argmax(dim=1)
    base_pred = base_pred.argmax(dim=1)
    parent_pred = parent_cls[tgt_padding_relation_mask_inv]

    position_pred = torch.stack([position_pred_x, position_pred_y, position_pred_z]).T
    position_pred_end = torch.stack([position_pred_x_end, position_pred_y_end, position_pred_z_end]).T

    return (position_pred.detach().cpu().numpy(), position_pred_end.detach().cpu().numpy(),
            mesh_pred.detach().cpu().numpy(), parent_pred.detach().cpu().numpy(), base_pred.detach().cpu().numpy())


def score_one_image(data_path, image_path, urdformer_part, device, num_roots=1):
    data = np.load(data_path, allow_pickle=True).item()
    image = np.array(Image.open(image_path).convert("RGB"))

    image_tensor, bbox, masks, tgt_padding_mask, tgt_padding_relation_mask = evaluate_parts_with_masks(data_path, image)
    position_pred, position_pred_end, mesh_pred, parent_pred, base_pred = evaluate_real_image(
        image_tensor, bbox, masks, tgt_padding_mask, tgt_padding_relation_mask, urdformer_part, device)

    n_parts = len(data['part_meshes'])
    mesh_gt = np.array(data['part_meshes'])
    pos_start_gt = np.array(data['part_positions_start'])  # (n_parts, 3)
    pos_end_gt = np.array(data['part_positions_end'])      # (n_parts, 3)
    part_relations_gt = data['part_relations']              # (n_parts+num_roots, n_parts+num_roots, 6) per-part, OR list

    mesh_correct = 0
    parent_correct = 0
    spatial_errors = []

    for i in range(n_parts):
        # --- category (mesh) accuracy ---
        if int(mesh_pred[i]) == int(mesh_gt[i]):
            mesh_correct += 1

        # --- parent accuracy ---
        # 버그 수정(2026-09-16): row 0(=num_roots 범위)은 루트 자신의 행이라 전부 0(의미 없음).
        # 파트 i의 실제 관계는 row[num_roots+i]에 있음 — 직접 데이터 찍어서 확인(row0 max=0.0,
        # row1/row2에 실제 관계 있음). 예측값 쪽(parent_pred)은 이미 num_roots+i로 맞게 인덱싱했었는데
        # 정답값 쪽만 이 오프셋을 빠뜨렸던 게 버그였음.
        all_rel = np.array(part_relations_gt) if not isinstance(part_relations_gt, np.ndarray) else part_relations_gt
        gt_rel = all_rel[num_roots + i]
        gt_parent_id = np.unravel_index(np.argmax(gt_rel), gt_rel.shape)[0]

        pred_rel = parent_pred[num_roots + i]
        pred_parent_id = np.unravel_index(np.argmax(pred_rel), pred_rel.shape)[0]

        if gt_parent_id == pred_parent_id:
            parent_correct += 1

        # --- spatial error (paper: avg abs error of discretized coords) ---
        # position_pred/position_pred_end from evaluate_real_image already exclude the root-axis
        # dimension in demo.py usage (position_pred_part[:, 1:]) for object-level (2D: y,z bins).
        # GT part_positions_start/end are already 2D (y,z) per part (직접 shape 확인: (n_parts,2)).
        # 모델 예측(position_pred/_end)은 x,y,z 3개 축이라 x(루트축)를 잘라내 GT와 같은 2D로 맞춤.
        gt_start = pos_start_gt[i]
        gt_end = pos_end_gt[i]
        pred_start = position_pred[i][1:]
        pred_end = position_pred_end[i][1:]

        # 버그 수정(2026-09-16): 논문 §Evaluation Metrics 원문 — "For small objects such as handles
        # and knobs, we predict only the object center x1,y1 ... spatial error only considers these
        # two values." part_names(utils.py/demo.py 원문)에서 handle=4, knob=5. 이 두 카테고리는 start
        # 좌표(중심점)만 비교하고, end 좌표는 애초에 논문 정의상 비교 대상이 아님 — 지금까지는 전부
        # start+end 4개 값으로 계산해서 handle/knob에 대해 불필요한 오차가 더해지고 있었음.
        HANDLE_MESH_ID, KNOB_MESH_ID = 4, 5
        if int(mesh_gt[i]) in (HANDLE_MESH_ID, KNOB_MESH_ID):
            err = np.mean(np.abs(pred_start.astype(float) - gt_start.astype(float)))
        else:
            err = np.mean(np.abs(np.concatenate([pred_start, pred_end]).astype(float) -
                                  np.concatenate([gt_start, gt_end]).astype(float)))
        spatial_errors.append(err)

    return mesh_correct, parent_correct, n_parts, spatial_errors


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--category', type=str, default='cabinets')
    parser.add_argument('--asset_path', type=str, default='assets/assets')
    parser.add_argument('--limit', type=int, default=0, help='0 = all')
    args = parser.parse_args()

    device = "cuda"
    num_relations = 6
    urdformer_part = URDFormer(num_relations=num_relations, num_roots=1)
    urdformer_part = urdformer_part.to(device)
    checkpoint = torch.load("checkpoints/part.pth")
    urdformer_part.load_state_dict(checkpoint['model_state_dict'])
    urdformer_part.eval()

    import glob, os
    categories = ['cabinets', 'ovens', 'dishwashers', 'fridges', 'washers'] if args.category == 'all' else [args.category]

    grand_mesh_correct = 0
    grand_parent_correct = 0
    grand_parts = 0
    grand_spatial_errors = []
    grand_images_scored = 0
    grand_images_total = 0

    with torch.no_grad():
        for cat in categories:
            label_files = sorted(glob.glob(f"{args.asset_path}/{cat}/labels/label*.npy"))
            if args.limit:
                label_files = label_files[:args.limit]

            total_mesh_correct = 0
            total_parent_correct = 0
            total_parts = 0
            all_spatial_errors = []
            n_images_scored = 0
            n_images_skipped = 0

            for label_path in label_files:
                test_id = os.path.basename(label_path)[5:-4]  # "label0.npy" -> "0"
                image_path = f"{args.asset_path}/{cat}/images/test{test_id}.jpg"
                if not os.path.exists(image_path):
                    n_images_skipped += 1
                    print(f"[skip] no image for {label_path}")
                    continue
                try:
                    mesh_c, parent_c, n_parts, sp_errs = score_one_image(label_path, image_path, urdformer_part, device)
                except Exception as e:
                    n_images_skipped += 1
                    print(f"[skip] {label_path}: {type(e).__name__}: {e}")
                    continue
                total_mesh_correct += mesh_c
                total_parent_correct += parent_c
                total_parts += n_parts
                all_spatial_errors.extend(sp_errs)
                n_images_scored += 1

            print("=" * 60)
            print(f"category: {cat}")
            print(f"images scored: {n_images_scored} / {len(label_files)} (skipped: {n_images_skipped})")
            print(f"total parts: {total_parts}")
            if total_parts > 0:
                print(f"Mesh(category) Accuracy: {total_mesh_correct/total_parts:.4f}")
                print(f"Parent Accuracy: {total_parent_correct/total_parts:.4f}")
                print(f"Spatial Error (mean abs, discretized bins): {np.mean(all_spatial_errors):.4f}")
            print("=" * 60)

            grand_mesh_correct += total_mesh_correct
            grand_parent_correct += total_parent_correct
            grand_parts += total_parts
            grand_spatial_errors.extend(all_spatial_errors)
            grand_images_scored += n_images_scored
            grand_images_total += len(label_files)

    if args.category == 'all':
        print("#" * 60)
        print(f"GRAND TOTAL across {categories}")
        print(f"images scored: {grand_images_scored} / {grand_images_total}")
        print(f"total parts: {grand_parts}")
        print(f"Mesh(category) Accuracy: {grand_mesh_correct/grand_parts:.4f}")
        print(f"Parent Accuracy: {grand_parent_correct/grand_parts:.4f}")
        print(f"Spatial Error (mean abs, discretized bins): {np.mean(grand_spatial_errors):.4f}")
        print("#" * 60)


if __name__ == "__main__":
    main()
