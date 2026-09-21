"""CPU-only validation of one completed official-example output directory.

Default --plan only describes checks. --execute reads existing payloads and
writes one new JSON report; it never changes outputs, runs inference, downloads,
or calls CUDA. Run via workspace_runner's offline, GPU-hidden build profile.
Only the existing imageio-ffmpeg executable is spawned for CPU video decoding.
The outer runner records actual process stdout/stderr/exit.
"""
import argparse
import datetime
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import struct
import subprocess
import sys
import time
import uuid

ROOT = Path('/home/minsujo/Desktop/SH/PHYSx')
TASK = ROOT / 'logs/official-example-20260921'
SITE = ROOT / 'envs/physxgen/lib/python3.10/site-packages'
INPUT = ROOT / 'sources/physx-4f54e750a309/example/table.png'
INPUT_SHA256 = '67ce4c07693c8814dbdb068c7184b3b6341dc8fd7a595cdaef314d0fb1c2b388'
VIDEOS = ('rgb.mp4', 'affordance.mp4', 'material.mp4', 'description.mp4')
CONDITIONAL_VIDEOS = ('kinematic_child.mp4', 'kinematic_parent.mp4')
KNOWN_GPUS = {
    'GPU-ff124b39-8b48-7d2a-bf74-bf6a5c8f1716': {'host_index': 0, 'device_minor': 0},
    'GPU-843dced4-ee97-dbb8-36c9-343fe13b7647': {'host_index': 1, 'device_minor': 1},
}


def require(value, message):
    if not value:
        raise RuntimeError(message)


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def configure_streams():
    # -I ignores PYTHONUNBUFFERED; original decoder/check progress must be live.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(line_buffering=True, write_through=True)


def progress(stage, **details):
    print(json.dumps({'kind': 'validation_progress', 'stage': stage, 'at': now(), **details},
                     ensure_ascii=False), flush=True)


def publish_report(path, report):
    require(path.parent.is_dir(), 'Create the task-local report parent before running.')
    require(not path.exists() and not path.is_symlink(), 'Refusing to overwrite an existing report.')
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.partial')
    with temporary.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')
    # link atomically publishes a complete file and refuses an existing path.
    # A failed publication preserves the partial file for inspection.
    os.link(temporary, path)
    temporary.unlink()


def workspace_path(path, *, must_exist=True):
    path = Path(path)
    require(path.is_absolute() and path.resolve().is_relative_to(ROOT), 'Path must be inside PHYSx.')
    require(not path.is_symlink(), 'Direct input/report symlink is not accepted.')
    if must_exist:
        require(path.exists(), 'Required path is missing: ' + str(path))
    return path


def fingerprint(path):
    path = workspace_path(path)
    require(path.is_file(), 'Expected a regular artifact file.')
    sha = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            sha.update(block)
    return {'path': str(path.relative_to(ROOT)), 'size_bytes': path.stat().st_size,
            'sha256': sha.hexdigest()}


