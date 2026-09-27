"""Prepare fixed public model files; never import model code, install, or use GPUs.

Default --plan is read-only. --execute requires workspace_runner's download
profile. Hugging Face calls explicitly use token=False. Existing mismatches are
fatal, not overwritten. Each operation gets stdout/stderr/command/result logs;
partial transfers and completed-file receipts are preserved on failure.
"""
import argparse
import contextlib
import datetime
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import sys
import urllib.request
import uuid

ROOT = Path('/home/minsujo/Desktop/SH/PHYSx')
TASK = ROOT / 'logs/official-example-20260921'
MANIFEST = TASK / 'model-source-manifest.json'
SITE = ROOT / 'envs/physxgen/lib/python3.10/site-packages'
RECEIPT = TASK / 'model-download-receipt.json'


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def safe_path(relative):
    path = PurePosixPath(relative)
    require(not path.is_absolute() and path.parts and '..' not in path.parts,
            'Manifest path must be relative and cannot traverse parents.')
    target = ROOT.joinpath(*path.parts)
    require(target.resolve().is_relative_to(ROOT), 'Path escapes workspace.')
    for component in [target, *target.parents]:
        if component == ROOT:
            break
        require(not component.is_symlink(), 'Manifest destination cannot contain symlinks.')
    return target


def write_json(path, value):
    require(path.resolve().is_relative_to(ROOT) and not path.is_symlink(), 'Unsafe log path.')
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.partial')
    with temporary.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    os.replace(temporary, path)


def hashes(path):
    require(path.is_file() and path.resolve().is_relative_to(ROOT), 'Input must be a workspace file.')
    size = path.stat().st_size
    sha = hashlib.sha256()
    blob = hashlib.sha1(f'blob {size}\0'.encode('ascii'))
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            sha.update(block)
            blob.update(block)
    return {'size_bytes': size, 'sha256': sha.hexdigest(), 'git_blob_sha1': blob.hexdigest()}


def verify(path, item, prior=None):
    actual = hashes(path)
    require(actual['size_bytes'] == item['size_bytes'], 'Model size mismatch.')
    if item.get('sha256'):
        require(actual['sha256'] == item['sha256'], 'Model upstream SHA256 mismatch.')
    if item.get('git_blob_sha1'):
        require(actual['git_blob_sha1'] == item['git_blob_sha1'], 'Model upstream git-blob SHA1 mismatch.')
    if prior is not None:
        require(actual['sha256'] == prior['sha256'], 'Model differs from previous local download receipt.')
    actual['upstream_cryptographic_hash_verified'] = bool(item.get('sha256') or item.get('git_blob_sha1'))
    return actual


def sanitized(message):
    # Do not preserve redirected signed-query URLs or auth header/token text.
    message = re.sub(r'(https?://[^\s?\"\'<>]+)\?[^\s\"\'<>]*', r'\1?<query-omitted>', str(message))
    message = re.sub(r'(?i)(authorization\s*[:=]\s*)[^\r\n]+', r'\1<omitted>', message)
    return re.sub(r'\bhf_[A-Za-z0-9]+\b', '<token-omitted>', message)


def operation(directory, number, item, callback):
    folder = directory / f'{number:02d}-{Path(item["destination"]).name}'
    folder.mkdir(mode=0o700)
    write_json(folder / 'command.json', {
        'kind': 'python_function', 'operation': 'download_and_verify_one_model',
        'source': item['url'], 'destination': str(ROOT / item['destination']),
        'started_at': now(), 'authentication': 'none; HF token=False',
        'automatic_task_retry': False,
    })
    result = {'status': 'running', 'operation_exit_code': None,
              'exit_code_semantics': '0/1 for this Python operation; process exit is recorded by outer runner'}
    failure = None
    try:
        with (folder / 'stdout.log').open('w') as out, (folder / 'stderr.log').open('w') as err:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                try:
                    result.update(callback())
                    print(json.dumps(result, ensure_ascii=False, indent=2))
                except Exception as exc:
                    failure = exc
                    print(sanitized(type(exc).__name__ + ': ' + str(exc)), file=sys.stderr)
        result.update(status='failed' if failure else 'passed', operation_exit_code=1 if failure else 0)
    finally:
        for name in ('stdout.log', 'stderr.log'):
            path = folder / name
            if path.exists():
                path.write_text(sanitized(path.read_text(errors='replace')), encoding='utf-8')
        result['finished_at'] = now()
        write_json(folder / 'result.json', result)
    if failure:
        raise RuntimeError('Model operation failed; see sanitized per-file logs.') from None
    return result


