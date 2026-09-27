"""Regenerate review patches from a pinned Git object; never modify upstream checkout.

Uses an isolated temporary Git repository. No model imports, installs or network.
"""
import ast
import hashlib
import itertools
import json
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parent
SOURCE = Path('D:/physX_dev/repos/PhysX-3D')
REF = '4f54e750a309fe9cd9f20816916ecc0e8a9ae594'
FILES = ['example.py', 'example_render_gt_foreval.py']
PATCHES = [
    '01_example_py_kinematic_map_fix.patch',
    '02_example_render_gt_foreval_py_des_index_fix.patch',
    '03_example_render_gt_foreval_py_meshname_fix_설계근거.patch',
]


def git(cwd, *args):
    return subprocess.run(['git', '-C', str(cwd), *args], check=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout


def replace_once(text, old, new):
    assert text.count(old) == 1, f'Expected unique source fragment: {old!r}'
    return text.replace(old, new, 1)


def transform(which, source):
    result = dict(source)
    if which == 0:
        result[FILES[0]] = replace_once(result[FILES[0]],
            '        kinematic_parameters.append(phy[...,5:-1][kinematic_map[(group_ind-1)*2]].mean(0))\n'
            '        kinematic_type.append(phy[...,-1][kinematic_map[(group_ind-1)*2]].mean(0))',
            '        # Select group members, not repeated point indices 0 and 1.\n'
            '        # Parent-group inference and empty groups still need validation.\n'
            '        _group_mask = kinematic_map[:, (group_ind-1)*2].bool()\n'
            '        kinematic_parameters.append(phy[...,5:-1][_group_mask].mean(0))\n'
            '        kinematic_type.append(phy[...,-1][_group_mask].mean(0))')
    elif which == 1:
        text = result[FILES[1]]
        text = replace_once(text,
            "        description_ind=np.random.randint(len(jsondata['parts']))\n        \n"
            "        np.save(os.path.join(savepath,'des_index.npy'),jsondata['parts'][part]['Basic_description'])\n",
            '')
        text = replace_once(text, "    for part in range(len(jsondata['parts'])):",
            '    # Choose and save one description target per object.\n'
            '    # Seed and prediction/GT question alignment are separate requirements.\n'
            "    description_ind=np.random.randint(len(jsondata['parts']))\n"
            "    np.save(os.path.join(savepath,'des_index.npy'),jsondata['parts'][description_ind]['Basic_description'])\n\n"
            "    for part in range(len(jsondata['parts'])):")
        result[FILES[1]] = text
    else:
        text = replace_once(result[FILES[1]], '    allrenobj=trimesh.Trimesh([])',
            '    # PROVISIONAL: confirm numeric file order matches JSON part order.\n'
            "    objlist = sorted(os.listdir(os.path.join(meshpath,name,'objs')), key=lambda x: int(x.split('.')[0]))\n"
            "    assert len(objlist) == len(jsondata['parts']), (\n"
            '        f"{name}: mesh/part count mismatch; validate dataset mapping")\n\n'
            '    allrenobj=trimesh.Trimesh([])')
        text = replace_once(text,
            "\n        eachpart1=trimesh.load(os.path.join(meshpath,name,'objs',str(meshname)+'.obj'))",
            "\n        eachpart1=trimesh.load(os.path.join(meshpath,name,'objs',objlist[part]))")
        result[FILES[1]] = text
    return result


source_status = git(SOURCE, 'status', '--porcelain')
source = {name: git(SOURCE, 'show', f'{REF}:{name}').decode('utf-8') for name in FILES}
report = {'base_commit': REF, 'syntax': [], 'individual_apply': [], 'orders': []}
scratch = Path('D:/physX_dev/patch_checks')
scratch.mkdir(parents=True, exist_ok=True)
with tempfile.TemporaryDirectory(prefix='physx-patch-check-', dir=scratch) as tmp:
    work = Path(tmp)
    assert work.resolve().parent == scratch.resolve()
    git(work, 'init', '-q')
    git(work, 'config', 'core.autocrlf', 'false')
    git(work, 'config', 'core.safecrlf', 'false')

    def write_files(content):
        for name, text in content.items():
            (work / name).write_bytes(text.encode('utf-8'))

    write_files(source)
    git(work, 'add', '--', *FILES)
    for i, patch in enumerate(PATCHES):
        modified = transform(i, source)
        for name, text in modified.items():
            ast.parse(text, filename=name)
        write_files(modified)
        # Minimal unchanged context keeps the two GT edits composable.
        diff = git(work, 'diff', '--no-ext-diff', '--no-color', '--unified=1', '--', *FILES)
        assert diff.startswith(b'diff --git ')
        (ROOT / patch).write_bytes(diff)
        write_files(source)
        git(work, 'apply', '--check', str(ROOT / patch))
        git(work, 'apply', str(ROOT / patch))
        for name in FILES:
            actual = (work / name).read_bytes().decode('utf-8')
            assert actual == modified[name]
            ast.parse(actual, filename=name)
        report['individual_apply'].append(patch)
        report['syntax'].append(patch)

    for order in itertools.permutations(range(3)):
        write_files(source)
        expected = dict(source)
        for i in order:
            git(work, 'apply', '--check', str(ROOT / PATCHES[i]))
            git(work, 'apply', str(ROOT / PATCHES[i]))
            expected = transform(i, expected)
        for name in FILES:
            actual = (work / name).read_bytes().decode('utf-8')
            assert actual == expected[name]
            ast.parse(actual, filename=name)
        report['orders'].append([i + 1 for i in order])

assert git(SOURCE, 'status', '--porcelain') == source_status
report['source_checkout_unchanged'] = True
report['patch_sha256'] = {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in PATCHES}
report['limits'] = 'Patch application and Python syntax only; no GPU/model/data validation. Patch 03 remains provisional; parent-group and empty-group issues remain.'
(ROOT / 'verification_result.json').write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
print(json.dumps(report, indent=2, ensure_ascii=False))
