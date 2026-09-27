"""Create a separate patched example tree; preserve the pinned upstream checkout."""
from pathlib import Path
import ast
import difflib
import hashlib
import json
import shutil

ROOT = Path('/home/minsujo/Desktop/SH/PHYSx')
TASK = ROOT / 'logs/official-example-20260921'
ORIGINAL = ROOT / 'sources/physx-4f54e750a309'
WORK = ROOT / 'sources/physx-example-work-4f54e750a309'

def replace_once(text, old, new):
    assert text.count(old) == 1, f'Expected one upstream match: {old[:80]}'
    return text.replace(old, new)

def main():
    if WORK.exists():
        previous = json.loads((TASK / 'example-source-manifest.json').read_text())
        for record in previous['files']:
            assert hashlib.sha256((WORK / record['file']).read_bytes()).hexdigest() == record['patched_sha256'], 'Unreviewed work-tree modification'
        backup = TASK / ('official-example.' + previous['patch_sha256'] + '.patch')
        if not backup.exists():
            shutil.copyfile(TASK / 'official-example.patch', backup)
    else:
        shutil.copytree(ORIGINAL, WORK, ignore=shutil.ignore_patterns('.git', 'pretrain', '__pycache__'))
        (WORK / 'pretrain').symlink_to(ORIGINAL / 'pretrain', target_is_directory=True)
    changes = []
    name = 'example.py'
    old = (ORIGINAL / name).read_text()
    new = replace_once(old, 'clip.load("ViT-L/14", jit=False)',
                       'clip.load("ViT-L/14", jit=False, download_root=os.environ["PHYSX_CLIP_DOWNLOAD_ROOT"])')
    new = replace_once(new, "phy_property[:,16:,None,None]", "phy_property[:,:16,None,None]")
    new = replace_once(new, 'phy=phy.squeeze()', '''phy=phy.squeeze()
# Preserve model output before unit conversion, normalization, or group rounding.
torch.save({'vertices': outputs['mesh'][0].vertices.detach().cpu(),
            'faces': outputs['mesh'][0].faces.detach().cpu(),
            'mesh_properties': outputs['mesh'][0].phy_property.detach().cpu(),
            'physical_before_unit_conversion': phy.detach().cpu(),
            'language': lang.detach().cpu()},
           os.path.join(savepath, 'raw-model-heads.pt'))
if not bool(torch.isfinite(phy).all()):
    raise RuntimeError('Nonfinite physical model output; raw-model-heads.pt preserved')''')
    new = replace_once(new, 'phy[...,5:-1][kinematic_map[(group_ind-1)*2]]',
                       'phy[...,5:-1][kinematic_map[:,(group_ind-1)*2].bool()]')
    new = replace_once(new, 'phy[...,-1][kinematic_map[(group_ind-1)*2]]',
                       'phy[...,-1][kinematic_map[:,(group_ind-1)*2].bool()]')
    new = replace_once(new, 'num_group=round(float(phy[...,3].max()))+1', '''num_group=round(float(phy[...,3].max()))+1

# Reproduction diagnostics: validate without altering predictions or thresholds.
for _name, _tensor in {
    'mesh_vertices': outputs['mesh'][0].vertices,
    'mesh_properties': outputs['mesh'][0].phy_property,
    'language': lang, 'physical': phy, 'score': score,
    'material': material, 'affordance': affordance,
}.items():
    if not bool(torch.isfinite(_tensor).all()):
        raise RuntimeError('Nonfinite official-example output: ' + _name)
if outputs['mesh'][0].vertices.numel() == 0 or outputs['mesh'][0].faces.numel() == 0:
    raise RuntimeError('Official example generated an empty mesh')
import json as _json
with open(os.path.join(savepath, 'prediction-diagnostics.json'), 'w') as _file:
    _json.dump({'seed': 1, 'question': args.question, 'question_type': args.question_type,
                'num_group': num_group,
                'vertices': int(outputs['mesh'][0].vertices.shape[0]),
                'faces': int(outputs['mesh'][0].faces.shape[0]),
                'finite_geometry_properties_and_heatmaps': True,
                'language_channel_slice': 'first 16 of 32; matches training renderer'}, _file, indent=2)
print('REPRO_PREDICTION_FINITE num_group=', num_group, flush=True)
torch.save({'vertices': outputs['mesh'][0].vertices.detach().cpu(),
            'faces': outputs['mesh'][0].faces.detach().cpu(),
            'physical': phy.detach().cpu(), 'language': lang.detach().cpu(),
            'score': score.detach().cpu(), 'num_group': num_group},
           os.path.join(savepath, 'raw-prediction.pt'))''')
    changes.append((name, old, new))
    name = 'trellis/pipelines/trellis_image_to_3d.py'
    old = (ORIGINAL / name).read_text()
    new = replace_once(old, 'from typing import *\n', 'from typing import *\nimport os\n')
    new = replace_once(new, "torch.hub.load('facebookresearch/dinov2', name, pretrained=True)",
                       "torch.hub.load(os.path.join(os.environ['PHYSX_ROOT'], 'sources/dinov2-9c7e3245797c'), name, source='local', pretrained=True)")
    changes.append((name, old, new))
    patches = []
    manifest = []
    for name, old, new in changes:
        ast.parse(new, filename=name)
        (WORK / name).write_text(new)
        patches.extend(difflib.unified_diff(old.splitlines(keepends=True), new.splitlines(keepends=True), fromfile='a/' + name, tofile='b/' + name))
        manifest.append({'file': name, 'original_sha256': hashlib.sha256(old.encode()).hexdigest(),
                         'patched_sha256': hashlib.sha256(new.encode()).hexdigest()})
    patch = TASK / 'official-example.patch'
    patch.write_text(''.join(patches))
    (TASK / 'example-source-manifest.json').write_text(json.dumps({
        'original': str(ORIGINAL), 'work': str(WORK),
        'upstream_commit': '4f54e750a309fe9cd9f20816916ecc0e8a9ae594',
        'patch': str(patch), 'patch_sha256': hashlib.sha256(patch.read_bytes()).hexdigest(),
        'files': manifest,
        'conditions_preserved': 'table input, seed1, sampler25steps/cfg5, render30frames, mesh simplification.95, texture1024, official texture optimizer2500steps',
        'scientific_limit': 'Language-slice implementation correction follows training code; patched output is not an unchanged-upstream baseline. Parent-group logic remains unmodified and unvalidated.',
    }, indent=2) + '\n')
    print(json.dumps({'work': str(WORK), 'patch': str(patch), 'syntax_checked_files': len(changes)}))

if __name__ == '__main__':
    main()