def verify_provenance(args):
    image = fingerprint(INPUT)
    require(image['sha256'] == INPUT_SHA256, 'Fixed table input changed.')
    manifest_path = TASK / 'example-source-manifest.json'
    manifest = json.loads(manifest_path.read_text())
    patch = fingerprint(Path(manifest['patch']))
    require(patch['sha256'] == manifest['patch_sha256'], 'Recorded patch hash changed.')
    files = []
    for entry in manifest['files']:
        source = fingerprint(Path(manifest['original']) / entry['file'])
        patched = fingerprint(Path(manifest['work']) / entry['file'])
        require(source['sha256'] == entry['original_sha256'], 'Pinned original source changed.')
        require(patched['sha256'] == entry['patched_sha256'], 'Working source differs from its manifest.')
        files.append({'original': source, 'working': patched})
    status_path = workspace_path(args.execution_status)
    require(status_path.name == 'status.json' and status_path.parent.parent == TASK / 'runs',
            'Supply the actual workspace-runner run status.json.')
    status = json.loads(status_path.read_text())
    require(status.get('exit_code') == 0 and status.get('command_exit_code') == 0 and
            status.get('phase') == 'completed' and status.get('command_passed') is True,
            'Official-example execution did not complete with exit 0.')
    require(status.get('run_id') == status_path.parent.name, 'Run status belongs to another run directory.')
    plan_path = status_path.parent / 'plan.json'
    plan = json.loads(workspace_path(plan_path).read_text())
    selected_gpu = status.get('gpu_uuid')
    require(selected_gpu in KNOWN_GPUS, 'Run did not select one of the two known full GPU UUIDs.')
    expected_gpu = KNOWN_GPUS[selected_gpu]
    expected_command = [str(ROOT / 'envs/physxgen/bin/python'), '-I', '-B', '-S', str(TASK / 'run_example.py'),
                        '--gpu-uuid', selected_gpu]
    require(plan.get('command') == expected_command, 'GPU plan does not launch the reviewed run_example.py command.')
    require(plan.get('profile') == status.get('profile') == 'gpu' and plan.get('network_allowed') is False,
            'Expected the offline GPU execution profile.')
    require(plan.get('label') == status.get('label') and
            re.fullmatch(r'official-table(?:-[A-Za-z0-9_.-]+)?', plan.get('label', '')),
            'Expected an official-table run label (optional rerun suffix).')
    require(Path(plan.get('cwd', '')) == Path(manifest['work']), 'Example plan has the wrong working directory.')

    def gpu_identity(value):
        require(isinstance(value, str), 'Missing recorded GPU UUID.')
        value = value.lower().removeprefix('gpu-')
        require(re.fullmatch(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', value),
                'Invalid recorded GPU UUID.')
        return value

    gpu = gpu_identity(plan.get('gpu_uuid'))
    require(plan.get('gpu_uuid') == selected_gpu and gpu == gpu_identity(selected_gpu), 'Plan/status GPU UUID differs.')
    require(plan.get('gpu_index') == status.get('gpu_index') and
            plan.get('device_minor') == status.get('device_minor'), 'Plan/status GPU index or minor differs.')
    require(type(plan.get('gpu_index')) is int and type(plan.get('device_minor')) is int and
            plan['gpu_index'] == expected_gpu['host_index'] and plan['device_minor'] == expected_gpu['device_minor'],
            'GPU UUID does not match its known host index/device-minor mapping.')
    mapping_path = status_path.parent / 'device-mapping.json'
    mapping = json.loads(workspace_path(mapping_path).read_text())
    require(gpu == gpu_identity(mapping.get('gpu_uuid')) and
            mapping.get('device_minor') == plan.get('device_minor'), 'Driver device mapping differs from the GPU plan.')

    output = workspace_path(args.output_dir)
    require(output.name == 'diffusion' and output.parent.name == 'pretrain', 'Expected savepath/pretrain/diffusion output.')
    output_root = output.parent.parent
    require(output_root.parent == ROOT / 'outputs/official-example' and output_root.name.startswith('table-'),
            'Expected the unique official table output directory.')
    execution_path = output_root / 'execution.json'
    execution = json.loads(workspace_path(execution_path).read_text())
    require(execution.get('status') == 'example_returned' and execution.get('exit_code') == 0,
            'The selected output tree has no successful example_returned record.')
    require(execution.get('output_files_directory') == str(output) and
            execution.get('output_root') == str(output_root), 'Execution record points to another output tree.')
    require(execution.get('source_manifest') == manifest, 'Execution source/patch manifest differs from the reviewed current manifest.')
    require(execution.get('seed') == 1 and execution.get('question_type') == 0 and
            execution.get('question') == args.expected_question, 'Execution record has different example conditions.')
    expected_input = Path(manifest['work']) / 'example/table.png'
    require(execution.get('input') == str(expected_input) and execution.get('input_sha256') == INPUT_SHA256,
            'Execution record uses another input path/hash.')
    working_image = fingerprint(expected_input)
    require(working_image['sha256'] == INPUT_SHA256, 'Working-copy table input changed.')
    require(gpu_identity(execution.get('device_uuid')) == gpu, 'Output execution GPU UUID differs from supplied run.')
    require(execution.get('requested_gpu_uuid') == selected_gpu and
            execution.get('expected_host_gpu_index') == expected_gpu['host_index'] and
            execution.get('expected_device_minor') == expected_gpu['device_minor'],
            'Example launcher recorded another requested GPU mapping.')
    expected_example_argv = [str(Path(manifest['work']) / 'example.py'), '--condpath', './example/table.png',
                             '--savepath', str(output_root), '--question', args.expected_question, '--question_type', '0']
    require(execution.get('argv') == expected_example_argv, 'Recorded example argv does not match this output/input/query.')
    model_manifest = fingerprint(TASK / 'model-source-manifest.json')
    require(execution.get('model_manifest_sha256') == model_manifest['sha256'] and
            execution.get('model_files_rehashed') == 21, 'Execution did not verify the selected 21-model manifest.')

    command_result_path = status_path.parent / 'command/result.json'
    command_result = json.loads(workspace_path(command_result_path).read_text())
    command_argv = command_result.get('argv', [])
    require(command_result.get('exit_code') == 0 and command_result.get('process_started') is True,
            'Actual GPU command lacks a successful process result.')
    require(command_argv and command_argv[0] == '/usr/bin/bwrap' and '--unshare-net' in command_argv and
            command_argv[-len(expected_command):] == expected_command,
            'Actual GPU command differs from the reviewed offline example launcher.')
    for key, value in [('PHYSX_RUN_PROFILE', 'gpu'), ('CUDA_VISIBLE_DEVICES', plan['gpu_uuid']),
                       ('HF_HUB_OFFLINE', '1')]:
        require(any(command_argv[i:i + 3] == ['--setenv', key, value] for i in range(len(command_argv) - 2)),
                'Actual command is missing the expected GPU/offline environment: ' + key)

    def timestamp(value):
        result = datetime.datetime.fromisoformat(value.replace('Z', '+00:00'))
        require(result.tzinfo is not None, 'Expected timezone-aware execution timestamps.')
        return result

    require(timestamp(command_result['started_at']) <= timestamp(execution['started_at']) <=
            timestamp(execution['finished_at']) <= timestamp(command_result['ended_at']),
            'Output execution timestamps are outside the supplied GPU command interval.')
    # Bind the chosen output to this outer run, even when two successful GPU
    # runs share the same command, input, patch and UUID.
    stdout_path = workspace_path(status_path.parent / 'command/stdout.log')
    final_records = []
    with stdout_path.open(encoding='utf-8', errors='replace') as stream:
        for line in stream:
            if not line.lstrip().startswith('{'):
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict) and 'execution_record' in value:
                final_records.append(value)
    require(len(final_records) == 1 and final_records[0].get('execution_record') == str(execution_path) and
            final_records[0].get('status') == 'example_returned' and final_records[0].get('exit_code') == 0,
            'Supplied GPU stdout is not the successful launcher record for this output tree.')
    return {'input': image, 'source_manifest': fingerprint(manifest_path), 'source_files': files,
            'patch': patch, 'execution_status': fingerprint(status_path),
            'execution_plan': fingerprint(plan_path), 'execution_record': fingerprint(execution_path),
            'working_input': working_image, 'device_mapping': fingerprint(mapping_path),
            'actual_command_result': fingerprint(command_result_path), 'launcher_stdout': fingerprint(stdout_path),
            'launcher': fingerprint(TASK / 'run_example.py'), 'model_manifest': model_manifest,
            'gpu_uuid': gpu, 'output_bound_to_supplied_run': True,
            'recorded_conditions': manifest['conditions_preserved'],
            'scientific_limit': manifest['scientific_limit'],
            'limit': 'Binds trusted local records, timestamps and stdout to one run/output; not tamper-proof attestation or proof of prior process memory state.'}


