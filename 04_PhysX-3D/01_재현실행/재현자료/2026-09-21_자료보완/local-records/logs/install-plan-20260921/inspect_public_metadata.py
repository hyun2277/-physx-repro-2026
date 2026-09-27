"""Read public package/source metadata only; never install or build anything."""
import concurrent.futures
import hashlib
import json
from pathlib import Path
import urllib.request

ROOT = Path('/home/minsujo/Desktop/SH/PHYSx/logs/install-plan-20260921')
PINS = {
    'numpy': '1.26.4', 'scipy': '1.15.3', 'pillow': '11.2.1',
    'imageio': '2.37.0', 'imageio-ffmpeg': '0.6.0', 'tqdm': '4.67.1',
    'easydict': '1.13', 'opencv-python-headless': '4.11.0.86',
    'ninja': '1.11.1.4', 'rembg': '2.0.65', 'onnxruntime': '1.22.0',
    'trimesh': '4.6.8', 'open3d': '0.19.0', 'xatlas': '0.0.10',
    'pyvista': '0.45.2', 'pymeshfix': '0.17.0', 'igraph': '0.11.8',
    'transformers': '4.51.3', 'huggingface-hub': '0.34.4',
    'tokenizers': '0.21.1', 'safetensors': '0.5.3', 'einops': '0.8.1',
    'ftfy': '6.3.1', 'regex': '2024.11.6', 'ipdb': '0.13.13',
    'flash-attn': '2.8.3', 'spconv-cu126': '2.3.8',
    'setuptools': '75.8.0', 'wheel': '0.45.1', 'packaging': '24.2',
    'cmake': '3.31.6', 'build': '1.2.2.post1',
    'moderngl': '5.12.0', 'plyfile': '1.1.2', 'glcontext': '3.0.0',
}

def inspect_pin(item):
    name, version = item
    url = f'https://pypi.org/pypi/{name}/{version}/json'
    try:
        with urllib.request.urlopen(url, timeout=25) as response:
            data = json.load(response)
        info = data['info']
        return name, {
            'version': info['version'], 'source': url,
            'requires_python': info.get('requires_python'),
            'requires_dist': info.get('requires_dist'),
            'files': [{key: obj.get(key) for key in
                       ('filename', 'packagetype', 'requires_python', 'digests', 'size', 'yanked')}
                      for obj in data.get('urls', [])],
        }
    except Exception as error:
        return name, {'version': version, 'source': url,
                      'error_type': type(error).__name__, 'error': str(error)}

with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
    results = dict(pool.map(inspect_pin, PINS.items()))
output = ROOT / 'pypi-candidate-metadata.json'
output.write_text(json.dumps(results, indent=2, ensure_ascii=False) + '\n')
for name, value in results.items():
    print(name, value['version'], value.get('error', 'metadata OK'))
print('Saved', output)

source_url = 'https://raw.githubusercontent.com/ziangcao0312/PhysX-3D/4f54e750a309fe9cd9f20816916ecc0e8a9ae594/setup.sh'
try:
    with urllib.request.urlopen(source_url, timeout=25) as response:
        source = response.read()
    (ROOT / 'upstream-setup.review.txt').write_bytes(source)
    print('Official setup source saved as review text; SHA256', hashlib.sha256(source).hexdigest())
except Exception as error:
    print('Official source fetch:', type(error).__name__, str(error))
