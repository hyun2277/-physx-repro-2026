import asyncio
import tempfile
from pathlib import Path
from PIL import Image
from capture_file_stability import wait_for_stable_png


def png_bytes(path):
    Image.new("RGB",(8,6),(20,40,60)).save(path)
    return path.read_bytes()


async def scenario(kind):
    with tempfile.TemporaryDirectory() as directory:
        path=Path(directory)/"capture.png";ticks=0;valid=png_bytes(Path(directory)/"valid.png")
        async def update():
            nonlocal ticks;ticks+=1
            if kind=="zero" and ticks==1:path.write_bytes(b"")
            if kind=="late" and ticks==4:path.write_bytes(valid)
            if kind=="changing":path.write_bytes(b"x"*ticks)
            if kind=="invalid" and ticks==2:path.write_bytes(b"not-a-png")
            if kind=="valid" and ticks==1:path.write_bytes(valid)
            await asyncio.sleep(0)
        result=await wait_for_stable_png(path,update,timeout_s=0.02)
        return result


def main():
    results={kind:asyncio.run(scenario(kind)) for kind in ("missing","zero","late","changing","invalid","valid")}
    assert results["missing"]["status"]=="CAPTURE_FAILED"
    assert results["zero"]["status"]=="CAPTURE_FAILED"
    assert results["late"]["status"]=="CAPTURE_OK"
    assert results["changing"]["status"]=="CAPTURE_FAILED"
    assert results["invalid"]["status"]=="CAPTURE_FAILED"
    assert results["valid"]["status"]=="CAPTURE_OK"
    # A failed first capture cannot prevent a later successful capture.
    assert [results["missing"]["status"],results["valid"]["status"]]==["CAPTURE_FAILED","CAPTURE_OK"]
    print("CAPTURE_FILE_STABILITY_TEST_PASS",results)


if __name__=="__main__":main()