def finite_tensor(tensor, torch):
    require(isinstance(tensor, torch.Tensor) and tensor.device.type == 'cpu', 'Expected a CPU tensor.')
    require(tensor.layout == torch.strided, 'Expected a dense tensor.')
    flat = tensor.reshape(-1)
    require(flat.numel() > 0, 'Raw prediction tensor is empty.')
    # Bound intermediate CPU masks; no CUDA calls or model deserialization.
    for start in range(0, flat.numel(), 1024 * 1024):
        require(bool(torch.isfinite(flat[start:start + 1024 * 1024]).all()), 'Raw prediction tensor is nonfinite.')
    return {'shape': list(tensor.shape), 'dtype': str(tensor.dtype), 'device': str(tensor.device),
            'numel': tensor.numel(), 'finite': True,
            'minimum': float(flat.min()), 'maximum': float(flat.max())}


def check_raw(output, diagnostics, torch):
    path = output / 'raw-prediction.pt'
    raw = torch.load(path, map_location='cpu', weights_only=True)
    require(isinstance(raw, dict), 'Raw prediction must be a tensor dictionary.')
    required = ('vertices', 'faces', 'physical', 'language', 'score')
    require(all(key in raw for key in required), 'Raw prediction lacks required tensors.')
    tensors = {}
    for key, value in raw.items():
        if isinstance(value, torch.Tensor):
            tensors[key] = finite_tensor(value, torch)
    vertices, faces = raw['vertices'], raw['faces']
    require(vertices.ndim == 2 and vertices.shape[1] == 3, 'Raw vertices must have shape [N,3].')
    require(faces.ndim == 2 and faces.shape[1] == 3 and not faces.is_floating_point(),
            'Raw triangle faces must be an integer [M,3] tensor.')
    require(int(faces.min()) >= 0 and int(faces.max()) < len(vertices), 'Raw face indices are out of bounds.')
    count = len(vertices)
    require(raw['physical'].shape == (count, 14), 'Expected one 14-channel physical prediction per vertex.')
    require(raw['language'].shape[0] == count and raw['language'].numel() == count * 3072,
            'Expected 3072 language values per vertex.')
    require(raw['score'].numel() == count, 'Expected one query score per vertex.')
    require(diagnostics['vertices'] == count and diagnostics['faces'] == len(faces),
            'Diagnostics geometry counts differ from raw predictions.')
    group = raw.get('num_group', diagnostics['num_group'])
    require(type(group) is int and group >= 1 and group == diagnostics['num_group'], 'Invalid/inconsistent group count.')
    return {'artifact': fingerprint(path), 'tensors': tensors, 'num_group': group,
            'note': 'physical values may already have the official unit conversion; see raw keys and source patch. Finite values do not establish physical or semantic accuracy.'}


