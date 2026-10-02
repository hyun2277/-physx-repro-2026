"""Validate capture mechanics; human mesh/motion review remains mandatory."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
from pathlib import Path

from PIL import Image, ImageChops, ImageStat


def digest(path: Path) -> str:
    value = hashlib.sha256()
    value.update(path.read_bytes())
    return value.hexdigest()


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
    times = [0.5, duration / 2.0, max(0.0, duration - 0.5)]
    frame_rows = []
    images = []
    for label, timestamp in zip(("start", "middle", "end"), times):
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

    records = report["capture"]["records"]
    video_start = float(report["capture"]["video_start_monotonic"])
    for frame in frame_rows:
        wanted = video_start + float(frame["timestamp_s"])
        nearest = min(records, key=lambda row: abs(float(row["wall_monotonic_s"]) - wanted))
        frame["nearest_physics_record"] = {
            "wall_time_delta_s": float(nearest["wall_monotonic_s"]) - wanted,
            "manager_step_after": nearest["manager_steps"][1],
            "requested_target_rad": nearest["requested_target_rad"],
            "measured_joint_position_rad": nearest["position_rad"],
            "joint_velocity_rad_s": nearest["velocity_rad_s"],
        }
    positions = [float(row["position_rad"]) for row in records]
    stream = probe["streams"][0]
    automated_pass = (
        report["status"] == "AUTOMATED_PRETEST_AND_CAPTURE_COMPLETE_HUMAN_VIEWPORT_REVIEW_REQUIRED"
        and stream.get("codec_name") == "h264"
        and stream.get("pix_fmt") == "yuv420p"
        and len(records) == len(report["capture"]["targets_rad"]) * 90
        and all(math.isfinite(value) for value in positions)
        and max(positions) - min(positions) >= 0.5
        and all(not row["completely_black"] for row in frame_rows)
        and all(row["bbox"] is not None for row in pair_differences)
        and all(row["viewport_region_bbox"] is not None and max(row["viewport_region_mean_abs_rgb"]) > 0.25 for row in pair_differences)
    )
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
            "position_span_rad": max(positions) - min(positions),
            "start_position_rad": positions[0],
            "middle_position_rad": positions[len(positions) // 2],
            "end_position_rad": positions[-1],
        },
        "human_review_required": [
            "actual laptop mesh is visible",
            "lid motion is visible and agrees with joint direction",
            "base remains fixed",
            "no separation, penetration, or wrong-axis rotation is visible",
            "Isaac GUI/viewport identity is visible",
        ],
    }
    (args.run_dir / "video_validation.json").write_text(json.dumps(result, indent=2) + "\n")
    return 0 if automated_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
