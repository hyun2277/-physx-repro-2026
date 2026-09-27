#!/usr/bin/env python3
"""CPU-only public-only v1 update for the three verified category additions."""
from pathlib import Path
import run_public_only_v1_eight_actual as base
base.RUNS.update({'48419':('20260927T111917Z-0339ac9f4d2c','20260927T114428Z-bfc5923c4174'),'38882':('20260927T112001Z-34dce7c4a88d','20260927T114821Z-1e706d7e43a6'),'15821':('20260927T112047Z-93e8bb019216','20260927T115607Z-c1f86b590b49')})
base.TIER.update({'48419':'B_translation','38882':'B_translation','15821':'C_rotation'})
base.RAW.update({k:Path('/home/minsujo/Desktop/SH/PHYSx')/f'staging/public-only-v1-extension-decoder-{k}-{d}/mesh/mesh_physics_raw.pt' for k,(_,d) in base.RUNS.items() if k in {'48419','38882','15821'}})
base.OUT=Path(__file__).resolve().parent/'2026-09-27_public-only-v1-eleven-actual'
base.main()
