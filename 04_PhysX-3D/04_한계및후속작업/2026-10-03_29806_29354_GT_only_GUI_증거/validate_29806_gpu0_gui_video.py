"""Validate capture mechanics; human mesh/motion review remains mandatory."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops, ImageStat
from scipy import ndimage


def digest(path: Path) -> str:
    value = hashlib.sha256()
    value.update(path.read_bytes())
    return value.hexdigest()


def color_components(image: Image.Image) -> dict:
    rgb=np.asarray(image.convert("RGB"));hsv=np.asarray(image.convert("HSV"));h,s,v=hsv[:,:,0],hsv[:,:,1],hsv[:,:,2]
    masks={"BASE_GRAY":(s<=65)&(v>=55)&(v<=245),"gt_C_1_RED":((h<=12)|(h>=247))&(s>=85)&(v>=55),"gt_C_2_GREEN":(h>=60)&(h<=112)&(s>=70)&(v>=50),"gt_C_3_BLUE":(h>=138)&(h<=190)&(s>=70)&(v>=50)}
    result={}
    for name,raw in masks.items():
        labels,n=ndimage.label(raw);sizes=np.bincount(labels.ravel());sizes[0]=0;mask=labels==int(sizes.argmax()) if sizes.max()>0 else np.zeros_like(raw,dtype=bool)
        ys,xs=np.where(mask);count=int(mask.sum())
        result[name]={"pixel_count":count,"bbox_xyxy":[int(xs.min()),int(ys.min()),int(xs.max()),int(ys.max())] if count else None,"center_xy":[float(xs.mean()),float(ys.mean())] if count else None}
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args()
    report_path = args.run_dir / "physics_gui_report.json"
    report = json.loads(report_path.read_text())
    video = Path(report["capture"]["video"])
    probe = json.loads(
        subprocess.check_output(
            [
                "ffprobe", "-v", "error", "-select_streams", "v:0",
                "-show_entries", "stream=codec_name,pix_fmt,width,height,avg_frame_rate,nb_frames:format=duration,bit_rate",
                "-of", "json", str(video),
            ],
            text=True,
        )
    )
    duration = float(probe["format"]["duration"])
    frame_dir = args.run_dir / "validation_frames"
    frame_dir.mkdir(exist_ok=True)
    records = report["capture"]["records"]
    video_start = float(report["capture"]["video_start_monotonic"])
    open_records={}
    for name in ("gt_C_1","gt_C_2","gt_C_3"):
        subset=[row for row in records if row["active_joint"]==name]
        open_target=min(float(row["requested_target_rad"]) for row in subset)
        candidates=[row for row in subset if abs(float(row["requested_target_rad"])-open_target)<1e-6]
        open_records[name]=max(candidates,key=lambda row:int(row["local_step"]))
    frame_specs=[("start",0.5)]+[(name,float(open_records[name]["wall_monotonic_s"])-video_start) for name in ("gt_C_1","gt_C_2","gt_C_3")]+[("end",max(0.0,duration-0.5))]
    frame_specs=[(label,max(0.0,min(duration-0.01,timestamp))) for label,timestamp in frame_specs]
    frame_rows = []
    images = []
    for label, timestamp in frame_specs:
        path = frame_dir / f"{label}.png"
        subprocess.run(
            ["ffmpeg", "-y", "-ss", f"{timestamp:.6f}", "-i", str(video), "-frames:v", "1", str(path)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        image = Image.open(path).convert("RGB")
        images.append(image)
        stats = ImageStat.Stat(image)
        extrema = image.getextrema()
        frame_rows.append(
            {
                "label": label,
                "timestamp_s": timestamp,
                "path": str(path),
                "sha256": digest(path),
                "size": list(image.size),
                "rgb_mean": list(stats.mean),
                "rgb_stddev": list(stats.stddev),
                "rgb_max": [channel[1] for channel in extrema],
                "completely_black": all(channel[1] == 0 for channel in extrema),
                "color_components":color_components(image),
            }
        )
    pair_differences = []
    for left, right in zip(images, images[1:]):
        difference = ImageChops.difference(left, right)
        stat = ImageStat.Stat(difference)
        width, height = difference.size
        viewport_region = difference.crop((0, 0, int(width * 0.72), height))
        viewport_stat = ImageStat.Stat(viewport_region)
        pair_differences.append({"mean_abs_rgb": list(stat.mean), "bbox": difference.getbbox(), "viewport_region_mean_abs_rgb": list(viewport_stat.mean), "viewport_region_bbox": viewport_region.getbbox()})

    for frame in frame_rows:
        wanted = video_start + float(frame["timestamp_s"])
        nearest = min(records, key=lambda row: abs(float(row["wall_monotonic_s"]) - wanted))
        frame["nearest_physics_record"] = {
            "wall_time_delta_s": float(nearest["wall_monotonic_s"]) - wanted,
            "manager_step_after": nearest["manager_steps"][1],
            "requested_target_rad": nearest["requested_target_rad"],
            "active_joint": nearest["active_joint"],
            "measured_joint_positions_rad": nearest["positions_rad"],
            "joint_velocities_rad_s": nearest["velocities_rad_s"],
        }
    positions = {name: [float(row["positions_rad"][name]) for row in records if row["active_joint"] == name] for name in ("gt_C_1","gt_C_2","gt_C_3")}
    frame_by_label={row["label"]:row for row in frame_rows}
    pixel_motion={}
    color_name={"gt_C_1":"gt_C_1_RED","gt_C_2":"gt_C_2_GREEN","gt_C_3":"gt_C_3_BLUE"}
    for joint,color in color_name.items():
        base=frame_by_label["start"]["color_components"][color];opened=frame_by_label[joint]["color_components"][color]
        center_delta=math.dist(base["center_xy"],opened["center_xy"]) if base["center_xy"] and opened["center_xy"] else 0.0
        area_change=abs(opened["pixel_count"]-base["pixel_count"])/max(1,base["pixel_count"])
        pixel_motion[joint]={"start":base,"opened":opened,"center_delta_px":center_delta,"relative_area_change":area_change,"motion_detected":center_delta>=3.0 or area_change>=0.05}
    stream = probe["streams"][0]
    automated_pass = (
        report["status"] == "AUTOMATED_PRETEST_AND_CAPTURE_COMPLETE_HUMAN_VIEWPORT_REVIEW_REQUIRED"
        and stream.get("codec_name") == "h264"
        and stream.get("pix_fmt") == "yuv420p"
        and len(records) == 3 * 5 * 90
        and all(all(math.isfinite(value) for value in values) for values in positions.values())
        and all(max(values) - min(values) >= 0.5 for values in positions.values())
        and all(not row["completely_black"] for row in frame_rows)
        and all(row["bbox"] is not None for row in pair_differences)
        and all(row["viewport_region_bbox"] is not None and max(row["viewport_region_mean_abs_rgb"]) > 0.25 for row in pair_differences)
        and all(row["motion_detected"] for row in pixel_motion.values())
        and all(frame_by_label[j]["color_components"][c]["pixel_count"]>=30 for j,c in color_name.items())
    )
    derived={}
    if automated_pass:
        submission=args.run_dir/"29806_gt_only_gpu0_gui_physics_submission.mp4"
        font="/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
        video_filter=f"crop=948:534:218:194,scale=1280:720,drawtext=fontfile={font}:text='GT-only physics control — not AI prediction':x=24:y=24:fontsize=28:fontcolor=white:box=1:boxcolor=black@0.55"
        subprocess.run(["ffmpeg","-y","-i",str(video),"-vf",video_filter,"-c:v","libx264","-preset","slow","-crf","24","-pix_fmt","yuv420p","-an",str(submission)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        preview=args.run_dir/"29806_gt_only_gpu0_gui_physics_preview.gif";gif_start=max(0.0,frame_specs[1][1]-1.0)
        subprocess.run(["ffmpeg","-y","-ss",f"{gif_start:.6f}","-t","8","-i",str(submission),"-vf","fps=10,scale=640:-1:flags=lanczos","-loop","0",str(preview)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        submission_probe=json.loads(subprocess.check_output(["ffprobe","-v","error","-select_streams","v:0","-show_entries","stream=codec_name,pix_fmt,width,height,avg_frame_rate,nb_frames:format=duration","-of","json",str(submission)],text=True))
        submission_stream=submission_probe["streams"][0]
        if submission_stream.get("codec_name")!="h264" or submission_stream.get("pix_fmt")!="yuv420p" or [submission_stream.get("width"),submission_stream.get("height")]!=[1280,720]: raise RuntimeError(f"submission encode invariant failed {submission_stream}")
        submission_check=frame_dir/"submission_check.png"
        subprocess.run(["ffmpeg","-y","-ss",f"{frame_specs[2][1]:.6f}","-i",str(submission),"-frames:v","1",str(submission_check)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        submission_colors=color_components(Image.open(submission_check).convert("RGB"))
        if any(submission_colors[name]["pixel_count"]<30 for name in ("BASE_GRAY","gt_C_1_RED","gt_C_2_GREEN","gt_C_3_BLUE")): raise RuntimeError(f"submission crop lost mapped geometry {submission_colors}")
        derived={"submission":{"path":str(submission),"bytes":submission.stat().st_size,"sha256":digest(submission),"probe":submission_probe,"pixel_check":submission_colors,"derivation":"crop 948:534 at 218,194; scale 1280x720; text overlay only; no trim, speed change, interpolation, transform, or keyframe"},"preview_gif":{"path":str(preview),"bytes":preview.stat().st_size,"sha256":digest(preview),"start_s":gif_start,"duration_s":8.0,"scope":"preview only"}}
    result = {
        "status": "AUTOMATED_VIDEO_VALIDATION_PASS_HUMAN_VISUAL_REQUIRED" if automated_pass else "FAIL",
        "video": {
            "path": str(video),
            "bytes": video.stat().st_size,
            "sha256": digest(video),
            "probe": probe,
        },
        "frames": frame_rows,
        "pair_differences": pair_differences,
        "joint_capture": {
            "record_count": len(records),
            "position_spans_rad": {name:max(values)-min(values) for name,values in positions.items()},
            "per_joint_records": {name:len(values) for name,values in positions.items()},
        },
        "per_door_pixel_motion":pixel_motion,
        "derived_outputs":derived,
        "human_review_required": [
            "cabinet base and all three door meshes are visible",
            "each active door motion is visible and agrees with its joint state",
            "base and inactive doors remain stable",
            "no separation, penetration, or wrong-axis rotation is visible",
            "Isaac GUI/viewport identity is visible",
        ],
    }
    (args.run_dir / "video_validation.json").write_text(json.dumps(result, indent=2) + "\n")
    return 0 if automated_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
