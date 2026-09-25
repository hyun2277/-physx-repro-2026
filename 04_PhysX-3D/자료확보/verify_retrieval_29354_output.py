#!/usr/bin/env python3
"""CPU-only verification of one existing PhysX-3D retrieval output."""
from pathlib import Path
import hashlib
import sys
import numpy as np
from PIL import Image
import trimesh

def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def parse_obj(path: Path):
    vertices, faces, uvs = [], [], []
    for line in path.read_text(errors="replace").splitlines():
        if line.startswith("v "):
            vertices.append([float(x) for x in line.split()[1:4]])
        elif line.startswith("vt "):
            uvs.append([float(x) for x in line.split()[1:3]])
        elif line.startswith("f "):
            faces.append([int(x.split("/")[0]) for x in line.split()[1:]])
    return np.asarray(vertices), faces, np.asarray(uvs)

def main(stage: Path, source_texture: Path) -> None:
    root = stage / "phy_dataset" / "29354"
    inp, out = root / "model.obj", root / "model_tex.obj"
    if not out.is_file():
        raise SystemExit(f"missing {out}")
    vi, fi, _ = parse_obj(inp)
    vo, fo, uv = parse_obj(out)
    if vi.shape != vo.shape or not np.allclose(vi, vo, rtol=0, atol=1e-6):
        raise SystemExit("vertex geometry changed")
    if fi != fo:
        raise SystemExit("face topology changed")
    if uv.size == 0 or not np.isfinite(uv).all():
        raise SystemExit("UV missing or non-finite")
    a = trimesh.load(inp, force="mesh")
    b = trimesh.load(out, force="mesh")
    if a.vertices.shape != b.vertices.shape or a.faces.shape != b.faces.shape:
        raise SystemExit("reloaded mesh shape changed")
    if not np.allclose(a.vertices, b.vertices, rtol=0, atol=1e-6) or not np.array_equal(a.faces, b.faces):
        raise SystemExit("reloaded mesh differs")
    refs = [x.split(maxsplit=1)[1].strip() for x in out.read_text(errors="replace").splitlines() if x.startswith("mtllib ")]
    if len(refs) != 1:
        raise SystemExit("expected one mtllib")
    mtl = (out.parent / refs[0]).resolve()
    if not mtl.is_file():
        raise SystemExit(f"missing referenced mtl {mtl}")
    texrefs = [x.split(maxsplit=1)[1].strip() for x in mtl.read_text(errors="replace").splitlines() if x.startswith("map_Kd ")]
    if not texrefs:
        raise SystemExit("no map_Kd reference")
    src = np.asarray(Image.open(source_texture).convert("RGB"))
    source_colors = {tuple(x) for x in src.reshape(-1, 3)}
    for ref in texrefs:
        tex = (mtl.parent / ref).resolve()
        if not tex.is_file():
            raise SystemExit(f"missing referenced texture {tex}")
        with Image.open(tex) as im:
            im.load()
            arr = np.asarray(im)
            rgb = arr[:, :, :3] if arr.ndim == 3 and arr.shape[2] >= 3 else arr
            mask = arr[:, :, 3] > 0 if arr.ndim == 3 and arr.shape[2] >= 4 else np.ones(rgb.shape[:2], bool)
            membership = sum(tuple(x) in source_colors for x in rgb[mask]) / max(1, int(mask.sum()))
            print(f"texture={tex} format={im.format} size={im.size} sha256={sha(tex)}")
            print(f"texture_source_color_membership={membership:.6f} source_shape={src.shape} output_shape={rgb.shape}")
            if membership < 0.99:
                raise SystemExit("texture content does not match ShapeNet source color set")
    print(f"model_tex={out} size={out.stat().st_size} sha256={sha(out)}")
    print(f"mtl={mtl} size={mtl.stat().st_size} sha256={sha(mtl)}")
    print(f"vertices={len(vo)} faces={len(fo)} uvs={len(uv)} uv_finite=True")
    print("mesh_reload_and_shape_preservation=PASS")
    print("texture_source_used=PASS")
    print("texture_transform=atlas_or_reencode (not a byte-identical source image)")
    print("gray_fallback=NOT_USED")

if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: verify_retrieval_29354_output.py STAGE SOURCE_TEXTURE")
    main(Path(sys.argv[1]), Path(sys.argv[2]))
