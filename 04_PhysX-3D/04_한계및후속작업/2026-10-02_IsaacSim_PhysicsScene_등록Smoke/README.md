# Isaac Sim PhysicsScene registration smoke

This record isolates the 2026-10-02 GT-only drive precondition.  It does not
convert URDF, command a joint, or use an AI-generated asset.

The prior physics runner selected the composed `Physics=physx` USD variant and
found the expected 10163 schemas (one revolute joint, one articulation root,
three rigid bodies, two colliders), but its timeline updates produced repeated
`No simulation registered` warnings.  There was no Python traceback at that
point.  The imported 10163 root stage had no `UsdPhysics.Scene` prim, and the
runner did not load or call Isaac Sim 6.1's `isaacsim.core.simulation_manager`.
It therefore did not establish a registered world before attempting the drive.

Isaac Sim 6.1.0's installed `isaacsim.core.simulation_manager` source documents
the required sequence: create/access `PhysxScene`, call
`SimulationManager.setup_simulation`, initialize physics when manual setup is
needed, then call `SimulationManager.step`.  The extension's own tests create
`/World/PhysicsScene` before updating/stepping.  The NVIDIA API documentation
also describes `PhysxScene(path)` as creating a scene when the prim does not
exist and provides the same setup/step example.  The runner uses only this
installed API and a standalone `SimulationApp`; it excludes ML and ROS
extensions.

The passing run is
`/home/minsujo/Desktop/SH/PHYSx/logs/isaac-sim-physics-scene-registration/20261002T082639Z-physics-scene-registration`.
It opened the existing `10163` USD, selected `Physics=physx`, authored
`/World/GTOnlyRuntimePhysicsScene` only in the anonymous USD session layer,
selected physical GPU 1 through `CUDA_VISIBLE_DEVICES=1`, and ran one no-drive
physics step.  The manager reported the sole `physx` engine active, created a
physics simulation view on CUDA device 0 (the CUDA-visible alias of physical
GPU 1), and advanced the official physics-step counter from 2 to 5.  The pass
Kit log contains no `No simulation registered` message.  Stopping the timeline
subsequently resets the counter to 0; this is recorded but is not a failed
step.

The imported USD, URDF, and GT inputs were not saved or changed.  `PhysicsScene`
is a runtime/session-layer component, so it is a world-initialization fix, not
a change to the converted asset.  The existing GT-only runner is now prepared
to apply this same mandatory preflight to **10163 only**.  It has not been run
after this change; 29806, 29354, generated-output assets, and all videos remain
outside this task.

Sources: installed Isaac Sim 6.1.0 extension
`tools/isaac-sim/exts/isaacsim.core.simulation_manager/` (version 1.17.1), and
[NVIDIA Simulation Manager API](https://docs.isaacsim.omniverse.nvidia.com/latest/py/source/extensions/isaacsim.core.simulation_manager/docs/index.html).
