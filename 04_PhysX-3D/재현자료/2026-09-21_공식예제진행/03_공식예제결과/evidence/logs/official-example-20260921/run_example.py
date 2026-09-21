"""Run exactly the reviewed table example once, offline, with a unique output tree."""
import argparse
import datetime
import hashlib
import importlib.metadata as md
import json
import os
from pathlib import Path
import runpy
import sys
import traceback
import uuid

ROOT = Path('/home/minsujo/Desktop/SH/PHYSx')
TASK = ROOT / 'logs/official-example-20260921'
ENV = ROOT / 'envs/physxgen'
SITE = ENV / 'lib/python3.10/site-packages'
WORK = ROOT / 'sources/physx-example-work-4f54e750a309'
KNOWN_GPUS = {
    'GPU-ff124b39-8b48-7d2a-bf74-bf6a5c8f1716': {'host_index': 0, 'device_minor': 0},
    'GPU-843dced4-ee97-dbb8-36c9-343fe13b7647': {'host_index': 1, 'device_minor': 1},
}

def configure_streams():
    # -I ignores PYTHONUNBUFFERED; configure the live streams explicitly.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(line_buffering=True, write_through=True)

def digest(path, on_progress=None):
    value = hashlib.sha256()
    completed = 0
    last_reported = 0
    total = path.stat().st_size if on_progress is not None else None
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            value.update(chunk)
            completed += len(chunk)
            if on_progress is not None and (completed - last_reported >= 256 * 1024 * 1024 or completed == total):
                on_progress(completed, total)
                last_reported = completed
    return value.hexdigest()

def write(path, value):
    assert path.resolve().is_relative_to(ROOT) and not path.is_symlink()
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.partial')
    with temporary.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    # Readers see either the old complete JSON or the new complete JSON.
    os.replace(temporary, path)

def progress(state, report, stage, **details):
    event = {'stage': stage, 'updated_at': datetime.datetime.now(datetime.timezone.utc).isoformat(), **details}
    state['progress'] = event
    write(report, state)
    print(json.dumps({'kind': 'example_progress', 'output_root': state['output_root'], **event}, ensure_ascii=False), flush=True)

