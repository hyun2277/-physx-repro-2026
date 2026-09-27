"""Read-only CPU checks; does not import the model, install, or run ZIP commands."""
from pathlib import Path
import ast
import hashlib
import json
import os
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parent
REPO = Path(r'D:\physX_dev\repos\PhysX-3D')
digest = lambda b: hashlib.sha256(b).hexdigest()
result = {'scope': 'CPU configuration check and input identity only; no GPU validation'}
zpath = ROOT / '김승민' / '04_PhysX-3D-20260920T161244Z-1-001.zip'
with zipfile.ZipFile(zpath) as z:
    result['zip'] = {'sha256': digest(zpath.read_bytes()), 'members': [
        {'name': n, 'bytes': len(z.read(n)), 'sha256': digest(z.read(n))}
        for n in z.namelist() if not n.endswith('/')]}
result['scripts'] = {p.name: digest(p.read_bytes()) for p in sorted((ROOT/'PhysX-3D_설치스크립트').glob('*.sh'))}
result['official_commit'] = subprocess.check_output(['git','-C',str(REPO),'rev-parse','HEAD'],text=True).strip()
result['official_status'] = subprocess.check_output(['git','-C',str(REPO),'status','--porcelain'],text=True)
# Execute only the parsed assignments, config function and its call, excluding imports of model modules.
old = {k: os.environ.get(k) for k in ('ATTN_BACKEND','SPARSE_ATTN_BACKEND')}
try:
    os.environ['ATTN_BACKEND'] = 'sdpa'
    os.environ.pop('SPARSE_ATTN_BACKEND', None)
    backends = {}
    for name in ('attention','sparse'):
        p = REPO/'trellis'/'modules'/name/'__init__.py'
        tree = ast.parse(p.read_text(encoding='utf-8'))
        nodes = []
        for node in tree.body:
            nodes.append(node)
            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name) and node.value.func.id == '__from_env':
                break
        ns = {}
        exec(compile(ast.Module(body=nodes,type_ignores=[]),str(p),'exec'),ns)
        backends[name] = ns['BACKEND' if name == 'attention' else 'ATTN']
    assert backends == {'attention':'sdpa','sparse':'flash_attn'}, backends
    result['sdpa_config_check'] = backends
finally:
    for k,v in old.items():
        if v is None: os.environ.pop(k,None)
        else: os.environ[k] = v
import numpy as np
a = np.load(REPO/'val_test_list.npy', allow_pickle=False)
result['val_test_list'] = {'shape':list(a.shape),'dtype':str(a.dtype),'unique':len(np.unique(a))}
result['val_test_list'].update(validation_unique=len(np.unique(a[:1000])), test_unique=len(np.unique(a[1000:])), shared_ids=len(set(a[:1000]) & set(a[1000:])))
(ROOT/'PhysX-3D_통합검증_증거.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(result,ensure_ascii=False,indent=2))
