#!/usr/bin/env bash
set -u

ROOT=/home/minsujo/Desktop/SH/PHYSx
SRC="$ROOT/sources/physx-4f54e750a309"
PY="$ROOT/envs/physxgen/bin/python"
MERGE_MODEL="$ROOT/staging/merge-29354-20260925T180423Z/phy_dataset/29354/model.obj"
SHAPE="$ROOT/data/shapenetcore/minimal/29354"
MERGE_MODEL_SHA=2fc96114b9967a5f5fca1be77b40a5cd4c41df24671ee6da9d60c7ee9bdbb53e
SHAPE_OBJ_SHA=d538696f9ac131cf3b36134d1ada25426701e85375c03daff26561e9c4933a9a
SHAPE_MTL_SHA=0eb2c76763251d7d00dff73d0f130db6a482a7bd2adfd48896f8454c74ac2ee5
SHAPE_TEX_SHA=37d97e4c0897fc8c139bf128379cfb033f5f207cc1ecec746691a1d8664848a9
EXPECTED_HEAD=4f54e750a309fe9cd9f20816916ecc0e8a9ae594
RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)"
STAGE="$ROOT/staging/retrieval-29354-$RUN_ID"
LOG="$ROOT/logs/retrieval-29354/$RUN_ID"
LOCK="$ROOT/logs/retrieval-29354/.active"
RC=99
cleanup() { rmdir "$LOCK" 2>/dev/null || true; }
if ! mkdir "$LOCK" 2>/dev/null; then
  echo "ABORT_REASON: another retrieval-29354 run is active or stale lock exists: $LOCK" >&2
  exit 2
fi
trap cleanup EXIT
if test -e "$STAGE" || test -e "$LOG"; then
  echo "ABORT_REASON: run directory collision: $RUN_ID" >&2
  exit 2
fi
mkdir -p "$STAGE/phy_dataset/29354" "$STAGE/shapenet/04379243/db406d9b2a94bce5622d7484764b58f/models" "$STAGE/shapenet/04379243/db406d9b2a94bce5622d7484764b58f/images" "$LOG"

START_UTC=$(date -u +%Y-%m-%dT%H:%M:%SZ)
ABORT=0
{
 echo "run_id=$RUN_ID"; echo "started_utc=$START_UTC"; echo "source=$SRC"; echo "stage=$STAGE"; echo "log=$LOG"
 actual_head=$(git -C "$SRC" rev-parse HEAD 2>/dev/null || echo unavailable); echo "source_head=$actual_head"
 if test "$actual_head" != "$EXPECTED_HEAD"; then echo "source_head_check=FAIL"; ABORT=1; else echo "source_head_check=PASS"; fi
 echo "tracked_status_begin"; git -C "$SRC" status --porcelain=v1; echo "tracked_status_end"
 "$PY" - "$SRC" <<'PY'
import pathlib, subprocess, sys
src=pathlib.Path(sys.argv[1])
lines=subprocess.check_output(['git','-C',str(src),'status','--porcelain=v1'],text=True).splitlines()
bad=[]
for line in lines:
 p=line[3:] if len(line)>=3 else line
 if ' -> ' in p: p=p.split(' -> ',1)[-1]
 if ('/__pycache__/' in p and p.endswith('.pyc')) or p.startswith('pretrain/'):
  continue
 bad.append(line)
print('related_tracked_change_check='+('FAIL' if bad else 'PASS'))
if bad:
 print('\n'.join('bad='+x for x in bad)); raise SystemExit(3)
PY
 if test $? -ne 0; then ABORT=1; fi
 retrieval_sha=$(sha256sum "$SRC/dataset_toolkits/retrieval_texture_example.py" | awk '{print $1}'); echo "retrieval_source_sha=$retrieval_sha"
 sha256sum "$MERGE_MODEL" "$SHAPE/models/model_normalized.obj" "$SHAPE/models/model_normalized.mtl" "$SHAPE/images/texture0.jpg"
} > "$LOG/preflight.log" 2>&1
if rg -q 'source_head_check=FAIL|related_tracked_change_check=FAIL' "$LOG/preflight.log"; then ABORT=1; fi
if test "$ABORT" -ne 0; then echo "ABORT_REASON: source or tracked-change preflight failed" > "$LOG/abort_reason.txt"; echo 2 > "$LOG/exit_code.txt"; exit 2; fi

