"""
저자가 제공한 자동 GroundingDINO 탐지 결과를, GUI 마우스 조작 없이 그대로 확정 저장하는 스크립트.
get_bbox.py의 evaluate() 함수를 그대로 재사용하되, root.mainloop()(사람의 GUI 조작 대기) 대신
BoundingBoxApp.confirm_and_exit()를 곧바로 호출해 "수정 없이 그대로 확정"한 것과 동일한 결과를 저장한다.
- 논문 arXiv 2405.11656 본문에 GUI/interactive 서술이 없고, 실제 실험(로봇 실험)은
  "자동으로 GroundingDINO가 탐지"했다고 명시되어 있어(파이프라인 자체가 이 방식), 이 스크립트는
  논문이 실제로 한 방식을 재현하는 것에 더 가깝다(우회/편법이 아님).
- get_bbox.py의 소스 코드는 한 글자도 수정하지 않았고, 이 스크립트는 별도 파일로 추가한 것뿐이다.
"""
import argparse
import glob
import os
import numpy as np
import tkinter as tk

from utils import detection_config
from grounding_dino.detection import detector
from grounding_dino.post_processing import post_processing
from labeller import BoundingBoxApp


def auto_evaluate(args, detection_args):
    input_path = args.image_path
    print('************ Applying Finetuned (Model Soup) GroundingDINO *******************')
    detector(args.scene_type, detection_args)

    label_dir = 'grounding_dino/labels'
    save_dir = 'grounding_dino/labels_filtered'
    manual_dir = 'grounding_dino/labels_manual'
    os.makedirs(manual_dir, exist_ok=True)
    post_processing(label_dir, input_path, save_dir)

    for img_path in glob.glob(f"{input_path}/*"):
        label_name = os.path.basename(img_path)[:-4]
        label_path = f"grounding_dino/labels_filtered/{label_name}.npy"
        labeled_boxes = np.load(label_path, allow_pickle=True).item()
        normalized_bboxes = labeled_boxes['part_normalized_bbox']
        root = tk.Tk()
        app = BoundingBoxApp(root, img_path, initial_boxes=normalized_bboxes, save_path=manual_dir)
        # 사람의 마우스 조작(우클릭 삭제/드래그 추가/confirm 버튼) 없이,
        # GroundingDINO의 자동 예측값을 수정 없이 그대로 확정 저장
        app.confirm_and_exit()
        print(f"[auto-confirmed, no manual edits] {label_name}: {len(normalized_bboxes)} boxes saved")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('-scene_type', '--scene_type', default='object', type=str)
    parser.add_argument('-image_path', '--image_path', default='images', type=str)
    args = parser.parse_args()
    detection_args = detection_config(args)
    auto_evaluate(args, detection_args)


if __name__ == "__main__":
    main()
