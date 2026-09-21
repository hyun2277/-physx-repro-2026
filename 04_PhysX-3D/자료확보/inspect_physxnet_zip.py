#!/usr/bin/env python3
"""Read PhysXNet.zip metadata and selected JSON members without extraction."""
import csv
import datetime as dt
import hashlib
import json
from pathlib import Path
import os
import sys
import traceback
import zipfile

ROOT = Path('/home/minsujo/Desktop/SH/PHYSx')
ZIP = ROOT / 'data/physxnet-download/PhysXNet.zip'
CSV = ROOT / 'repro-records/04_PhysX-3D/평가규약/2026-09-21_초안/test-input-gt-correspondence.csv'
OUTROOT = ROOT / 'logs/physxnet-download-20260921'


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def load_ids():
    with CSV.open(newline='', encoding='utf-8') as stream:
        return list(csv.DictReader(stream))


def classify_json(value):
    if not isinstance(value, dict):
        return 'UNRESOLVED', 'json_not_object'
    groups = value.get('group_info', value.get('groups', value.get('group')))
    if groups in (None, {}, [], ''):
        return 'FIXED_CANDIDATE', 'no_group_info_field_or_empty'
    if isinstance(groups, dict):
        count = len(groups)
    elif isinstance(groups, list):
        count = len(groups)
    else:
        return 'UNRESOLVED', 'group_info_unexpected_type'
    return ('ARTICULATED_CANDIDATE' if count else 'FIXED_CANDIDATE'), f'group_count={count}'


def main():
    started = dt.datetime.now(dt.timezone.utc)
    run = OUTROOT / ('inspect-' + started.strftime('%Y%m%dT%H%M%SZ') + '-' + str(os.getpid()))
    run.mkdir(parents=True, exist_ok=False)
    (run / 'command.json').write_text(json.dumps({'argv': sys.argv, 'zip': str(ZIP), 'started_at': started.isoformat(),
        'extract': False, 'paper_equivalent': False}, indent=2) + '\n')
    try:
        if not ZIP.is_file():
            raise FileNotFoundError(f'missing verified archive: {ZIP}')
        rows = load_ids()
        with zipfile.ZipFile(ZIP) as archive:
            infos = archive.infolist()
            names = {info.filename for info in infos}
            by_id = []
            for row in rows:
                object_id = row['object_id']
                json_name = next((x for x in (f'finaljson/{object_id}.json', f'PhysXNet/finaljson/{object_id}.json') if x in names), None)
                obj_prefix = next((x for x in (f'partseg/{object_id}/objs/', f'PhysXNet/partseg/{object_id}/objs/') if any(n.startswith(x) for n in names)), None)
                img_prefix = next((x for x in (f'partseg/{object_id}/img/', f'PhysXNet/partseg/{object_id}/img/') if any(n.startswith(x) for n in names)), None)
                entry = {'test_index': row['test_index_0based'], 'source_index': row['source_index_0based'],
                         'object_id': object_id, 'json_member': json_name, 'obj_prefix': obj_prefix,
                         'img_prefix': img_prefix, 'classification': 'UNRESOLVED', 'classification_reason': 'annotation_not_read'}
                if json_name:
                    try:
                        with archive.open(json_name) as stream:
                            annotation = json.load(stream)
                        entry['classification'], entry['classification_reason'] = classify_json(annotation)
                        entry['annotation_keys'] = sorted(annotation) if isinstance(annotation, dict) else []
                    except Exception as exc:
                        entry['classification_reason'] = 'json_read_error:' + type(exc).__name__
                by_id.append(entry)
            listing = [{'name': info.filename, 'bytes': info.file_size, 'compressed_bytes': info.compress_size,
                        'crc32': f'{info.CRC:08x}'} for info in infos]
            report = {'started_at': started.isoformat(), 'ended_at': dt.datetime.now(dt.timezone.utc).isoformat(),
                      'archive_bytes': ZIP.stat().st_size, 'archive_sha256': sha256_file(ZIP),
                      'member_count': len(infos), 'extracted': False, 'official_test_rows': len(rows),
                      'test_rows_missing_any_candidate': sum(not (x['json_member'] and x['obj_prefix'] and x['img_prefix']) for x in by_id),
                      'classification_counts': {key: sum(x['classification'] == key for x in by_id) for key in ['FIXED_CANDIDATE', 'ARTICULATED_CANDIDATE', 'UNRESOLVED']},
                      'paper_equivalent': False}
            (run / 'archive-members.json').write_text(json.dumps(listing, ensure_ascii=False, indent=2) + '\n')
            (run / 'test-id-annotation-report.json').write_text(json.dumps(by_id, ensure_ascii=False, indent=2) + '\n')
            (run / 'result.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 0
    except Exception as exc:
        (run / 'result.json').write_text(json.dumps({'started_at': started.isoformat(), 'ended_at': dt.datetime.now(dt.timezone.utc).isoformat(),
            'exit_code': 1, 'error_type': type(exc).__name__, 'error': str(exc), 'extracted': False, 'paper_equivalent': False}, indent=2) + '\n')
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
