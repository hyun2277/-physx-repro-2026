"""Deterministic CPU layout of saved pixels; never imports a model or calls CUDA."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path('/home/minsujo/Desktop/SH/PHYSx')
BASE = ROOT / 'logs/official-example-comparison-20260921'
INPUT = ROOT / 'sources/physx-4f54e750a309/example/table.png'
VIDEO = ROOT / 'outputs/official-example/table-20260921T122033Z-60b5940050/pretrain/diffusion/rgb.mp4'
assert os.environ.get('PHYSX_WORKSPACE_ISOLATED') == '1'
assert os.environ.get('CUDA_VISIBLE_DEVICES') == ''
sys.path.insert(0, str(ROOT / 'envs/physxgen/lib/python3.10/site-packages'))
from PIL import Image, ImageDraw, ImageFont
import imageio_ffmpeg

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', choices=('candidates','comparison'), required=True)
    parser.add_argument('--frame', type=int)
    args = parser.parse_args()
    assert sha(INPUT) == '67ce4c07693c8814dbdb068c7184b3b6341dc8fd7a595cdaef314d0fb1c2b388'
    assert sha(VIDEO) == '1a10165a37137f848c6e7f8a0394d487cd078aa32e9aeca2039f6bc1c53017d3'
    reader = imageio_ffmpeg.read_frames(str(VIDEO), pix_fmt='rgb24', input_params=['-hwaccel','none','-protocol_whitelist','file,pipe'])
    meta = next(reader)
    frames = [Image.frombytes('RGB', meta['size'], b) for b in reader]
    assert len(frames) == 30 and meta['size'] == (512,512)
    source = Image.open(INPUT).convert('RGBA')
    bbox = source.getchannel('A').getbbox()
    cx,cy = (bbox[0]+bbox[2])//2,(bbox[1]+bbox[3])//2
    crop = (cx-256,cy-256,cx+256,cy+256)
    assert crop[0] <= bbox[0] and crop[1] <= bbox[1] and crop[2] >= bbox[2] and crop[3] >= bbox[3]
    original = Image.alpha_composite(Image.new('RGBA',(512,512),(0,0,0,255)),source.crop(crop)).convert('RGB')
    fontpath = '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc'
    font = ImageFont.truetype(fontpath,22,index=1)
    title = ImageFont.truetype(fontpath,29,index=1)
    if args.mode == 'candidates':
        out = BASE / 'candidate-frames.png'
        canvas = Image.new('RGB',(1536,1084),'white')
        draw = ImageDraw.Draw(canvas)
        for i, n in enumerate((0,1,13,14,28,29)):
            x,y = (i%3)*512,(i//3)*542
            draw.text((x+8,y+2),'frame '+str(n),font=font,fill='black')
            canvas.paste(frames[n],(x,y+30))
        print(json.dumps({'alpha_bbox':bbox,'input_crop':crop,'candidate_frames':[0,1,13,14,28,29]}))
    else:
        assert args.frame is not None and 0 <= args.frame < 30
        out = ROOT / ('outputs/comparisons/table-input-vs-generated-frame%02d-20260921.png' % args.frame)
        canvas = Image.new('RGB',(1088,866),'#f5f5f5')
        draw = ImageDraw.Draw(canvas)
        draw.text((24,14),'기존 입력과 저장된 생성 결과 비교',font=title,fill='#111111')
        draw.text((24,57),'시점 정확히 일치하지 않음 · 카메라/배율 정합 미수행',font=font,fill='#a33a08')
        draw.text((24,100),'입력: table.png',font=font,fill='#111111')
        draw.text((552,100),f'생성: rgb.mp4 / frame {args.frame} (0부터)',font=font,fill='#111111')
        canvas.paste(original,(24,138))
        canvas.paste(frames[args.frame],(552,138))
        lines = [
            '관찰: 입력은 가느다란 중앙 틈, 선택 프레임은 넓은 타원형 구멍으로 보입니다.',
            '시점 차이는 구멍의 보이는 폭·형태에 영향을 줄 수 있습니다.',
            '이 비교만으로 형상 차이의 원인이나 시점의 기여도를 확정하지 않습니다.',
            '픽셀 1:1 유지. 입력의 완전 투명 여백만 제외하고 검은 배경에 표시했습니다.',
            '생성 프레임은 전체 그대로. 물체의 회전·크기 변경·왜곡·리터칭은 없습니다.'
        ]
        for i,line in enumerate(lines):
            draw.text((24,670+34*i),line,font=font,fill='#222222')
    out.parent.mkdir(parents=True,exist_ok=True)
    assert not out.exists(), 'Do not overwrite existing comparisons'
    canvas.save(out)
    record = {'mode':args.mode,'input':{'path':str(INPUT),'sha256':sha(INPUT)},
              'video':{'path':str(VIDEO),'sha256':sha(VIDEO)},'frame_zero_based':args.frame,
              'frame_time_seconds':None if args.frame is None else args.frame/meta['fps'],
              'input_nontransparent_bbox':bbox,'input_crop':crop,
              'input_foreground_clipped':False,'object_pixel_scaling':1,'rotation_or_warp':False,
              'frame_rgb_sha256':None if args.frame is None else hashlib.sha256(frames[args.frame].tobytes()).hexdigest(),
              'output':{'path':str(out),'bytes':out.stat().st_size,'sha256':sha(out)},
              'gpu_or_model_used':False,'timestamp':datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'versions':{'pillow':Image.__version__,'imageio_ffmpeg':imageio_ffmpeg.__version__}}
    record_path = BASE / (args.mode+'-record.json')
    with record_path.open('x') as f:
        json.dump(record,f,ensure_ascii=False,indent=2);f.write('\n')
    print(json.dumps(record,ensure_ascii=False),flush=True)

if __name__ == '__main__':
    main()
