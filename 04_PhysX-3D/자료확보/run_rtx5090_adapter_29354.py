#!/usr/bin/env python3
"""Fail-closed terminal runner for a single 29354 adapter inference."""

import argparse
import difflib
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone

ROOT = Path('/home/minsujo/Desktop/SH/PHYSx')
SRC = ROOT / 'sources/physx-4f54e750a309'
REPO = ROOT / 'repro-records'
ADAPTER = REPO / '04_PhysX-3D/자료확보/rtx5090_adapter'
PY = ROOT / 'envs/physxgen/bin/python'
INPUT = ROOT / 'staging/render-cond-29354-portable-20260925T185825Z/datasets/PhysXNet/renders_cond/29354_/000.png'
TRANSFORMS = INPUT.with_name('transforms.json')
MANIFEST = REPO / '04_PhysX-3D/자료확보/evidence/29354-inference-checkpoint-manifest.txt'
CUDA_HELPER = REPO / '04_PhysX-3D/실행스크립트/cuda_jit_environment.sh'
CUDA_TOOLKIT = ROOT / 'toolchains/cuda-12.8.1'
HEAD = '4f54e750a309fe9cd9f20816916ecc0e8a9ae594'
INPUT_SHA = '2db40557423afe1f0e1ae4e85c72e702f25fee227931a564c92879c68f733e85'
TRANSFORMS_SHA = '636144e9fc74f41cb0160b2c877aa0e798e55d4fa0e466434cb16703d0a28a3d'
MAX_GPU_MIB = 28000
MAX_SECONDS = 7200


def now():
    return datetime.now(timezone.utc).isoformat()


def sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def run_capture(args, **kwargs):
    result = subprocess.run(args, capture_output=True, text=True, **kwargs)
    if result.returncode:
        raise RuntimeError(f'{args[0]} exited {result.returncode}: {result.stderr.strip()}')
    return result.stdout


def tracked_changes():
    found = set()
    for args in (['git', '-C', str(SRC), 'diff', '--name-only', '-z'],
                 ['git', '-C', str(SRC), 'diff', '--cached', '--name-only', '-z']):
        found.update(p.decode() for p in subprocess.check_output(args).split(b'\0') if p)
    allowed = sorted(p for p in found if re.fullmatch(r'trellis/(?:[^/]+/)*__pycache__/[^/]+\.pyc', p))
    rejected = sorted(found - set(allowed))
    if rejected:
        raise RuntimeError(f'non-pyc tracked source changes: {rejected}')
    return allowed


def validate_manifest():
    if not MANIFEST.is_file() or MANIFEST.stat().st_size == 0:
        raise RuntimeError('checkpoint manifest missing or empty')
    rows = []
    for line in MANIFEST.read_text().splitlines():
        if not line.strip():
            continue
        fields = line.split(maxsplit=1)
        if len(fields) != 2 or not re.fullmatch('[0-9a-f]{64}', fields[0]):
            raise RuntimeError('malformed checkpoint manifest')
        rel = Path(fields[1])
        if rel.is_absolute() or '..' in rel.parts or not str(rel).startswith('pretrain/'):
            raise RuntimeError('unsafe checkpoint manifest path')
        path = SRC / rel
        if not path.is_file() or sha(path) != fields[0]:
            raise RuntimeError(f'checkpoint missing or hash mismatch: {rel}')
        rows.append({'path': str(path), 'sha256': fields[0]})
    if len(rows) != 11:
        raise RuntimeError(f'expected 11 checkpoint files, found {len(rows)}')
    return rows


def gpu_uuid():
    rows = run_capture(['nvidia-smi', '--query-gpu=index,uuid,name,memory.total,memory.free',
                        '--format=csv,noheader,nounits']).splitlines()
    chosen = [r.split(',') for r in rows if r.split(',')[0].strip() == '1']
    if len(chosen) != 1 or len(chosen[0]) < 5:
        raise RuntimeError('GPU index 1 unavailable or ambiguous')
    gpu = [s.strip() for s in chosen[0]]
    apps = run_capture(['nvidia-smi', '--query-compute-apps=pid,gpu_uuid,used_memory',
                        '--format=csv,noheader,nounits']).splitlines()
    if any(len(parts := r.split(',')) >= 2 and parts[1].strip() == gpu[1] for r in apps):
        raise RuntimeError('GPU 1 already has a compute process')
    return {'index': 1, 'uuid': gpu[1], 'name': gpu[2], 'total_mib': gpu[3], 'free_mib': gpu[4]}


