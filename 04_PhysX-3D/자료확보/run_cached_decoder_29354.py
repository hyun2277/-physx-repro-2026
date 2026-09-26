#!/usr/bin/env python3
"""Guarded GPU-1 runner for the cached 29354 physics and mesh decoders."""

import argparse
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
LATENT = ROOT / 'logs/rtx5090-adapter-29354/20260926T192709Z-db921ba64aaa/sampled_latents.pt'
LATENT_SHA = 'a75c3d9807780eec308b383a6db406d31dab48e2a21388b70bdd6e41ab940744'
MANIFEST = REPO / '04_PhysX-3D/자료확보/evidence/29354-inference-checkpoint-manifest.txt'
CUDA_HELPER = REPO / '04_PhysX-3D/실행스크립트/cuda_jit_environment.sh'
CUDA_TOOLKIT = ROOT / 'toolchains/cuda-12.8.1'
EXPECTED_HEAD = '4f54e750a309fe9cd9f20816916ecc0e8a9ae594'
TOTAL_OBSERVED_MIB = 32607
PREVIOUS_BEFORE_LARGE_MIB = 18744
PREVIOUS_AFTER_LARGE_MIB = 28276
LARGE_DELTA_MIB = PREVIOUS_AFTER_LARGE_MIB - PREVIOUS_BEFORE_LARGE_MIB
RESERVE_MIB = 4607
HARD_LIMIT_MIB = 28000
MODEL_OVERHEAD_MIB = 2048
MAX_SECONDS = 3600
REQUESTED_SPCONV_ALGO = 'native'


def now():
    return datetime.now(timezone.utc).isoformat()


def sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def checked(args, **kwargs):
    result = subprocess.run(args, capture_output=True, text=True, **kwargs)
    if result.returncode:
        raise RuntimeError(f'{args[0]} exited {result.returncode}: {result.stderr.strip()}')
    return result.stdout


def source_and_checkpoints():
    if checked(['git', '-C', str(SRC), 'rev-parse', 'HEAD']).strip() != EXPECTED_HEAD:
        raise RuntimeError('source HEAD mismatch')
    changed = set()
    for cmd in (['git', '-C', str(SRC), 'diff', '--name-only', '-z'],
                ['git', '-C', str(SRC), 'diff', '--cached', '--name-only', '-z']):
        changed.update(x.decode() for x in subprocess.check_output(cmd).split(b'\0') if x)
    allowed = sorted(p for p in changed if re.fullmatch(r'trellis/(?:[^/]+/)*__pycache__/[^/]+\.pyc', p))
    rejected = sorted(changed - set(allowed))
    if rejected:
        raise RuntimeError(f'non-pyc source change: {rejected}')
    if not MANIFEST.is_file() or MANIFEST.stat().st_size == 0:
        raise RuntimeError('checkpoint manifest missing or empty')
    hashes = []
    for line in MANIFEST.read_text().splitlines():
        if not line.strip():
            continue
        fields = line.split(maxsplit=1)
        if len(fields) != 2 or not re.fullmatch('[0-9a-f]{64}', fields[0]):
            raise RuntimeError('malformed checkpoint manifest')
        path = SRC / fields[1]
        if not path.is_file() or sha(path) != fields[0]:
            raise RuntimeError(f'checkpoint hash mismatch: {fields[1]}')
        hashes.append({'path': str(path), 'sha256': fields[0]})
    if len(hashes) != 11:
        raise RuntimeError(f'expected 11 manifest entries, found {len(hashes)}')
    return allowed, hashes