def download_one(item, directory, previous, hf_download):
    target = safe_path(item['destination'])
    prior = previous.get(item['destination'])
    if target.exists():
        require(item.get('sha256') or item.get('git_blob_sha1') or prior,
                'Unhashed existing file has no prior local receipt; refusing reuse/overwrite.')
        return {'reused': True, 'destination': item['destination'],
                **verify(target, item, prior=prior)}
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(target.name + '.' + directory.name + '.partial')
    require(not partial.exists(), 'Partial target already exists; refusing overwrite.')
    if item['kind'] == 'huggingface':
        cached = Path(hf_download(repo_id=item['repo_id'], filename=item['filename'],
                                  revision=item['revision'], repo_type='model', token=False,
                                  cache_dir=str(ROOT / 'cache/huggingface/hub'),
                                  local_files_only=False))
        require(cached.resolve().is_relative_to(ROOT / 'cache/huggingface/hub'),
                'HF returned a path outside the workspace cache.')
        verify(cached, item)
        with cached.open('rb') as source, partial.open('xb') as output:
            shutil.copyfileobj(source, output, length=8 * 1024 * 1024)
    else:
        # No ambient proxy, cookies, password manager, auth header, or token.
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        request = urllib.request.Request(item['url'], headers={'User-Agent': 'PhysX-public-model-preparation/1'})
        with opener.open(request, timeout=120) as response, partial.open('xb') as output:
            require(response.status == 200, 'Expected HTTP 200 for complete model download.')
            length = response.headers.get('Content-Length')
            if length is not None:
                require(int(length) == item['size_bytes'], 'HTTP Content-Length differs from pinned metadata.')
            count = 0
            while True:
                block = response.read(8 * 1024 * 1024)
                if not block:
                    break
                count += len(block)
                require(count <= item['size_bytes'], 'Remote payload exceeded pinned size.')
                output.write(block)
    actual = verify(partial, item)
    require(not target.exists(), 'Destination appeared during download; refusing overwrite.')
    # link() atomically refuses an existing destination; both files are in its directory.
    os.link(partial, target)
    partial.unlink()
    return {'reused': False, 'destination': item['destination'], **actual}


def validate_manifest(manifest):
    require(manifest['schema_version'] == 1 and manifest['root'] == str(ROOT), 'Unexpected manifest root/schema.')
    require(len(manifest['files']) == 21 and manifest['file_count'] == 21, 'Expected fixed 21-file selection.')
    seen = set()
    for item in manifest['files']:
        safe_path(item['destination'])
        require(item['destination'] not in seen, 'Duplicate destination.')
        seen.add(item['destination'])
        require(item['kind'] in ('huggingface', 'url') and item['url'].startswith('https://'), 'Unexpected source type.')
        require(isinstance(item['size_bytes'], int) and item['size_bytes'] > 0, 'Expected positive pinned size.')
        require('?' not in item['url'] and '@' not in item['url'], 'Query/auth-bearing model URL prohibited.')
    require(sum(x['size_bytes'] for x in manifest['files']) == manifest['total_expected_payload_bytes'], 'Size total mismatch.')