def main():
    configure_streams()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gpu-uuid', required=True, choices=tuple(KNOWN_GPUS),
                        help='Known full GPU UUID selected and rechecked by the terminal driver.')
    args = parser.parse_args()
    selected_gpu = args.gpu_uuid
    assert sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode
    assert Path(sys.prefix).resolve() == ENV and Path.cwd() == WORK
    assert os.environ.get('PHYSX_RUN_PROFILE') == 'gpu'
    assert os.environ.get('CUDA_VISIBLE_DEVICES') == selected_gpu
    assert os.environ.get('HF_HUB_OFFLINE') == '1'
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:10]
    output = ROOT / 'outputs/official-example' / ('table-' + stamp)
    output.mkdir(parents=True, exist_ok=False)
    report = output / 'execution.json'
    state = {'status': 'preflight', 'started_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
             'output_root': str(output), 'output_files_directory': str(output / 'pretrain/diffusion'),
             'input': str(WORK / 'example/table.png'), 'question': 'wooden tabletop surface',
             'requested_gpu_uuid': selected_gpu, 'expected_host_gpu_index': KNOWN_GPUS[selected_gpu]['host_index'],
             'expected_device_minor': KNOWN_GPUS[selected_gpu]['device_minor'],
             'question_type': 0, 'seed': 1, 'model_evaluation_claim': 'One patched official example only; no quantitative evaluation or retraining.'}
    progress(state, report, 'preflight_started')
    try:
        progress(state, report, 'verify_input_and_sources')
        state['input_sha256'] = digest(WORK / 'example/table.png')
        assert state['input_sha256'] == '67ce4c07693c8814dbdb068c7184b3b6341dc8fd7a595cdaef314d0fb1c2b388'
        source = json.loads((TASK / 'example-source-manifest.json').read_text())
        for item in source['files']:
            assert digest(WORK / item['file']) == item['patched_sha256']
        assert digest(TASK / 'official-example.patch') == source['patch_sha256']
        state['source_manifest'] = source
        manifest = json.loads((TASK / 'model-source-manifest.json').read_text())
        receipt = json.loads((TASK / 'model-download-receipt.json').read_text())
        assert receipt['manifest_sha256'] == digest(TASK / 'model-source-manifest.json')
        receipts = {r['destination']: r for r in receipt['files']}
        assert len(receipts) == 21
        for index, model in enumerate(manifest['files'], 1):
            file = ROOT / model['destination']
            progress(state, report, 'model_hash_started', file=model['destination'],
                     model_index=index, model_count=len(manifest['files']), size_bytes=model['size_bytes'])
            assert file.resolve().is_relative_to(ROOT) and file.stat().st_size == model['size_bytes']
            actual_digest = digest(file, on_progress=lambda completed, total: progress(
                state, report, 'model_hash_progress', file=model['destination'],
                model_index=index, model_count=len(manifest['files']), bytes_hashed=completed, size_bytes=total))
            assert actual_digest == receipts[model['destination']]['sha256']
            progress(state, report, 'model_hash_passed', file=model['destination'],
                     model_index=index, model_count=len(manifest['files']))
        state['model_manifest_sha256'] = receipt['manifest_sha256']
        state['model_files_rehashed'] = len(receipts)
        progress(state, report, 'verify_installed_versions_and_extension_records')
        installed = {d.metadata['Name'].lower().replace('_', '-'): d.version for d in md.distributions(path=[str(SITE)])}
        required = {'torch': '2.7.1+cu128', 'torchvision': '0.22.1+cu128', 'kaolin': '0.18.0',
                    'spconv-cu126': '2.3.8', 'cumm-cu126': '0.7.11', 'flash-attn': '2.8.3',
                    'nvdiffrast': '0.3.3', 'diff-gaussian-rasterization': '0.0.0', 'clip': '1.0', 'utils3d': '0.0.2'}
        assert all(installed.get(k) == v for k, v in required.items())
        state['installed_versions'] = installed
        for case in ['kaolin', 'nvdiffrast', 'gaussian', 'flashattn']:
            successes = [p for p in TASK.glob('extension-' + case + '-*/result.json') if json.loads(p.read_text()).get('status') == 'passed']
            assert successes, 'Required extension check missing: ' + case
        assert any(json.loads(p.read_text()).get('status') == 'passed' for p in TASK.glob('sparse-check-*/result.json'))
        progress(state, report, 'initialize_torch_and_verify_selected_device')
        sys.path.insert(0, str(SITE))
        sys.path.insert(0, str(WORK))
        import torch
        assert torch.cuda.is_available() and torch.cuda.device_count() == 1
        actual = str(torch.cuda.get_device_properties(0).uuid).lower().removeprefix('gpu-')
        assert actual == selected_gpu.lower().removeprefix('gpu-')
        state['device_uuid'] = actual
        state['tf32'] = {'matmul': torch.backends.cuda.matmul.allow_tf32, 'cudnn': torch.backends.cudnn.allow_tf32}
        sys.argv = [str(WORK / 'example.py'), '--condpath', './example/table.png', '--savepath', str(output),
                    '--question', state['question'], '--question_type', '0']
        state.update(status='running_official_example', argv=sys.argv)
        progress(state, report, 'running_official_example', output=str(output))
        # The official texture optimizer needs autograd. Do not wrap this in no_grad.
        runpy.run_path(str(WORK / 'example.py'), run_name='__main__')
        progress(state, report, 'example_returned_synchronizing')
        torch.cuda.synchronize(0)
        state.update(status='example_returned', exit_code=0, output_validation='pending separate CPU validator',
                     torch_peak_allocation_bytes=torch.cuda.max_memory_allocated(0),
                     torch_peak_reserved_bytes=torch.cuda.max_memory_reserved(0))
        return 0
    except BaseException as error:
        state.update(status='failed', exit_code=1, error_type=type(error).__name__, error=str(error))
        (output / 'traceback.log').write_text(traceback.format_exc())
        traceback.print_exc()
        return 1
    finally:
        state['finished_at'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        write(report, state)
        print(json.dumps({'status': state['status'], 'exit_code': state.get('exit_code'), 'execution_record': str(report)}), flush=True)

if __name__ == '__main__':
    raise SystemExit(main())