def validate_latent():
    if not LATENT.is_file() or LATENT.stat().st_size == 0 or sha(LATENT) != LATENT_SHA:
        raise RuntimeError('cached latent missing, empty, or hash mismatch')
    script = '''import json,sys,torch
x=torch.load(sys.argv[1],map_location='cpu',weights_only=True)
assert set(x)=={'slat_coords','slat_feats','phy_coords','phy_feats','cpu_rng','cuda_rng'}
assert torch.equal(x['slat_coords'],x['phy_coords'])
assert len(torch.unique(x['slat_coords'],dim=0))==33886
for k in ('slat_feats','phy_feats'):
 assert x[k].shape==(33886,8) and x[k].dtype==torch.float32 and torch.isfinite(x[k]).all()
print(json.dumps({k:{'shape':list(v.shape),'dtype':str(v.dtype)} for k,v in x.items() if isinstance(v,torch.Tensor)}))'''
    return json.loads(checked([str(PY), '-c', script, str(LATENT)]).strip())


def gpu_one():
    rows = checked(['nvidia-smi', '--query-gpu=index,uuid,name,memory.total,memory.free',
                    '--format=csv,noheader,nounits']).splitlines()
    match = [[x.strip() for x in row.split(',')] for row in rows if row.split(',')[0].strip() == '1']
    if len(match) != 1 or len(match[0]) < 5:
        raise RuntimeError('GPU index 1 unavailable or ambiguous')
    gpu = match[0]
    apps = checked(['nvidia-smi', '--query-compute-apps=pid,gpu_uuid,used_memory',
                    '--format=csv,noheader,nounits']).splitlines()
    if any(len(parts := row.split(',')) >= 2 and parts[1].strip() == gpu[1] for row in apps):
        raise RuntimeError('GPU 1 already has a compute process')
    return {'index': 1, 'uuid': gpu[1], 'name': gpu[2],
            'total_mib': int(gpu[3]), 'free_mib': int(gpu[4])}


def environment(run_dir, gpu_uuid):
    shell = 'source "$1"; cuda_jit_prepare "$2" "$3" /usr/bin/gcc-12 /usr/bin/g++-12 && env -0'
    raw = subprocess.check_output(['bash', '-c', shell, 'bash', str(CUDA_HELPER),
                                   str(run_dir), str(CUDA_TOOLKIT)])
    env = {k.decode(): v.decode() for item in raw.split(b'\0') if item
           for k, v in [item.split(b'=', 1)]}
    env.update(CUDA_VISIBLE_DEVICES=gpu_uuid, PHYSX_TILE_ENABLE='1',
               SPCONV_ALGO=REQUESTED_SPCONV_ALGO,
               PYTHONPATH=f'{ADAPTER}:{SRC}' + (f':{os.environ["PYTHONPATH"]}' if os.environ.get('PYTHONPATH') else ''),
               HOME=str(run_dir / 'home'), XDG_CACHE_HOME=str(ROOT / 'cache'),
               TORCH_HOME=str(ROOT / 'cache/torch'), HF_HOME=str(ROOT / 'cache/huggingface'),
               PYTHONDONTWRITEBYTECODE='1', PYTHONUNBUFFERED='1')
    env.pop('PHYSX_TILE_TEST_FORCE', None)
    return env


