#!/usr/bin/env python3
"""CPU-only aggregation of the frozen v1 evaluator over 20 verified artifacts."""
from pathlib import Path
import run_public_only_v1_eight_actual as base

NEW = {
 "19661":("20260927T122526Z-54a86e6c4f09","20260927T122802Z-06336d055672"),
 "25862":("20260927T122901Z-9149461ee2a3","20260927T123143Z-acfc216c55ca"),
 "31114":("20260927T123339Z-d2820a3cd135","20260927T123628Z-5672f496024f"),
 "22738":("20260927T123732Z-fafea3822b72","20260927T124015Z-b67143e58a4e"),
 "24163":("20260927T124118Z-98b365f21e48","20260927T124420Z-df88f8f6da1e"),
 "27499":("20260927T124529Z-ac778e0f577f","20260927T124813Z-6cff17e43fef"),
 "25598":("20260927T124916Z-a09043344e69","20260927T125150Z-7cf59abd9103"),
 "19335":("20260927T125249Z-0cb2e79b5874","20260927T125530Z-e449cfc20e80"),
 "34676":("20260927T125633Z-97831a19566c","20260927T125910Z-73bc09db5944"),
}
# Preserve the three category-extension entries already validated in the
# eleven-artifact report, then append only newly successful batch entries.
PRIOR={"48419":("20260927T111917Z-0339ac9f4d2c","20260927T114428Z-bfc5923c4174"),"38882":("20260927T112001Z-34dce7c4a88d","20260927T114821Z-1e706d7e43a6"),"15821":("20260927T112047Z-93e8bb019216","20260927T115607Z-c1f86b590b49")}
base.RUNS.update(PRIOR); base.RUNS.update(NEW)
base.TIER.update({k:"fixed" for k in NEW}); base.TIER.update({"48419":"B_translation","38882":"B_translation","15821":"C_rotation"})
for key,(_,decoder) in {**PRIOR,**NEW}.items():
    base.RAW[key]=Path('/home/minsujo/Desktop/SH/PHYSx')/f'staging/public-only-v1-extension-decoder-{key}-{decoder}/mesh/mesh_physics_raw.pt'
base.OUT=Path(__file__).resolve().parent/'2026-09-27_public-only-v1-twenty-actual'
base.main()