def overlay_environment(run_dir, uuid_value):
    clip_weight = ROOT / 'cache/clip/ViT-L-14.pt'
    if not clip_weight.is_file() or clip_weight.stat().st_size == 0:
        raise RuntimeError('existing CLIP ViT-L/14 weight missing; download forbidden')
    clip_dir = run_dir / 'home/.cache/clip'
    clip_dir.mkdir(parents=True, exist_ok=False)
    (clip_dir / 'ViT-L-14.pt').symlink_to(clip_weight)
    script = 'source "$1"; cuda_jit_prepare "$2" "$3" /usr/bin/gcc-12 /usr/bin/g++-12 && env -0'
    raw = subprocess.check_output(['bash', '-c', script, 'bash', str(CUDA_HELPER),
                                   str(run_dir), str(CUDA_TOOLKIT)])
    env = {k.decode(): v.decode() for item in raw.split(b'\0') if item
           for k, v in [item.split(b'=', 1)]}
    env.update(CUDA_VISIBLE_DEVICES=uuid_value, PHYSX_TILE_ENABLE='1',
               PYTHONPATH=f'{ADAPTER}:{SRC}' + (f':{os.environ["PYTHONPATH"]}' if os.environ.get('PYTHONPATH') else ''),
               HOME=str(run_dir / 'home'), XDG_CACHE_HOME=str(ROOT / 'cache'),
               TORCH_HOME=str(ROOT / 'cache/torch'), HF_HOME=str(ROOT / 'cache/huggingface'),
               PYTHONDONTWRITEBYTECODE='1', PYTHONUNBUFFERED='1',
               PHYSX_RUN_LOG=str(run_dir))
    env.pop('PHYSX_TILE_TEST_FORCE', None)
    return env


def make_example_copy(run_dir):
    text = (SRC / 'example.py').read_text()
    marker = 'pipeline.cuda()'
    if text.count(marker) != 1:
        raise RuntimeError('example pipeline insertion point changed')
    record = '''\n_original_preprocess_image = pipeline.preprocess_image
def _record_preprocess_image(image):
    result = _original_preprocess_image(image)
    import numpy as _np
    from PIL import Image as _Image
    pixels = _np.asarray(result)
    foreground = _np.argwhere(_np.any(pixels != 0, axis=2))
    if len(foreground) == 0:
        raise RuntimeError("empty preprocessed foreground")
    result.save(os.path.join(os.environ["PHYSX_RUN_LOG"], "preprocessed.png"))
    import json as _json
    with open(os.path.join(os.environ["PHYSX_RUN_LOG"], "preprocessed.json"), "w") as _f:
        _json.dump({"size":list(result.size), "pixel_min":int(pixels.min()),
                    "pixel_max":int(pixels.max()), "foreground_pixels":int(len(foreground)),
                    "foreground_bbox_yx": [foreground.min(0).tolist(), foreground.max(0).tolist()]}, _f)
    return result
pipeline.preprocess_image = _record_preprocess_image
_original_sample_slat = pipeline.sample_slat
def _record_sample_slat(*args, **kwargs):
    slat, phy_latent = _original_sample_slat(*args, **kwargs)
    import json as _json
    _coords = slat.coords.cpu()
    with open(os.path.join(os.environ["PHYSX_RUN_LOG"], "sparse_coords.json"), "w") as _f:
        _json.dump({"rows":len(_coords), "min":_coords.min(0).values.tolist(),
                    "max":_coords.max(0).values.tolist(),
                    "unique_rows":len(torch.unique(_coords,dim=0))}, _f)
    torch.save({"slat_coords": slat.coords.cpu(), "slat_feats": slat.feats.cpu(),
                "phy_coords": phy_latent.coords.cpu(), "phy_feats": phy_latent.feats.cpu(),
                "cpu_rng": torch.get_rng_state(), "cuda_rng": torch.cuda.get_rng_state_all()},
               os.path.join(os.environ["PHYSX_RUN_LOG"], "sampled_latents.pt"))
    return slat, phy_latent
pipeline.sample_slat = _record_sample_slat
'''
    text = text.replace(marker, marker + record)
    marker = 'phy=phy.squeeze()'
    if text.count(marker) != 1:
        raise RuntimeError('example physics insertion point changed')
    text = text.replace(marker, marker + '''\ntorch.save(phy.detach().cpu(), os.path.join(os.environ["PHYSX_RUN_LOG"], "physics_raw.pt"))''')
    target = run_dir / 'example_adapter.py'
    target.write_text(text)
    (run_dir / 'example_adapter.diff').write_text(''.join(difflib.unified_diff(
        (SRC / 'example.py').read_text().splitlines(keepends=True),
        text.splitlines(keepends=True), fromfile='official/example.py',
        tofile='run/example_adapter.py')))
    return target