def check_raw_heads(output, diagnostics, torch):
    path = output / 'raw-model-heads.pt'
    raw = torch.load(path, map_location='cpu', weights_only=True)
    required = ('vertices', 'faces', 'mesh_properties', 'physical_before_unit_conversion', 'language')
    require(isinstance(raw, dict) and all(key in raw for key in required), 'Raw model heads lack required tensors.')
    tensors = {key: finite_tensor(raw[key], torch) for key in required}
    vertices, faces = raw['vertices'], raw['faces']
    require(vertices.ndim == 2 and vertices.shape[1] == 3, 'Raw model-head vertices must have shape [N,3].')
    require(faces.ndim == 2 and faces.shape[1] == 3 and not faces.is_floating_point(),
            'Raw model-head faces must be an integer [M,3] tensor.')
    require(int(faces.min()) >= 0 and int(faces.max()) < len(vertices), 'Raw model-head face indices are out of bounds.')
    count = len(vertices)
    require(raw['mesh_properties'].shape == (count, 32), 'Expected 32 latent mesh-property channels per vertex.')
    require(raw['physical_before_unit_conversion'].shape == (count, 14), 'Expected 14 raw physical channels per vertex.')
    require(raw['language'].shape[0] == count and raw['language'].numel() == count * 3072,
            'Expected 3072 raw language values per vertex.')
    if diagnostics:
        require(diagnostics['vertices'] == count and diagnostics['faces'] == len(faces),
                'Diagnostics geometry counts differ from raw model heads.')
    return {'artifact': fingerprint(path), 'tensors': tensors,
            'note': 'Saved before physical-unit conversion, heatmap normalization and group rounding; shape/finite checks only.'}


