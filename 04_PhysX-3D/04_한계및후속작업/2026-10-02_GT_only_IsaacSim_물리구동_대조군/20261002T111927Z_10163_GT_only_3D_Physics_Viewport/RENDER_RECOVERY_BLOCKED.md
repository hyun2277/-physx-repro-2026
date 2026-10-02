# 10163 3D rendering recovery — blocked before valid mesh frame

The existing `10163_gt_only_physics_viewport.mp4` is `INVALID_BLACK_CAPTURE`: 1440×900, 27 decoded frames, 9.0 s, 7,635 bytes; start/middle/end RGB means were about 0.389/255. It must not be used as physics-video evidence.

The headless swapchain path does not receive a populated render product. A Replicator camera/render-product static-frame probe was then attempted before any new tensor drive. The default Isaac experience loaded `omni.isaac.ml_archive` and failed on `libc10_cuda.so: undefined symbol: cudaGetDriverEntryPointByVersion`. The validated ML/ROS-excluding Kit avoided that ABI error, but `SimulationApp._wait_for_viewport` reported `No module named 'omni.kit.viewport`; no RGB render product was written. Therefore there are no three non-black mesh frames and no valid 3D physics MP4.

No transform/keyframe animation, automatic prediction, generated artifact, or new joint drive was substituted. The existing 10163 GT-only Tensor physics PASS remains separate and unchanged.

Next reproducible diagnostic: create an ML/ROS-excluding Kit experience whose explicit dependencies include the official offscreen render-product/Replicator requirements without `omni.isaac.ml_archive`, then prove three non-black static camera frames with decoded mesh visibility before executing the GT-only tensor drive capture.