def verify_artifacts(output_dir, run_dir, env):
    result = output_dir / 'pretrain/diffusion'
    files = ['rgb.mp4', 'affordance.mp4', 'material.mp4', 'description.mp4', 'texture.glb']
    evidence = {}
    for filename in files:
        path = result / filename
        if not path.is_file() or path.stat().st_size == 0:
            raise RuntimeError(f'output missing or empty: {filename}')
        evidence[filename] = {'path': str(path), 'bytes': path.stat().st_size, 'sha256': sha(path)}
        if filename.endswith('.mp4'):
            probe = run_capture(['ffprobe', '-v', 'error', '-select_streams', 'v:0',
                                 '-count_frames', '-show_entries', 'stream=nb_read_frames,width,height',
                                 '-of', 'json', str(path)])
            stream = json.loads(probe)['streams'][0]
            if int(stream.get('nb_read_frames', 0)) < 2:
                raise RuntimeError(f'video decoding failed: {filename}')
            evidence[filename]['decoded_frames'] = int(stream['nb_read_frames'])
    verification = '''import json, pathlib, sys, torch, trimesh
from PIL import Image
p=pathlib.Path(sys.argv[1]); run=pathlib.Path(sys.argv[2])
scene=trimesh.load(p, force='scene'); meshes=list(scene.geometry.values())
assert meshes and sum(len(m.faces) for m in meshes)>0
uv_meshes=0; images=0
for m in meshes:
    uv=getattr(m.visual,'uv',None)
    if uv is not None and len(uv)==len(m.vertices): uv_meshes+=1
    material=getattr(m.visual,'material',None)
    image=getattr(material,'baseColorTexture',None)
    if image is not None:
        image.load(); image.verify(); images+=1
assert uv_meshes>0 and images>0
raw=torch.load(run/'physics_raw.pt',map_location='cpu',weights_only=True)
cache=torch.load(run/'sampled_latents.pt',map_location='cpu',weights_only=True)
assert raw.numel()>0 and torch.isfinite(raw).all()
for key in ('slat_coords','slat_feats','phy_coords','phy_feats'):
    assert key in cache and cache[key].numel()>0
assert torch.equal(cache['slat_coords'],cache['phy_coords'])
print(json.dumps({'mesh_count':len(meshes),'uv_meshes':uv_meshes,'decoded_textures':images,
                  'physics_shape':list(raw.shape),'physics_finite':True,
                  'latent_rows':len(cache['slat_coords'])}))'''
    parsed = run_capture([str(PY), '-c', verification, str(result / 'texture.glb'), str(run_dir)], env=env)
    evidence['structure'] = json.loads(parsed.strip().splitlines()[-1])
    for filename in ('physics_raw.pt', 'sampled_latents.pt'):
        path = run_dir / filename
        evidence[filename] = {'path': str(path), 'bytes': path.stat().st_size, 'sha256': sha(path)}
    return evidence


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--cpu-only', action='store_true', help='inspect source and CPU algebra only')
    args = parser.parse_args()
    run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:12]
    run_dir = ROOT / 'logs/rtx5090-adapter-29354' / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    lock = open(run_dir.parent / '.runner.lock', 'w')
    if not args.cpu_only:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit('another RTX 5090 adapter runner is active')
    result = {'run_id': run_id, 'started_utc': now(), 'status': 'not_run',
              'stage': 'created', 'child_exit_code': None,
              'inference_status': 'not_run', 'run_dir': str(run_dir)}
    def save():
        result['updated_utc'] = now()
        (run_dir / 'result.json').write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n')
    def stage(name):
        result['stage'] = name
        save()
        print(f'[{now()}] {name} | log={run_dir}', flush=True)
    save()
    child = None
    try:
        stage('1 source/input/checkpoints')
        if run_capture(['git', '-C', str(SRC), 'rev-parse', 'HEAD']).strip() != HEAD:
            raise RuntimeError('source HEAD mismatch')
        result['allowed_pyc'] = tracked_changes()
        if sha(INPUT) != INPUT_SHA or sha(TRANSFORMS) != TRANSFORMS_SHA:
            raise RuntimeError('conditioning input hash mismatch')
        result['input'] = {'path': str(INPUT), 'sha256': INPUT_SHA,
                           'transforms_sha256': TRANSFORMS_SHA}
        result['checkpoints'] = validate_manifest()
        stage('2 CPU algebra and int32 boundary')
        for item in ('cpu', 'cpu_spconv', 'boundary'):
            output = run_capture([str(PY), str(ADAPTER / 'validate_candidate.py'), item])
            (run_dir / f'{item}.log').write_text(output)
        if args.cpu_only:
            result['status'] = 'not_run'
            result['reason'] = 'cpu_only_requested'
            return
        stage('3 GPU index 1 and import paths')
        gpu = gpu_uuid()
        result['gpu'] = gpu
        if int(gpu['total_mib']) < MAX_GPU_MIB or int(gpu['free_mib']) < MAX_GPU_MIB:
            raise RuntimeError('GPU available memory smaller than configured limit')
        env = overlay_environment(run_dir, gpu['uuid'])
        result['limits'] = {'gpu_mib': MAX_GPU_MIB, 'seconds': MAX_SECONDS}
        print(f"limits gpu={MAX_GPU_MIB} MiB time={MAX_SECONDS} seconds", flush=True)
        module_check = '''import json, pathlib, spconv, torch, trellis, channel_tiled_spconv as a
from spconv.pytorch.conv import SparseConvolution
print(json.dumps({'python':str(pathlib.Path(__import__('sys').executable).resolve()),
 'torch':torch.__version__,'torch_file':torch.__file__,
 'cuda':torch.version.cuda,'spconv':spconv.__file__,
 'trellis':trellis.__file__,'adapter':a.__file__,
 'patched':SparseConvolution.forward is a._tiled_forward,
 'available':torch.cuda.is_available(),
 'capability':torch.cuda.get_device_capability(0) if torch.cuda.is_available() else None}))'''
        info = json.loads(run_capture([str(PY), '-c', module_check], env=env).strip().splitlines()[-1])
        (run_dir / 'imports.json').write_text(json.dumps(info, indent=2) + '\n')
        if (info['python'] != str(PY.resolve()) or info['torch'] != '2.7.1+cu128'
            or not info['torch_file'].startswith(str(PY.parent.parent))
            or not info['spconv'].startswith(str(PY.parent.parent))
            or not info['trellis'].startswith(str(SRC))
            or not info['adapter'].startswith(str(ADAPTER)) or not info['patched']
            or info['capability'] != [12, 0]):
            raise RuntimeError('Python/module path or sm_120 validation failed')
        stage('4 small CUDA, original spconv, tiled candidate, independent reference')
        compare_env = dict(env, PHYSX_TILE_ENABLE='0')
        with open(run_dir / 'gpu-comparison.stdout.log', 'w') as out, open(run_dir / 'gpu-comparison.stderr.log', 'w') as err:
            rc = subprocess.run([str(PY), str(ADAPTER / 'validate_candidate.py'), 'gpu'],
                                env=compare_env, stdout=out, stderr=err, timeout=300).returncode
        if rc:
            raise RuntimeError(f'GPU comparison failed with exit {rc}')
        stage('5 table regression evidence')
        table = ROOT / 'logs/original-example-terminal/20260922T074246Z/example.exit_code.txt'
        if not table.is_file() or table.read_text().strip() != '0':
            raise RuntimeError('prior official table success evidence missing')
        (run_dir / 'table-regression.txt').write_text(f'prior_table_exit_code={table.read_text().strip()}\n'
                                                      'adapter activates only above int32 feature boundary; table not rerun\n')
        stage('6 actual decoder and 29354 full inference (single invocation)')
        if gpu_uuid()['uuid'] != gpu['uuid']:
            raise RuntimeError('GPU index 1 changed before inference')
        example = make_example_copy(run_dir)
        output_dir = ROOT / 'staging' / f'rtx5090-adapter-29354-{run_id}'
        output_dir.mkdir(parents=True, exist_ok=False)
        cmd = [str(PY), str(example), '--condpath', str(INPUT), '--savepath', str(output_dir)]
        result['command'] = cmd
        result['output_dir'] = str(output_dir)
        (run_dir / 'command.json').write_text(json.dumps({'argv': cmd,
            'cuda_visible_devices': gpu['uuid'], 'cuda_home': env['CUDA_HOME'],
            'cc': env['CC'], 'cxx': env['CXX'], 'max_gpu_mib': MAX_GPU_MIB,
            'max_seconds': MAX_SECONDS}, indent=2) + '\n')
        started = time.monotonic()
        with open(run_dir / 'example.stdout.log', 'w') as out, open(run_dir / 'example.stderr.log', 'w') as err, open(run_dir / 'gpu_usage.log', 'w') as usage:
            result['inference_status'] = 'running'
            save()
            child = subprocess.Popen(cmd, cwd=SRC, env=env, stdout=out, stderr=err,
                                     start_new_session=True)
            while child.poll() is None:
                if time.monotonic() - started > MAX_SECONDS:
                    os.killpg(child.pid, signal.SIGTERM)
                    raise RuntimeError('model time limit reached')
                sample = subprocess.run(['nvidia-smi', '--query-compute-apps=pid,gpu_uuid,used_memory',
                    '--format=csv,noheader,nounits'], capture_output=True, text=True)
                usage.write(f'{now()} rc={sample.returncode} {sample.stdout} {sample.stderr}\n')
                usage.flush()
                if sample.returncode:
                    os.killpg(child.pid, signal.SIGTERM)
                    raise RuntimeError('GPU monitoring failed')
                for row in sample.stdout.splitlines():
                    fields = [v.strip() for v in row.split(',')]
                    if len(fields) >= 3 and fields[1] == gpu['uuid'] and fields[2].isdigit() and int(fields[2]) > MAX_GPU_MIB:
                        os.killpg(child.pid, signal.SIGTERM)
                        raise RuntimeError('GPU memory limit reached')
                time.sleep(5)
        result['child_exit_code'] = child.returncode
        result['inference_status'] = 'success' if child.returncode == 0 else 'failed'
        (run_dir / 'example.exit_code.txt').write_text(str(child.returncode) + '\n')
        if child.returncode:
            raise RuntimeError(f'example exited {child.returncode}')
        stage('7 videos, GLB mesh/UV/texture, raw physics')
        result['artifacts'] = verify_artifacts(output_dir, run_dir, env)
        result['status'] = 'success'
    except KeyboardInterrupt:
        result['status'] = 'interrupted'
        result['inference_status'] = 'interrupted' if child is not None else 'not_run'
        result['reason'] = 'SIGINT'
        if child is not None and child.poll() is None:
            os.killpg(child.pid, signal.SIGINT)
            child.wait(timeout=30)
            result['child_exit_code'] = child.returncode
    except Exception as exc:
        result['status'] = 'failed'
        if child is not None:
            result['inference_status'] = 'failed'
        result['reason'] = str(exc)
        if child is not None and child.poll() is None:
            os.killpg(child.pid, signal.SIGTERM)
            child.wait(timeout=30)
            result['child_exit_code'] = child.returncode
    finally:
        save()
        print(f"status={result['status']} stage={result['stage']} child_rc={result['child_exit_code']} log={run_dir}", flush=True)
    if result['status'] == 'failed':
        raise SystemExit(1)
    if result['status'] == 'interrupted':
        raise SystemExit(130)


if __name__ == '__main__':
    main()
