# 10163 GT-only 3D Physics viewport capture

This 9-second H.264 video is assembled solely from 19 Isaac Sim renderer frames captured after actual GPU-1 Warp articulation-tensor target requests and PhysX simulation steps on the composed `Physics=physx` stage. It is **GT-only physics control — not AI prediction**. No generated/predicted output, USD target authoring, object transform writes, or keyframe animation was used.

The run reused the existing 10163 GT-only range `[-1.2, -0.6, 0, 0.6, 1.2]` rad, initialization ×3, ten round trips, session PhysicsScene, collider, and controlled material condition. Its runner completed with `GT_TENSOR_DRIVE=PASS`; full state report remains outside Git in `/home/minsujo/Desktop/SH/PHYSx/staging/gt-only-isaac-viewport-drive-20261002T111927Z-10163-viewport-drive/physics_drive_report.json`.

`10163_gt_only_physics_joint_state_trace.mp4` in the earlier result folder is a graph of logged states. This file is the separate 3D renderer capture. Neither establishes automatic joint prediction or real-world asset validity.