def verify_outputs(output):
    raw = output / 'mesh_physics_raw.pt'
    obj = output / 'mesh.obj'
    if not raw.is_file() or not obj.is_file() or raw.stat().st_size == 0 or obj.stat().st_size == 0:
        raise RuntimeError('decoder output missing or empty')
    script = '''import json,sys,torch,trimesh
x=torch.load(sys.argv[1],map_location='cpu',weights_only=True)
assert set(x)=={'vertices','faces','vertex_attrs','vertex_physics'}
assert len(x['vertices'])>0 and len(x['faces'])>0 and torch.isfinite(x['vertices']).all()
for k in ('vertex_attrs','vertex_physics'):
 assert x[k] is not None and torch.isfinite(x[k]).all()
m=trimesh.load(sys.argv[2],force='mesh',process=False)
assert len(m.vertices)==len(x['vertices']) and len(m.faces)==len(x['faces'])
print(json.dumps({'vertices':len(m.vertices),'faces':len(m.faces),
 'vertex_attrs_shape':list(x['vertex_attrs'].shape),'vertex_physics_shape':list(x['vertex_physics'].shape)}))'''
    result = json.loads(checked([str(PY), '-c', script, str(raw), str(obj)]).strip())
    return {'raw': {'path': str(raw), 'bytes': raw.stat().st_size, 'sha256': sha(raw)},
            'obj': {'path': str(obj), 'bytes': obj.stat().st_size, 'sha256': sha(obj)},
            'reload': result}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--cpu-only', action='store_true')
    args = parser.parse_args()
    run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:12]
    run_dir = ROOT / 'logs/rtx5090-cached-decoder-29354' / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    lock = open(run_dir.parent / '.runner.lock', 'w')
    if not args.cpu_only:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit('another cached decoder runner is active')
    result = {'run_id': run_id, 'started_utc': now(), 'status': 'not_run',
              'stage': 'created', 'child_exit_code': None, 'run_dir': str(run_dir)}
    child = None
    def save():
        result['updated_utc'] = now()
        (run_dir / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    def stage(name):
        result['stage'] = name; save()
        print(f'[{now()}] {name} | log={run_dir}', flush=True)
    def sync_decoder_report():
        decoder_report = run_dir / 'decoder_report.json'
        if decoder_report.is_file() and decoder_report.stat().st_size:
            child_report = json.loads(decoder_report.read_text())
            result.setdefault('spconv_algo', {'requested': REQUESTED_SPCONV_ALGO})
            result['spconv_algo']['actual'] = child_report.get('spconv_algo_actual', 'missing')
            result['decoder_report'] = str(decoder_report)
    save()
    try:
        stage('1 source, checkpoints, cached latent')
        result['allowed_pyc'], result['checkpoints'] = source_and_checkpoints()
        result['latent'] = {'path': str(LATENT), 'bytes': LATENT.stat().st_size,
                            'sha256': LATENT_SHA, 'tensors': validate_latent()}
        if args.cpu_only:
            result['reason'] = 'cpu_only_requested'; return
        stage('2 GPU 1 and measured memory budget')
        gpu = gpu_one(); result['gpu'] = gpu
        largest_decoder_mib = max(
            (SRC / 'pretrain/diffusion/ckpts_new/property_decoder_step0100000.pt').stat().st_size,
            (SRC / 'pretrain/diffusion/ckpts_new/decoder_step0100000.pt').stat().st_size) // 2**20 + 1
        expected_peak_mib = LARGE_DELTA_MIB + largest_decoder_mib + MODEL_OVERHEAD_MIB
        safe_limit = min(HARD_LIMIT_MIB, gpu['total_mib'] - RESERVE_MIB)
        result['memory_budget'] = {
            'previous_large_delta_mib': LARGE_DELTA_MIB,
            'largest_decoder_checkpoint_mib': largest_decoder_mib,
            'model_runtime_overhead_mib': MODEL_OVERHEAD_MIB,
            'expected_peak_mib': expected_peak_mib,
            'hard_limit_mib': safe_limit, 'reserved_mib': gpu['total_mib'] - safe_limit,
            'free_before_mib': gpu['free_mib'],
        }
        print(json.dumps({'memory_budget': result['memory_budget']}), flush=True)
        if gpu['total_mib'] != TOTAL_OBSERVED_MIB or safe_limit != HARD_LIMIT_MIB:
            raise RuntimeError('GPU memory geometry differs from measured run')
        if expected_peak_mib >= safe_limit or gpu['free_mib'] < expected_peak_mib + RESERVE_MIB:
            raise RuntimeError('decoder expected peak does not fit safety reserve')
        env = environment(run_dir, gpu['uuid'])
        result['spconv_algo'] = {'requested': REQUESTED_SPCONV_ALGO, 'actual': 'pending_child_import'}
        save()
        stage('3 small original/tiled/reference CUDA equivalence')
        comparison_env = dict(env, PHYSX_TILE_ENABLE='0')
        with open(run_dir / 'gpu-comparison.stdout.log', 'w') as out, open(run_dir / 'gpu-comparison.stderr.log', 'w') as err:
            rc = subprocess.run([str(PY), str(ADAPTER / 'validate_candidate.py'), 'gpu'],
                                env=comparison_env, stdout=out, stderr=err, timeout=300).returncode
        if rc:
            raise RuntimeError(f'small GPU equivalence failed with exit {rc}')
        stage('4 cached physics and mesh decoders')
        if gpu_one()['uuid'] != gpu['uuid']:
            raise RuntimeError('GPU index 1 changed before decoder')
        output = ROOT / 'staging' / f'rtx5090-cached-decoder-29354-{run_id}'
        command = [str(PY), str(ADAPTER / 'decode_cached_29354.py'), '--latent', str(LATENT),
                   '--source', str(SRC), '--output', str(output),
                   '--report', str(run_dir / 'decoder_report.json')]
        result['command'] = command; result['output'] = str(output); save()
        (run_dir / 'command.json').write_text(json.dumps({'argv': command,
            'CUDA_VISIBLE_DEVICES': gpu['uuid'], 'CUDA_HOME': env['CUDA_HOME'],
            'SPCONV_ALGO': env['SPCONV_ALGO'],
            'hard_limit_mib': safe_limit, 'reserve_mib': gpu['total_mib'] - safe_limit,
            'max_seconds': MAX_SECONDS}, indent=2) + '\n')
        started = time.monotonic()
        with open(run_dir / 'decoder.stdout.log', 'w') as out, open(run_dir / 'decoder.stderr.log', 'w') as err, open(run_dir / 'gpu_usage.log', 'w') as usage:
            child = subprocess.Popen(command, cwd=SRC, env=env, stdout=out, stderr=err,
                                     start_new_session=True)
            while child.poll() is None:
                if time.monotonic() - started > MAX_SECONDS:
                    os.killpg(child.pid, signal.SIGTERM)
                    raise RuntimeError('decoder time limit reached')
                sample = subprocess.run(['nvidia-smi', '--query-compute-apps=pid,gpu_uuid,used_memory',
                    '--format=csv,noheader,nounits'], capture_output=True, text=True)
                usage.write(f'{now()} rc={sample.returncode} {sample.stdout} {sample.stderr}\n'); usage.flush()
                if sample.returncode:
                    os.killpg(child.pid, signal.SIGTERM); raise RuntimeError('GPU monitoring failed')
                for row in sample.stdout.splitlines():
                    fields = [x.strip() for x in row.split(',')]
                    if len(fields) >= 3 and fields[1] == gpu['uuid'] and fields[2].isdigit() and int(fields[2]) > safe_limit:
                        os.killpg(child.pid, signal.SIGTERM); raise RuntimeError('GPU memory safety limit reached')
                time.sleep(3)
        result['child_exit_code'] = child.returncode
        sync_decoder_report(); save()
        if child.returncode:
            raise RuntimeError(f'decoder child exited {child.returncode}')
        stage('5 raw mesh and physics reload')
        result['artifacts'] = verify_outputs(output)
        result['status'] = 'success'
    except KeyboardInterrupt:
        result['status'] = 'interrupted'; result['reason'] = 'SIGINT'
        if child is not None and child.poll() is None:
            os.killpg(child.pid, signal.SIGINT); child.wait(timeout=30)
            result['child_exit_code'] = child.returncode
    except Exception as exc:
        result['status'] = 'failed'; result['reason'] = str(exc)
        if child is not None and child.poll() is None:
            os.killpg(child.pid, signal.SIGTERM); child.wait(timeout=30)
            result['child_exit_code'] = child.returncode
    finally:
        sync_decoder_report()
        save()
        print(f"status={result['status']} stage={result['stage']} child_rc={result['child_exit_code']} log={run_dir}", flush=True)
    if result['status'] == 'failed': raise SystemExit(1)
    if result['status'] == 'interrupted': raise SystemExit(130)


if __name__ == '__main__':
    main()