def video_check(path, ffmpeg, imageio_ffmpeg, np, decoder_commands):
    artifact = fingerprint(path)
    require(artifact['size_bytes'] > 0, 'Video is empty.')
    # Strict decode failure detection plus separate actual frame enumeration.
    command = [str(ffmpeg), '-nostdin', '-v', 'error', '-xerror', '-err_detect', 'explode',
               '-hwaccel', 'none', '-protocol_whitelist', 'file,pipe', '-i', str(path),
               '-map', '0:v:0', '-an', '-f', 'null', '-']
    result = subprocess.run(command, stdin=subprocess.DEVNULL, capture_output=True,
                            timeout=180, check=False, text=True)
    execution = {'argv': command, 'exit_code': result.returncode,
                 'stdout': result.stdout, 'stderr': result.stderr}
    decoder_commands.append(execution)
    require(result.returncode == 0, 'Strict CPU ffmpeg decode failed: ' + result.stderr[-1000:])
    reader = imageio_ffmpeg.read_frames(str(path), pix_fmt='rgb24',
                                       input_params=['-nostdin', '-hwaccel', 'none',
                                                     '-protocol_whitelist', 'file,pipe'])
    frame_hashes = []
    minimum, maximum = 255, 0
    try:
        metadata = next(reader)
        width, height = metadata['size']
        require(width > 0 and height > 0, 'Video has invalid dimensions.')
        require(math.isfinite(metadata['fps']) and abs(metadata['fps'] - 30) < 0.01,
                'Official video must have 30 fps metadata.')
        for frame in reader:
            require(len(frame) == width * height * 3, 'Decoded frame size mismatch.')
            pixels = np.frombuffer(frame, dtype=np.uint8)
            minimum = min(minimum, int(pixels.min()))
            maximum = max(maximum, int(pixels.max()))
            frame_hashes.append(hashlib.sha256(frame).hexdigest())
            require(len(frame_hashes) <= 30, 'Video contains more than the expected 30 frames.')
    finally:
        reader.close()
    require(len(frame_hashes) == 30, 'Video has fewer than the expected 30 decoded frames.')
    return {'artifact': artifact, 'strict_decode': execution, 'decoder': 'imageio_ffmpeg.read_frames; rgb24 CPU',
            'metadata': metadata, 'decoded_frames': len(frame_hashes), 'decoded_frame_sha256': frame_hashes,
            'unique_decoded_frames': len(set(frame_hashes)), 'pixel_minimum': minimum, 'pixel_maximum': maximum,
            'limit': 'Decodability and finite uint8 pixels do not certify object quality, colors, or semantic heatmaps.'}


