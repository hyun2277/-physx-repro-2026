#!/usr/bin/env python3
"""Call the fixed source render_cond algorithm with a PHYSx-local Blender path."""
import argparse
import pathlib
import sys

p = argparse.ArgumentParser()
p.add_argument('--source-dir', required=True)
p.add_argument('--blender', required=True)
p.add_argument('--model', required=True)
p.add_argument('--output', required=True)
p.add_argument('--num-views', type=int, default=24)
p.add_argument('--object-id', default='29354')
a = p.parse_args()
src = pathlib.Path(a.source_dir)
sys.path.insert(0, str(src))
import render_cond  # noqa: E402
render_cond.BLENDER_PATH = a.blender
result = render_cond._render_cond(a.model, a.object_id + '_', a.output, a.num_views)
if result is None:
    raise SystemExit('official _render_cond returned no record')
print(result)