def execute(manifest):
    require(os.environ.get('PHYSX_WORKSPACE_ISOLATED') == '1' and
            os.environ.get('PHYSX_RUN_PROFILE') == 'download', 'Use workspace_runner download profile.')
    require(os.environ.get('CUDA_VISIBLE_DEVICES') == '', 'GPU must be hidden.')
    require(not list(Path('/dev').glob('nvidia*')), 'NVIDIA device nodes must be hidden.')
    require(os.environ.get('HF_TOKEN_PATH') == '/dev/null' and
            os.environ.get('HF_HUB_DISABLE_IMPLICIT_TOKEN') == '1', 'HF credentials must be disabled.')
    for key, expected in {
        'HF_HOME': ROOT / 'cache/huggingface',
        'HF_HUB_CACHE': ROOT / 'cache/huggingface/hub',
        'TORCH_HOME': ROOT / 'cache/torch',
        'PHYSX_CLIP_DOWNLOAD_ROOT': ROOT / 'cache/clip',
    }.items():
        require(os.environ.get(key) == str(expected), 'Required cache environment mismatch: ' + key)
    for key in ('HF_TOKEN', 'HUGGING_FACE_HUB_TOKEN', 'HUGGINGFACE_HUB_CACHE', 'TRANSFORMERS_CACHE'):
        require(key not in os.environ, 'Unexpected inherited credential/cache environment variable.')
    os.environ['HF_HUB_DISABLE_XET'] = '1'
    os.environ['HF_HUB_DISABLE_PROGRESS_BARS'] = '1'
    sys.path.insert(0, str(SITE))  # Do not run site.py, .pth files, or model imports.
    from huggingface_hub import hf_hub_download

    manifest_hash = hashes(MANIFEST)['sha256']
    previous = {}
    if RECEIPT.exists():
        require(not RECEIPT.is_symlink(), 'Receipt may not be a symlink.')
        receipt = json.loads(RECEIPT.read_text())
        require(receipt['manifest_sha256'] == manifest_hash, 'Prior receipt belongs to another manifest.')
        previous = {x['destination']: x for x in receipt['files']}
    run_id = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:10]
    directory = TASK / 'model-downloads' / run_id
    directory.mkdir(parents=True, mode=0o700, exist_ok=False)
    status = {'started_at': now(), 'status': 'running', 'manifest_sha256': manifest_hash,
              'script_sha256': hashes(Path(__file__))['sha256'], 'file_count': 21,
              'completed_this_run': 0, 'model_imports': False, 'GPU_operations': False}
    write_json(directory / 'status.json', status)
    try:
        for number, item in enumerate(manifest['files'], 1):
            result = operation(directory, number, item,
                               lambda item=item: download_one(item, directory, previous, hf_hub_download))
            previous[item['destination']] = result
            write_json(RECEIPT, {'manifest_sha256': manifest_hash, 'updated_at': now(),
                                 'files': list(previous.values()),
                                 'dino_hash_limit': 'DINO SHA256 is local first-download provenance, not an upstream published hash.'})
            status['completed_this_run'] = number
            write_json(directory / 'status.json', status)
        status['status'] = 'passed'
        return 0
    except Exception as exc:
        status.update(status='failed', error=sanitized(type(exc).__name__ + ': ' + str(exc)))
        return 1
    finally:
        status['finished_at'] = now()
        status['process_exit_code'] = 0 if status['status'] == 'passed' else 1
        write_json(directory / 'status.json', status)
        print(json.dumps({'run_directory': str(directory), **status}, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--plan', action='store_true', help='Read-only manifest summary (default).')
    mode.add_argument('--execute', action='store_true', help='Download publicly, verify, and place fixed model files.')
    args = parser.parse_args()
    manifest = json.loads(MANIFEST.read_text())
    validate_manifest(manifest)
    if not args.execute:
        print(json.dumps({'executed': False, 'manifest': str(MANIFEST),
                          'manifest_sha256': hashes(MANIFEST)['sha256'],
                          'file_count': 21, 'payload_bytes': manifest['total_expected_payload_bytes'],
                          'HF_cache_additional_copy_bytes': sum(x['size_bytes'] for x in manifest['files'] if x['kind'] == 'huggingface'),
                          'dino_source': manifest['dino_source'], 'limits': manifest['limits']},
                         ensure_ascii=False, indent=2))
        return 0
    return execute(manifest)


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as error:
        print(sanitized(type(error).__name__ + ': ' + str(error)), file=sys.stderr)
        raise SystemExit(1)
