#!/usr/bin/env python3
"""CPU-only readiness gate for public-only density/affordance map evaluation.

This program deliberately writes blocked records instead of inventing a renderer,
vertex-to-part correspondence, value range, or benchmark camera rule.  Its small
masked-map primitive is exercised only on synthetic fixtures.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

ROOT = Path('/home/minsujo/Desktop/SH/PHYSx')
HERE = Path(__file__).resolve().parent
ARTIFACTS = HERE / '2026-09-27_public-only-v1-eleven-actual' / 'manifest.json'
# Preserve the first incomplete, validation-failed draft rather than overwriting it.
OUT = HERE / '2026-09-27_public-only-v1-density-affordance-readiness-r2'
SOURCE = ROOT / 'sources/physx-4f54e750a309'


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def finite_maps(pred, gt, pred_mask, gt_mask):
    if not (len(pred) == len(gt) == len(pred_mask) == len(gt_mask)):
        raise ValueError('map and mask shapes differ')
    for values in (pred, gt):
        if any(not isinstance(x, (int, float)) or not math.isfinite(x) for x in values):
            raise ValueError('map contains NaN or Inf')
    if any(type(x) is not bool for x in [*pred_mask, *gt_mask]):
        raise ValueError('mask is not boolean')


def masked_diagnostic(pred, gt, pred_mask, gt_mask):
    """Raw-unit error only; deliberately no arbitrary PSNR range."""
    finite_maps(pred, gt, pred_mask, gt_mask)
    intersection = [i for i, (a, b) in enumerate(zip(pred_mask, gt_mask)) if a and b]
    union = [i for i, (a, b) in enumerate(zip(pred_mask, gt_mask)) if a or b]
    if not intersection:
        raise ValueError('empty intersection mask')
    errors = [float(pred[i]) - float(gt[i]) for i in intersection]
    mae = math.fsum(abs(x) for x in errors) / len(errors)
    rmse = math.sqrt(math.fsum(x * x for x in errors) / len(errors))
    return {
        'metric_authority': 'proposal', 'paper_equivalent': False,
        'raw_unit_mae_intersection': mae, 'raw_unit_rmse_intersection': rmse,
        'intersection_pixels': len(intersection), 'union_pixels': len(union),
        'mask_iou': len(intersection) / len(union) if union else 1.0,
        'pred_coverage': sum(pred_mask) / len(pred_mask),
        'gt_coverage': sum(gt_mask) / len(gt_mask),
        'union_error': 'not computed: unmatched pixels have no valid counterpart',
    }


def cameras():
    """Candidate only: source render_multiview Hammersley yaw/pitch, r=2/FOV=40.

    It is serialised as camera positions plus target/up rather than asserting an
    unverified utils3d matrix convention.  It is not used for a score.
    """
    result = []
    for i in range(30):
        u = i / 30
        # source hammersley_sequence(2, i, 30): second component is radical inverse base 2.
        n, inv, v = i, 0.5, 0.0
        while n:
            v += (n % 2) * inv
            n //= 2
            inv *= 0.5
        pitch = math.acos(1 - 2 * u) - math.pi / 2
        yaw = v * 2 * math.pi
        position = [2 * math.sin(yaw) * math.cos(pitch),
                    2 * math.cos(yaw) * math.cos(pitch), 2 * math.sin(pitch)]
        result.append({'view_id': f'hammersley_{i:02d}', 'yaw_rad': yaw,
                       'pitch_rad': pitch, 'position': position,
                       'target': [0.0, 0.0, 0.0], 'up': [0.0, 0.0, 1.0],
                       'fov_deg': 40.0, 'resolution': 512, 'radius': 2.0})
    return result


def synthetic_validation(camera_hash):
    identical = masked_diagnostic([2.0, 2.0], [2.0, 2.0], [True, True], [True, True])
    different = masked_diagnostic([3.0, 2.0], [2.0, 2.0], [True, True], [True, True])
    split = masked_diagnostic([0.0, 0.0, 0.0], [0.0, 1.0, 0.0], [True, True, False], [False, True, True])
    rejected = {}
    for label, args in {
        'empty_intersection': ([0.0], [0.0], [True], [False]),
        'nonfinite': ([float('nan')], [0.0], [True], [True]),
    }.items():
        try:
            masked_diagnostic(*args)
        except ValueError as exc:
            rejected[label] = str(exc)
        else:
            raise AssertionError(f'{label} was accepted')
    if identical['raw_unit_mae_intersection'] != 0 or identical['raw_unit_rmse_intersection'] != 0:
        raise AssertionError('identical map did not yield zero error')
    if different['raw_unit_mae_intersection'] <= identical['raw_unit_mae_intersection']:
        raise AssertionError('different map did not increase error')
    if (split['intersection_pixels'], split['union_pixels'], split['mask_iou']) != (1, 3, 1 / 3):
        raise AssertionError('intersection/union accounting changed')
    if camera_hash != hashlib.sha256((json.dumps(cameras(), indent=2, sort_keys=True).encode() + b'\n')).hexdigest():
        raise AssertionError('camera manifest is not reproducible')
    return {'status': 'pass', 'identical_map': identical, 'different_map': different,
            'intersection_union_fixture': split, 'rejected': rejected,
            'camera_manifest_sha256_reproducible': camera_hash,
            'failed_sample_denominator_rule': 'blocked/failed samples are excluded from numeric metric denominators'}


def main():
    if OUT.exists():
        raise RuntimeError(f'refusing to overwrite {OUT}')
    items = json.loads(ARTIFACTS.read_text())['items']
    if len(items) != 11 or any(x['status'] != 'success' for x in items):
        raise RuntimeError('eleven-artifact manifest changed or is incomplete')
    OUT.mkdir(parents=True)
    camera = cameras()
    camera_bytes = json.dumps(camera, indent=2, sort_keys=True).encode() + b'\n'
    camera_hash = hashlib.sha256(camera_bytes).hexdigest()
    (OUT / 'camera_manifest.json').write_bytes(camera_bytes)
    validation = synthetic_validation(camera_hash)
    (OUT / 'synthetic_validation.json').write_text(json.dumps(validation, indent=2) + '\n')
    audit = {
        'source_head': '4f54e750a309fe9cd9f20816916ecc0e8a9ae594',
        'findings': [
            {'topic': 'GT density', 'status': 'confirmed', 'evidence': 'merge_property.py:138-148 reads density.split()[0] and stores it as property index 2; inspected JSON strings use g/cm^3.'},
            {'topic': 'GT affordance', 'status': 'confirmed', 'evidence': 'merge_property.py:138-148 reads priority_rank as integer and stores it as property index 1.'},
            {'topic': 'training normalization', 'status': 'confirmed', 'evidence': 'structured_latent_vae_mesh.py:212-218 maps channel 1 to 1-rank/10 and channel 2 to (density-2.3)/2.8 under target mask.'},
            {'topic': 'property head output', 'status': 'confirmed', 'evidence': 'config:property_output sets 14 physical channels; decoder_mesh.py:359-368 applies only a Conv2d output layer. The normalized semantic interpretation follows the training loss, not an output activation.'},
            {'topic': 'example display', 'status': 'confirmed', 'evidence': 'example.py:179-192 applies the property head; :182-185 inverse-affines selected channels; :190-192 min-max normalizes density/material and affordance per object for display.'},
            {'topic': 'GT numeric maps', 'status': 'blocked', 'evidence': 'example_render_gt_foreval.py:152-169 uses stale meshname instead of part; :172-181 passes MeshExtractResult to render_video_gt, whose render_utils.py:117-125 indexes gt[0:3]. No successful metric-ready GT rendering is established.'},
            {'topic': 'mask/camera', 'status': 'partial', 'evidence': 'render_utils.py:117-125 specifies a 30-frame orbit, r=2/FOV=40/resolution=512 and returns mask/allphy_map. It is not established as the paper random unit-sphere condition, and no map scorer consumes it.'},
            {'topic': 'PSNR', 'status': 'blocked', 'evidence': 'loss_utils.py:34-36 supplies max_val=1 default only; no official density/affordance caller fixes global range, mask policy, camera manifest, or view-to-test aggregation.'},
            {'topic': 'generated-to-GT correspondence', 'status': 'blocked', 'evidence': 'current generated meshes/raw property arrays have no official vertex/face/part correspondence to PhysXNet parts; bbox/nearest/ICP would be a new unvalidated rule.'}
        ]
    }
    (OUT / 'source_audit.json').write_text(json.dumps(audit, indent=2) + '\n')
    protocol = {
        'name': 'public-only density/affordance map protocol draft', 'executable': False,
        'paper_equivalent': False, 'psnr_computed': False,
        'candidate_camera_manifest': {'path': 'camera_manifest.json', 'sha256': camera_hash,
                                      'status': 'draft only; not used for metrics'},
        'future_proposed_rules_if_prerequisites_are_supplied': {
            'views': 'the fixed 30 camera records in camera_manifest.json',
            'alignment': 'must be a single predeclared GT/pred transform; not supplied or invented here',
            'map_resolution': 512,
            'errors': 'raw-unit MAE/RMSE over the intersection mask; record mask IoU and both coverages',
            'psnr': 'only after a fixed shared value range, masking rule, and map provenance are established',
            'aggregation': 'mean views within each successful sample, then mean samples; failed/blocked samples excluded'
        },
        'blocking_prerequisites': [
            'metric-ready GT density/affordance maps from a valid official path',
            'official or explicitly adopted generated-mesh to GT-part correspondence',
            'paired numeric renderer and masks in one coordinate/camera convention',
            'fixed shared range/normalization and aggregation rule for PSNR'
        ],
        'description_psnr': 'blocked unchanged', 'kinematics_cov_mmd': 'blocked unchanged'
    }
    (OUT / 'protocol.json').write_text(json.dumps(protocol, indent=2) + '\n')
    reasons = '; '.join(protocol['blocking_prerequisites'])
    rows = []
    for item in items:
        for metric in ('density_map', 'affordance_map'):
            rows.append({'object_id': item['object_id'], 'metric': metric, 'status': 'blocked',
                         'reason': reasons, 'generated_mesh_sha256': item['files']['generated_mesh']['sha256'],
                         'property_sha256': item['files']['property']['sha256'], 'gt_json_sha256': item['files']['gt_json']['sha256']})
    (OUT / 'map_results.json').write_text(json.dumps({'status': 'blocked', 'paper_equivalent': False, 'rows': rows}, indent=2) + '\n')
    header = list(rows[0])
    (OUT / 'map_results.csv').write_text(','.join(header) + '\n' + '\n'.join(','.join(str(row[k]).replace(',', ';') for k in header) for row in rows) + '\n')
    ledger = [
        {'object_id': '23787', 'status': 'failed', 'reason': 'official texture retrieval output non-finite OBJ', 'numeric_denominator': False},
        {'object_id': '27281', 'status': 'excluded', 'reason': 'mesh decoder OOM under retained 28000 MiB/4607 MiB policy', 'numeric_denominator': False},
        {'object_id': '14567', 'status': 'failed', 'reason': 'verified source MTL has no map_Kd texture reference', 'numeric_denominator': False},
        {'object_id': '11 artifact-complete samples', 'status': 'map_metrics_blocked', 'reason': reasons, 'numeric_denominator': False}
    ]
    (OUT / 'failure_ledger.json').write_text(json.dumps(ledger, indent=2) + '\n')
    comparison = 'topic,official_paper_condition,official_code_condition,public_only_action,unknown_or_missing\n'
    comparison += 'density/affordance PSNR,PSNR maps,training normalization exists but evaluator absent,blocked; no PSNR,global range/mask/camera/aggregation\n'
    comparison += 'GT map,metric-ready target,GT script saves arrays but has static call/part-loop defects,blocked,validated GT map provenance\n'
    comparison += 'correspondence,not stated in public evaluator,none found,blocked,no generated-mesh to GT-part rule\n'
    comparison += 'camera,30 random unit-sphere views,30 orbit and deterministic Hammersley helpers exist,candidate manifest only,seed/matrix/paper equivalence\n'
    (OUT / 'conditions_comparison.csv').write_text(comparison)
    readme = '''# Density and affordance map readiness\n\nThis is a CPU-only public-materials audit, not PhysX-3D Table 2 or a paper-identical evaluation. The 11 artifact-complete samples retain their existing geometry/scale/group results, but **all 22 density/affordance map rows are blocked**. No PSNR, MAE, or RMSE was calculated from those samples.\n\nThe official preprocessing confirms density is read from the numeric prefix of a `g/cm^3` string and priority rank is an integer. Training normalizes rank as `1-rank/10` and density as `(density-2.3)/2.8`. The output head emits 14 channels without a semantic output activation; its normalized reading is grounded in that training loss. The example inverses density then min-max rescales display values per object, which is not a shared scoring range.\n\nA metric-ready GT renderer is not established: the public GT script uses a stale `meshname` in the part loop and passes a `MeshExtractResult` to a helper that indexes `gt[0:3]`. There is also no official generated-mesh-to-GT-part correspondence, paired numeric maps/masks, fixed map value range, or scorer aggregation. Those are fail-closed prerequisites.\n\n`camera_manifest.json` is a deterministic **candidate** based on the source Hammersley helper (`30`, `r=2`, `FOV=40`, `512`), stored for reproducibility only and not used for a score. `synthetic_validation.json` validates the proposed raw-unit intersection-map primitive and its rejection rules. Description PSNR and NAP COV/MMD remain blocked.\n'''
    (OUT / 'README.md').write_text(readme)
    print(json.dumps({'status': 'blocked', 'artifact_complete_samples': len(items),
                      'map_rows_blocked': len(rows), 'camera_manifest_sha256': camera_hash,
                      'output': str(OUT)}, indent=2))


if __name__ == '__main__':
    main()
