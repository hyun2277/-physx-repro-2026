"""Pure async PNG completion checks used after Kit renderer capture requests."""
import asyncio
import hashlib
import time
from pathlib import Path
from PIL import Image


async def wait_for_stable_png(path, next_update, timeout_s=15.0, stable_observations=2):
    path=Path(path);deadline=time.monotonic()+timeout_s;stable=0;last_size=None;last_error=None
    while time.monotonic()<deadline:
        await next_update()
        if not path.is_file():continue
        size=path.stat().st_size
        stable=stable+1 if size>0 and size==last_size else 0;last_size=size
        if stable<stable_observations:continue
        try:
            if path.read_bytes()[:8]!=b"\x89PNG\r\n\x1a\n":raise ValueError("invalid PNG signature")
            with Image.open(path) as image:image.verify()
            with Image.open(path) as image:image.load();width,height=image.size
            return {"status":"CAPTURE_OK","path":str(path.resolve()),"bytes":size,"sha256":hashlib.sha256(path.read_bytes()).hexdigest(),"width":width,"height":height,"stable_observations":stable+1}
        except BaseException as error:last_error=repr(error)
    return {"status":"CAPTURE_FAILED","path":str(path.resolve()),"reason":"FILE_TIMEOUT_ZERO_UNSTABLE_OR_UNDECODABLE","last_observed_size":last_size,"last_decode_error":last_error}