if ! test -f "$MERGE_MODEL" || test "$(sha256sum "$MERGE_MODEL" | awk '{print $1}')" != "$MERGE_MODEL_SHA"; then echo 'ABORT_REASON: merge model missing or hash mismatch' > "$LOG/abort_reason.txt"; echo 2 > "$LOG/exit_code.txt"; exit 2; fi
for spec in "$SHAPE/models/model_normalized.obj:$SHAPE_OBJ_SHA" "$SHAPE/models/model_normalized.mtl:$SHAPE_MTL_SHA" "$SHAPE/images/texture0.jpg:$SHAPE_TEX_SHA"; do
 f=${spec%%:*}; h=${spec##*:}; if ! test -f "$f" || test "$(sha256sum "$f" | awk '{print $1}')" != "$h"; then echo "ABORT_REASON: input hash mismatch $f" > "$LOG/abort_reason.txt"; echo 2 > "$LOG/exit_code.txt"; exit 2; fi
done
cp "$MERGE_MODEL" "$STAGE/phy_dataset/29354/model.obj"
cp "$SHAPE/models/model_normalized.obj" "$STAGE/shapenet/04379243/db406d9b2a94bce5622d7484764b58f/models/"
cp "$SHAPE/models/model_normalized.mtl" "$STAGE/shapenet/04379243/db406d9b2a94bce5622d7484764b58f/models/"
cp "$SHAPE/images/texture0.jpg" "$STAGE/shapenet/04379243/db406d9b2a94bce5622d7484764b58f/images/"
"$PY" - "$SRC/tools/finalindex.json" "$STAGE/finalindex.json" <<'PY' > "$LOG/mapping_check.log" 2>&1
import json, pathlib, sys
src,dst=map(pathlib.Path,sys.argv[1:]); d=json.loads(src.read_text()); expected='shapenet/04379243/db406d9b2a94bce5622d7484764b58f'
assert d.get('29354')==expected, d.get('29354')
dst.write_text(json.dumps({'29354':d['29354']},indent=2)+'\n'); print('mapping=PASS',d['29354'])
PY
if test $? -ne 0; then echo 'ABORT_REASON: mapping verification failed' > "$LOG/abort_reason.txt"; echo 2 > "$LOG/exit_code.txt"; exit 2; fi

# Dependency import and the same nearest-surface operation that failed previously.
set +e
PYTHONDONTWRITEBYTECODE=1 "$PY" - > "$LOG/dependency_cpu.stdout.log" 2> "$LOG/dependency_cpu.stderr.log" <<'PY'
import numpy as np, trimesh, rtree
mesh=trimesh.creation.box(extents=[1,1,1]); points=np.array([[.2,.2,2.],[-.4,0.,0.]])
closest,distances,face_ids=mesh.nearest.on_surface(points)
assert np.isfinite(closest).all() and np.isfinite(distances).all()
print('trimesh',trimesh.__version__,'rtree',rtree.__version__,'closest_shape',closest.shape,'distances',distances.tolist())
PY
DEP_RC=$?
set -e
echo "$DEP_RC" > "$LOG/dependency_cpu.exit_code.txt"
if test "$DEP_RC" -ne 0; then echo 'ABORT_REASON: rtree import or CPU nearest check failed' > "$LOG/abort_reason.txt"; echo "$DEP_RC" > "$LOG/exit_code.txt"; exit "$DEP_RC"; fi

{
 echo "command_start_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
 echo "command=CUDA_VISIBLE_DEVICES='' PYTHONDONTWRITEBYTECODE=1 $PY $SRC/dataset_toolkits/retrieval_texture_example.py --index 0 --range 1"
 find "$STAGE/phy_dataset" "$STAGE/shapenet" -type f -printf '%P %s bytes\n' | sort
} > "$LOG/command.log"
set +e
(cd "$STAGE" && CUDA_VISIBLE_DEVICES='' PYTHONDONTWRITEBYTECODE=1 "$PY" "$SRC/dataset_toolkits/retrieval_texture_example.py" --index 0 --range 1) > "$LOG/stdout.log" 2> "$LOG/stderr.log"
RC=$?
set -e
END_UTC=$(date -u +%Y-%m-%dT%H:%M:%SZ)
echo "command_end_utc=$END_UTC" >> "$LOG/command.log"
echo "$RC" > "$LOG/exit_code.txt"
if test "$RC" -ne 0; then echo 'retrieval_failed; no retry performed' > "$LOG/output_verification.log"; echo "failure_stage=official retrieval execution" >> "$LOG/output_verification.log"; exit "$RC"; fi

set +e
"$PY" - "$STAGE" "$SHAPE/images/texture0.jpg" > "$LOG/output_verification.log" 2>&1 <<'PY'
from pathlib import Path
import hashlib, math, sys
import numpy as np
from PIL import Image
stage,source_tex=Path(sys.argv[1]),Path(sys.argv[2]); root=stage/'phy_dataset/29354'; out=root/'model_tex.obj'; inp=root/'model.obj'
def sha(p):
 h=hashlib.sha256(); h.update(p.read_bytes()); return h.hexdigest()
def parse_obj(p):
 vs=[]; fs=[]; uvs=[]
 for line in p.read_text(errors='replace').splitlines():
  if line.startswith('v '): vs.append([float(x) for x in line.split()[1:4]])
  elif line.startswith('vt '): uvs.append([float(x) for x in line.split()[1:3]])
  elif line.startswith('f '): fs.append([int(x.split('/')[0]) for x in line.split()[1:]])
 return np.array(vs),fs,np.array(uvs)
if not out.is_file(): raise SystemExit('missing model_tex.obj')
vs,fs,uv=parse_obj(out); vi,fi,_=parse_obj(inp)
if len(uv)==0 or not np.isfinite(uv).all(): raise SystemExit('UV missing or non-finite')
if vs.shape!=vi.shape or not np.allclose(vs,vi,rtol=0,atol=1e-6) or fs!=fi: raise SystemExit('generated mesh differs from input model.obj')
lines=out.read_text(errors='replace').splitlines(); refs=[x.split(maxsplit=1)[1].strip() for x in lines if x.startswith('mtllib ')]
if len(refs)!=1: raise SystemExit('expected one mtllib')
mtl=(out.parent/refs[0]).resolve()
if not mtl.is_file(): raise SystemExit(f'missing mtl {mtl}')
texrefs=[x.split(maxsplit=1)[1].strip() for x in mtl.read_text(errors='replace').splitlines() if x.startswith('map_Kd ')]
if not texrefs: raise SystemExit('no map_Kd texture reference')
used=[]
for ref in texrefs:
 p=(mtl.parent/ref).resolve()
 if not p.is_file(): raise SystemExit(f'missing texture {p}')
 with Image.open(p) as im:
  im.load(); arr=np.array(im); print('decoded_texture',p,im.format,im.size,arr.shape,sha(p))
 with Image.open(source_tex) as im:
  im.load(); src=np.array(im.convert('RGB'))
 rgb=arr[:,:,:3] if arr.ndim==3 and arr.shape[2]>=3 else arr
 mask=(arr[:,:,3]>0) if arr.ndim==3 and arr.shape[2]>=4 else np.ones(rgb.shape[:2],dtype=bool)
 source_colors={tuple(x) for x in src.reshape(-1,3)}
 membership=sum(tuple(x) in source_colors for x in rgb[mask])/max(1,int(mask.sum()))
 print('texture_source_color_membership',membership,'source_shape',src.shape,'output_shape',rgb.shape)
 if membership < 0.99: raise SystemExit('texture content does not match ShapeNet source color set')
 print('texture_transform=atlas_or_reencode',arr.shape!=src.shape or not np.array_equal(rgb,src))
 used.append(p)
print('model_tex',out.stat().st_size,sha(out)); print('mtl',mtl.stat().st_size,sha(mtl)); print('vertices',len(vs),'faces',len(fs),'uvs',len(uv)); print('texture_source_color_membership=PASS'); print('gray_fallback=NOT_USED')
PY
VRC=$?
set -e
echo "$VRC" > "$LOG/output_verification.exit_code.txt"
if test "$VRC" -ne 0; then echo 'ABORT_REASON: output verification failed' >> "$LOG/output_verification.log"; exit "$VRC"; fi
exit 0