def glb_json(data):
    require(len(data) >= 20, 'GLB is too short.')
    magic, version, length = struct.unpack_from('<4sII', data, 0)
    require(magic == b'glTF' and version == 2 and length == len(data), 'Invalid GLB header/length.')
    size, kind = struct.unpack_from('<II', data, 12)
    require(kind == 0x4E4F534A and 20 + size <= len(data), 'GLB has no valid initial JSON chunk.')
    document = json.loads(data[20:20 + size].decode('utf-8'))

    def reject_external(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if key == 'uri':
                    require(isinstance(child, str) and child.startswith('data:'), 'External GLB resource URI prohibited.')
                reject_external(child)
        elif isinstance(value, list):
            for child in value:
                reject_external(child)
    reject_external(document)
    return document


def mesh_check(mesh, np, *, require_texture):
    vertices, faces = np.asarray(mesh.vertices), np.asarray(mesh.faces)
    require(vertices.ndim == 2 and vertices.shape[0] > 0 and vertices.shape[1] == 3 and np.isfinite(vertices).all(),
            'Mesh geometry is empty or nonfinite.')
    require(faces.ndim == 2 and faces.shape[0] > 0 and faces.shape[1] == 3 and
            np.issubdtype(faces.dtype, np.integer), 'Mesh lacks integer triangle faces.')
    require(faces.min() >= 0 and faces.max() < len(vertices), 'Mesh faces are out of bounds.')
    result = {'vertices': len(vertices), 'faces': len(faces), 'finite_geometry': True,
              'bounds': np.asarray(mesh.bounds).tolist()}
    if require_texture:
        uv = np.asarray(getattr(mesh.visual, 'uv', None))
        require(uv.shape == (len(vertices), 2) and np.isfinite(uv).all(), 'Mesh has missing/nonfinite UV coordinates.')
        material = getattr(mesh.visual, 'material', None)
        image = getattr(material, 'baseColorTexture', None)
        if image is None:
            image = getattr(material, 'image', None)
        require(image is not None, 'Mesh has no decoded base-color texture.')
        image.load()
        pixels = np.asarray(image)
        require(image.size == (1024, 1024) and pixels.size > 0 and np.isfinite(pixels).all(),
                'Expected a finite 1024x1024 texture from the official configuration.')
        result['texture'] = {'size': list(image.size), 'mode': image.mode, 'finite': True,
                             'pixel_sha256': hashlib.sha256(pixels.tobytes()).hexdigest(),
                             'minimum': float(pixels.min()), 'maximum': float(pixels.max())}
        result['finite_uv'] = True
    return result


def check_glb(path, trimesh, np):
    data = path.read_bytes()
    document = glb_json(data)
    scene = trimesh.load_scene(io.BytesIO(data), file_type='glb', resolver={}, process=False)
    require(len(scene.geometry) > 0, 'GLB contains no geometry.')
    geometry = {str(name): mesh_check(mesh, np, require_texture=True) for name, mesh in scene.geometry.items()}
    for node in scene.graph.nodes_geometry:
        require(np.isfinite(scene.graph[node][0]).all(), 'GLB scene transform is nonfinite.')
    return {'artifact': fingerprint(path), 'geometry': geometry, 'embedded_images': len(document.get('images', [])),
            'finite_scene_transforms': True, 'external_resources': False,
            'limit': 'No accuracy, watertightness, scale correctness, texture alignment, or paper metric is certified.'}


def check_obj(path, trimesh, np):
    data = path.read_text()
    # The official concatenated OBJ may mention an exported MTL. Geometry-only
    # inspection intentionally blocks resolver access and does not load it.
    scene = trimesh.load_scene(io.StringIO(data), file_type='obj', resolver={},
                               process=False, skip_materials=True)
    require(len(scene.geometry) > 0, 'Conditional kinematic OBJ contains no geometry.')
    return {'artifact': fingerprint(path), 'geometry': {
        str(name): mesh_check(mesh, np, require_texture=False) for name, mesh in scene.geometry.items()},
        'limit': 'Geometry validity does not validate kinematic parent assignment, type, axis, or range.'}


def main():
    configure_streams()
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--plan', action='store_true')
    mode.add_argument('--execute', action='store_true')
    parser.add_argument('--output-dir', type=Path, required=True,
                        help='Actual directory containing rgb.mp4, e.g. savepath/pretrain/diffusion.')
    parser.add_argument('--execution-status', type=Path, required=True, help='Completed GPU run status.json.')
    parser.add_argument('--report', type=Path, required=True, help='New JSON path under logs/official-example-20260921.')
    parser.add_argument('--expected-question', default='wooden tabletop surface')
    args = parser.parse_args()
    output = workspace_path(args.output_dir, must_exist=args.execute)
    report_path = workspace_path(args.report, must_exist=False)
    require(report_path.resolve().is_relative_to(TASK) and report_path.suffix == '.json', 'Report must be task-local JSON.')
    require(not report_path.exists(), 'Refusing to overwrite an existing report.')
    if not args.execute:
        print(json.dumps({'executed': False, 'output_directory': str(output), 'report': str(report_path),
                          'checks': ['successful run exit', 'source/input hashes', 'diagnostics seed/question',
                                     'raw CPU tensors finite/shape/index checks', 'four videos decode 30 frames at 30 fps',
                                     'GLB finite geometry/UV/embedded 1024 texture', 'conditional kinematic artifacts'],
                          'payload_mutation': False, 'GPU_calls': False, 'inference': False}, indent=2))
        return 0
    require(os.environ.get('PHYSX_WORKSPACE_ISOLATED') == '1' and
            os.environ.get('PHYSX_RUN_PROFILE') == 'build', 'Use the offline GPU-hidden build profile for CPU validation.')
    require(os.environ.get('CUDA_VISIBLE_DEVICES') == '' and not list(Path('/dev').glob('nvidia*')),
            'GPU must be hidden for this CPU validator.')
    require(os.environ.get('HF_HUB_OFFLINE') == '1', 'Offline profile required.')
    sys.path.insert(0, str(SITE))  # No site.py/.pth or project model imports.
    report = {'started_at': now(), 'status': 'running', 'issues': [], 'checks': {},
              'script': fingerprint(Path(__file__)), 'output_directory': str(output),
              'GPU_calls': False, 'inference': False, 'payload_mutation': False,
              'decoder_commands': []}
    progress('validation_started', output_directory=str(output), report=str(report_path))

    def check(name, callback):
        started = time.monotonic()
        progress('check_started', check=name)
        try:
            report['checks'][name] = {'status': 'passed', 'result': callback()}
            return report['checks'][name]['result']
        except Exception as error:
            message = type(error).__name__ + ': ' + str(error)
            report['checks'][name] = {'status': 'failed', 'error': message}
            report['issues'].append({'check': name, 'error': message})
            return None
        finally:
            progress('check_finished', check=name, status=report['checks'].get(name, {}).get('status', 'interrupted'),
                     elapsed_seconds=round(time.monotonic() - started, 3))

    try:
        progress('import_cpu_validation_dependencies')
        import numpy as np
        import torch
        import trimesh
        import imageio_ffmpeg
        require(sys.version_info[:2] == (3, 10), 'Use the target Python3.10 interpreter.')
        report['versions'] = {'python': sys.version.split()[0], 'torch': str(torch.__version__),
                              'numpy': np.__version__, 'trimesh': trimesh.__version__,
                              'imageio_ffmpeg': imageio_ffmpeg.__version__}
        ffmpeg_candidates = list((SITE / 'imageio_ffmpeg/binaries').glob('ffmpeg-linux-x86_64-*'))
        require(len(ffmpeg_candidates) == 1, 'Expected exactly one wheel-provided ffmpeg executable.')
        ffmpeg = workspace_path(ffmpeg_candidates[0])
        os.environ['IMAGEIO_FFMPEG_EXE'] = str(ffmpeg)
        report['ffmpeg'] = fingerprint(ffmpeg)
        check('provenance', lambda: verify_provenance(args))

        def read_diagnostics():
            value = json.loads((output / 'prediction-diagnostics.json').read_text())
            require(value.get('seed') == 1 and value.get('question') == args.expected_question and
                    value.get('question_type') == 0, 'Unexpected seed/question/question_type.')
            require(value.get('finite_geometry_properties_and_heatmaps') is True, 'Source finite diagnostics did not pass.')
            require(type(value.get('num_group')) is int and value['num_group'] >= 1, 'Invalid group count.')
            return {'artifact': fingerprint(output / 'prediction-diagnostics.json'), 'values': value}

        diagnostics = check('diagnostics', read_diagnostics)
        check('raw_model_heads', lambda: check_raw_heads(output, diagnostics['values'] if diagnostics else None, torch))
        if diagnostics:
            check('raw_prediction', lambda: check_raw(output, diagnostics['values'], torch))
        else:
            report['checks']['raw_prediction'] = {'status': 'not_run', 'reason': 'No valid diagnostics for cross-check.'}
        for name in VIDEOS:
            check(name, lambda name=name: video_check(output / name, ffmpeg, imageio_ffmpeg, np, report['decoder_commands']))
        check('texture.glb', lambda: check_glb(output / 'texture.glb', trimesh, np))
        group = diagnostics['values']['num_group'] if diagnostics else None
        for name in CONDITIONAL_VIDEOS:
            if group is not None and group > 1 or (output / name).exists():
                check(name, lambda name=name: video_check(output / name, ffmpeg, imageio_ffmpeg, np, report['decoder_commands']))
            else:
                report['checks'][name] = {'status': 'not_required' if group == 1 else 'unknown_condition'}
        if group is not None and group > 1 or (output / 'kinematic.obj').exists():
            check('kinematic.obj', lambda: check_obj(output / 'kinematic.obj', trimesh, np))
        else:
            report['checks']['kinematic.obj'] = {'status': 'not_required' if group == 1 else 'unknown_condition'}
        progress('hash_output_inventory')
        report['all_output_files'] = []
        for path in sorted(output.iterdir()):
            if path.is_file():
                progress('hash_output_file_started', file=path.name, size_bytes=path.stat().st_size)
                report['all_output_files'].append(fingerprint(path))
                progress('hash_output_file_finished', file=path.name)
        report['limits'] = [
            'This is a patched-example artifact integrity check, not an unchanged-upstream baseline or paper reproduction metric.',
            'Parent-group inference/aggregation remains unmodified and unvalidated; valid conditional artifacts do not establish its correctness.',
            'Visual quality, language grounding, physical units/accuracy and kinematic semantics need separate interpretation.',
            'CPU torch.load uses weights_only=True and map_location=cpu; no project model class is imported.',
        ]
    except Exception as error:
        report['issues'].append({'check': 'validator_setup_or_finalization', 'error': type(error).__name__ + ': ' + str(error)})
    report.update(status='passed' if not report['issues'] else 'failed', finished_at=now())
    report['exit_code'] = 0 if report['status'] == 'passed' else 1
    progress('publish_final_report', status=report['status'])
    publish_report(report_path, report)
    print(json.dumps({'status': report['status'], 'exit_code': report['exit_code'],
                      'issues': report['issues'], 'report': str(report_path)}, ensure_ascii=False, indent=2), flush=True)
    return report['exit_code']


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as error:
        print(type(error).__name__ + ': ' + str(error), file=sys.stderr)
        raise SystemExit(1)
