"""Read completed artifacts; CPU contact sheets and approximate GLB previews only.
No model import, inference, CUDA, download, or mutation of original outputs.
Run through the existing offline, GPU-hidden workspace runner (build profile).
"""
import datetime
import hashlib
import json
import os
from pathlib import Path
import sys
import uuid

ROOT = Path('/home/minsujo/Desktop/SH/PHYSx')
sys.path.insert(0, str(ROOT / 'envs/physxgen/lib/python3.10/site-packages'))
assert os.environ.get('PHYSX_WORKSPACE_ISOLATED') == '1'
assert os.environ.get('CUDA_VISIBLE_DEVICES') == ''
import numpy as np
from PIL import Image, ImageDraw
import imageio_ffmpeg
import trimesh

SOURCE = ROOT / 'outputs/official-example/table-20260921T122033Z-60b5940050/pretrain/diffusion'
REPORT = ROOT / 'logs/official-example-20260921/terminal-runs/20260921T122021Z-415cd02be5/output-validation.json'
DEST = ROOT / 'logs/official-example-review-20260921' / ('previews-' + datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8])
DEST.mkdir()
manifest = {'purpose': 'CPU inspection of completed outputs; no inference rerun', 'directory': str(DEST), 'hash_checks': [], 'videos': {}, 'previews': [], 'versions': {'numpy': np.__version__, 'trimesh': trimesh.__version__, 'imageio_ffmpeg': imageio_ffmpeg.__version__}}

def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()

def save(img, name):
    p = DEST / name
    img.save(p)
    manifest['previews'].append({'path': str(p), 'bytes': p.stat().st_size, 'sha256': digest(p)})
    print(str(p), flush=True)

for item in json.loads(REPORT.read_text())['all_output_files']:
    p = ROOT / item['path']
    actual = digest(p)
    assert actual == item['sha256'] and p.stat().st_size == item['size_bytes'], p
    manifest['hash_checks'].append({'path': item['path'], 'sha256': actual, 'bytes': p.stat().st_size, 'matches_original_validation': True})

for name in ('rgb', 'affordance', 'material', 'description'):
    reader = imageio_ffmpeg.read_frames(str(SOURCE / (name + '.mp4')), pix_fmt='rgb24', input_params=['-hwaccel', 'none', '-protocol_whitelist', 'file,pipe'])
    meta = next(reader)
    frames = [Image.frombytes('RGB', meta['size'], frame) for frame in reader]
    assert len(frames) == 30
    sheet = Image.new('RGB', (6 * 280, 5 * 236), 'white')
    draw = ImageDraw.Draw(sheet)
    for i, frame in enumerate(frames):
        thumb = frame.copy()
        thumb.thumbnail((276, 210))
        x, y = (i % 6) * 280, (i // 6) * 236
        sheet.paste(thumb, (x, y + 20))
        draw.text((x + 5, y + 3), name + ' frame ' + str(i), fill='black')
    save(sheet, name + '-all-30-frames.png')
    save(frames[0], name + '-frame00.png')
    manifest['videos'][name] = {'frames_viewable_in_sheet': list(range(30)), 'dimensions': meta['size'], 'fps': meta['fps']}

scene = trimesh.load_scene(SOURCE / 'texture.glb', process=False)
assert len(scene.geometry) == 1
node = list(scene.graph.nodes_geometry)[0]
transform, geometry_name = scene.graph[node]
mesh = scene.geometry[geometry_name]
vertices = trimesh.transform_points(mesh.vertices, transform)
faces = np.asarray(mesh.faces)
uv = np.asarray(mesh.visual.uv)
texture = mesh.visual.material.baseColorTexture.convert('RGB')
save(texture, 'glb-embedded-texture.png')
tex = np.asarray(texture)
centered = vertices - (vertices.min(0) + vertices.max(0)) / 2

def render(yaw, elevation=25, size=600):
    # Orthographic CPU rasterizer; no PBR, transparency, antialiasing or GPU.
    a, b = np.deg2rad([yaw, elevation])
    right = np.array([np.cos(a), 0., -np.sin(a)])
    toward = np.array([np.sin(a)*np.cos(b), np.sin(b), np.cos(a)*np.cos(b)])
    up = np.cross(toward, right)
    p = np.column_stack([centered @ right, centered @ up, centered @ toward])
    scale = (size * .82) / np.linalg.norm(np.ptp(centered, axis=0))
    p[:, :2] *= scale
    p[:, 0] += size/2
    p[:, 1] = size/2 - p[:, 1]
    canvas = np.full((size, size, 3), 235, dtype=np.uint8)
    depth = np.full((size, size), -np.inf)
    for tri in faces:
        q = p[tri]
        lo = np.maximum(np.floor(q[:, :2].min(0)).astype(int), 0)
        hi = np.minimum(np.ceil(q[:, :2].max(0)).astype(int), size-1)
        if (lo > hi).any():
            continue
        xx, yy = np.meshgrid(np.arange(lo[0],hi[0]+1)+.5, np.arange(lo[1],hi[1]+1)+.5)
        den = (q[1,1]-q[2,1])*(q[0,0]-q[2,0])+(q[2,0]-q[1,0])*(q[0,1]-q[2,1])
        if abs(den) < 1e-10:
            continue
        w0 = ((q[1,1]-q[2,1])*(xx-q[2,0])+(q[2,0]-q[1,0])*(yy-q[2,1]))/den
        w1 = ((q[2,1]-q[0,1])*(xx-q[2,0])+(q[0,0]-q[2,0])*(yy-q[2,1]))/den
        w2 = 1-w0-w1
        z = w0*q[0,2]+w1*q[1,2]+w2*q[2,2]
        region = np.s_[lo[1]:hi[1]+1,lo[0]:hi[0]+1]
        visible = (w0 >= 0)&(w1 >= 0)&(w2 >= 0)&(z > depth[region])
        tuv = w0[...,None]*uv[tri[0]]+w1[...,None]*uv[tri[1]]+w2[...,None]*uv[tri[2]]
        tx = np.clip(np.rint(tuv[...,0]*(tex.shape[1]-1)),0,tex.shape[1]-1).astype(int)
        ty = np.clip(np.rint((1-tuv[...,1])*(tex.shape[0]-1)),0,tex.shape[0]-1).astype(int)
        canvas[region][visible] = tex[ty,tx][visible]
        depth[region][visible] = z[visible]
    img = Image.fromarray(canvas)
    ImageDraw.Draw(img).text((12,12), 'GLB CPU preview: yaw ' + str(yaw) + ' / elevation ' + str(elevation), fill='black')
    return img

views = Image.new('RGB', (1800,600))
for i, angle in enumerate((30,150,270)):
    views.paste(render(angle), (i*600,0))
save(views, 'glb-three-views.png')
manifest['mesh'] = {'vertices': len(vertices), 'faces': len(faces), 'bounds': [vertices.min(0).tolist(), vertices.max(0).tolist()], 'preview_limit': 'Approximate orthographic CPU UV texture preview; no PBR, no interactive viewer or semantic/physical accuracy test.'}
input_img = Image.open(ROOT / 'sources/physx-4f54e750a309/example/table.png').convert('RGBA')
bg = Image.new('RGBA', input_img.size, (235,235,235,255))
save(Image.alpha_composite(bg,input_img).convert('RGB'), 'input-on-gray.png')
(DEST / 'inspection.json').write_text(json.dumps(manifest, indent=2) + '\n')
print(json.dumps({'completed': True, 'manifest': str(DEST / 'inspection.json')}), flush=True)
