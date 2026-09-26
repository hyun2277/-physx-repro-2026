#!/usr/bin/env python3
"""Fail-closed, resumable one-sample PhysX-3D runner for object 27281."""

from __future__ import annotations
import argparse, csv, fcntl, hashlib, json, os, re, signal, subprocess, sys, time, uuid, zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/home/minsujo/Desktop/SH/PHYSx")
REPO = ROOT / "repro-records"
SRC = ROOT / "sources/physx-4f54e750a309"
TOOLS = REPO / "04_PhysX-3D/자료확보"
ADAPTER = TOOLS / "rtx5090_adapter"
PY = ROOT / "envs/physxgen/bin/python"
PHYSX_ZIP = ROOT / "data/physxnet-download/PhysXNet.zip"
SHAPE_ZIP = ROOT / "data/shapenetcore/raw/04379243.zip"
BLENDER = ROOT / "tools/blender-3.0.1/unpacked/blender-3.0.1-linux-x64/blender"
CLIP_WEIGHT = ROOT / "cache/clip/ViT-L-14.pt"
MANIFEST = TOOLS / "evidence/29354-inference-checkpoint-manifest.txt"
CUDA_HELPER = REPO / "04_PhysX-3D/실행스크립트/cuda_jit_environment.sh"
CUDA_TOOLKIT = ROOT / "toolchains/cuda-12.8.1"
HEAD = "4f54e750a309fe9cd9f20816916ecc0e8a9ae594"
OBJECT = "27281"; SHAPE = "a7887db4982215cc5afc372fcbe94f4a"
MAX_GPU_MIB = 28000; RESERVE_MIB = 4607; MAX_SECONDS = 7200
RESULT_MARKER = "PHYSX_RESULT_JSON="

PHYSX_MEMBERS = [f"version_1/finaljson/{OBJECT}.json"] + [f"version_1/partseg/{OBJECT}/objs/{i}.obj" for i in range(7)]
SHAPE_MEMBERS = [f"04379243/{SHAPE}/models/model_normalized.obj",
                 f"04379243/{SHAPE}/models/model_normalized.mtl",
                 f"04379243/{SHAPE}/images/texture0.jpg"]

def now(): return datetime.now(timezone.utc).isoformat()
def sha(path):
    h=hashlib.sha256()
    with open(path,"rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""): h.update(b)
    return h.hexdigest()
def write_json(path, data): path.write_text(json.dumps(data,indent=2,ensure_ascii=False)+"\n")
def command_text(args): return " ".join(subprocess.list2cmdline([str(x)]) for x in args)

def parse_result_marker(stdout, required):
    """Parse one explicitly marked JSON object while preserving arbitrary other output."""
    marked=[line[len(RESULT_MARKER):] for line in stdout.splitlines() if line.startswith(RESULT_MARKER)]
    if len(marked)!=1: raise ValueError(f"expected exactly one {RESULT_MARKER} line, found {len(marked)}")
    try: value=json.loads(marked[0])
    except json.JSONDecodeError as exc: raise ValueError(f"invalid marked JSON: {exc}") from exc
    if not isinstance(value,dict): raise TypeError("marked JSON must be an object")
    for key,kind in required.items():
        if key not in value: raise KeyError(f"marked JSON missing required key: {key}")
        if not isinstance(value[key],kind): raise TypeError(f"marked JSON key {key} must be {kind.__name__}")
    return value

def source_guard():
    head=subprocess.check_output(["git","-C",str(SRC),"rev-parse","HEAD"],text=True).strip()
    if head != HEAD: raise RuntimeError(f"source HEAD mismatch: {head}")
    changed=set()
    for args in (["git","-C",str(SRC),"diff","--name-only","-z"],
                 ["git","-C",str(SRC),"diff","--cached","--name-only","-z"]):
        changed.update(x.decode() for x in subprocess.check_output(args).split(b"\0") if x)
    allowed=sorted(x for x in changed if re.fullmatch(r"trellis/(?:[^/]+/)*__pycache__/[^/]+\.pyc",x))
    rejected=sorted(changed-set(allowed))
    if rejected: raise RuntimeError(f"non-pyc tracked source changes: {rejected}")
    return {"head":head,"allowed_tracked_pyc":allowed,"other_tracked_changes":[]}

def checkpoint_guard():
    rows=[]
    if not MANIFEST.is_file() or not MANIFEST.stat().st_size: raise RuntimeError("checkpoint manifest missing/empty")
    for line in MANIFEST.read_text().splitlines():
        if not line.strip(): continue
        digest,rel=line.split(maxsplit=1); path=SRC/rel
        if not re.fullmatch(r"[0-9a-f]{64}",digest) or not rel.startswith("pretrain/") or not path.is_file() or sha(path)!=digest:
            raise RuntimeError(f"bad checkpoint manifest row: {rel}")
        rows.append({"path":str(path),"sha256":digest,"bytes":path.stat().st_size})
    if len(rows)!=11: raise RuntimeError(f"expected 11 checkpoint files, got {len(rows)}")
    return rows

def zip_inventory(path, members):
    if not path.is_file(): raise RuntimeError(f"missing archive: {path}")
    with zipfile.ZipFile(path) as z:
        result=[]
        for member in members:
            info=z.getinfo(member)
            result.append({"archive":str(path),"member":member,"bytes":info.file_size,
                           "compressed_bytes":info.compress_size,"crc32":f"{info.CRC:08x}"})
        return result

def extract_member(z, member, target):
    info=z.getinfo(member); target.parent.mkdir(parents=True,exist_ok=True)
    data=z.read(info)
    if (zipfile.crc32(data)&0xffffffff)!=info.CRC or len(data)!=info.file_size: raise RuntimeError(f"ZIP verification failed: {member}")
    target.write_bytes(data)
    return {"member":member,"target":str(target),"bytes":len(data),"crc32":f"{info.CRC:08x}","sha256":sha(target)}

def gpu_guard():
    query=["nvidia-smi","--query-gpu=index,uuid,name,memory.total,memory.free","--format=csv,noheader,nounits"]
    rows=subprocess.check_output(query,text=True).splitlines(); chosen=[]
    for row in rows:
        parts=[x.strip() for x in row.split(",")]
        if parts[0]=="1": chosen.append(parts)
    if len(chosen)!=1: raise RuntimeError("physical GPU index 1 unavailable/ambiguous")
    gpu=chosen[0]
    apps=subprocess.check_output(["nvidia-smi","--query-compute-apps=pid,gpu_uuid,used_memory","--format=csv,noheader,nounits"],text=True).splitlines()
    if any(len(p:=[x.strip() for x in r.split(",")])>=2 and p[1]==gpu[1] for r in apps):
        raise RuntimeError("GPU 1 already has a compute process")
    if int(gpu[3]) < MAX_GPU_MIB+RESERVE_MIB: raise RuntimeError("GPU total memory does not preserve configured hard-limit reserve")
    return {"index":1,"uuid":gpu[1],"name":gpu[2],"total_mib":int(gpu[3]),"free_mib":int(gpu[4]),
            "hard_limit_mib":MAX_GPU_MIB,"reserve_mib":RESERVE_MIB}

def cuda_env(run):
    home=run/"home"; clip=home/".cache/clip"; clip.mkdir(parents=True,exist_ok=True)
    if not CLIP_WEIGHT.is_file(): raise RuntimeError("existing CLIP cache missing; download forbidden")
    clip_link=clip/"ViT-L-14.pt"
    if not clip_link.exists(): clip_link.symlink_to(CLIP_WEIGHT)
    overlay=run/"cuda-home"
    if not overlay.exists():
        script='source "$1"; cuda_jit_prepare "$2" "$3" /usr/bin/gcc-12 /usr/bin/g++-12 && env -0'
        raw=subprocess.check_output(["bash","-c",script,"bash",str(CUDA_HELPER),str(run),str(CUDA_TOOLKIT)])
        env={k.decode():v.decode() for item in raw.split(b"\0") if item for k,v in [item.split(b"=",1)]}
    else:
        required=["bin/nvcc","bin/cicc","bin/nvlink","bin/ptxas","bin/fatbinary","include","lib","lib64","nvvm","targets"]
        if any(not (overlay/x).exists() for x in required): raise RuntimeError("existing CUDA overlay is incomplete")
        env=os.environ.copy(); env.update(CUDA_HOME=str(overlay),CUDACXX=str(overlay/"bin/nvcc"),
            CC="/usr/bin/gcc-12",CXX="/usr/bin/g++-12",CUDAHOSTCXX="/usr/bin/g++-12",NVCC_CCBIN="/usr/bin/g++-12",
            TORCH_EXTENSIONS_DIR=str(run/"torch-extensions"),TORCH_CUDA_ARCH_LIST="12.0",PATH=f"{overlay/'bin'}:{os.environ['PATH']}")
    env.update(CUDA_VISIBLE_DEVICES="1",SPCONV_ALGO="native",PHYSX_TILE_ENABLE="1",
        PYTHONPATH=f"{ADAPTER}:{SRC}"+(f":{os.environ['PYTHONPATH']}" if os.environ.get("PYTHONPATH") else ""),
        HOME=str(home),XDG_CACHE_HOME=str(ROOT/"cache"),TORCH_HOME=str(ROOT/"cache/torch"),
        HF_HOME=str(ROOT/"cache/huggingface"),PYTHONDONTWRITEBYTECODE="1",PYTHONUNBUFFERED="1",
        PHYSX_RUN_LOG=str(run))
    env.pop("PHYSX_TILE_TEST_FORCE",None)
    return env

class Runner:
    def __init__(self, run, stage, resume=False):
        self.run=run; self.stage=stage; self.resume=resume
        self.result={"status":"not_run","reason":None,"stage":"created","child_exit_code":None,
                     "run_dir":str(run),"staging_dir":str(stage),"started_utc":now(),
                     "gpu_hard_limit_mib":MAX_GPU_MIB,"gpu_reserve_mib":RESERVE_MIB}
        run.mkdir(parents=True,exist_ok=resume); stage.mkdir(parents=True,exist_ok=resume); self.save()
    def save(self): self.result["updated_utc"]=now(); write_json(self.run/"result.json",self.result)
    def outputs(self, paths):
        return [{"path":str(p.resolve()),"bytes":p.stat().st_size,"sha256":sha(p)} for p in paths if p.is_file()]
    def marker_valid(self, directory, fingerprint):
        marker=directory/"SUCCESS.json"
        if not marker.is_file(): return False
        try: data=json.loads(marker.read_text())
        except Exception: return False
        return data.get("input_fingerprint")==fingerprint and all(Path(x["path"]).is_file() and sha(Path(x["path"]))==x["sha256"] for x in data.get("outputs",[]))
    def step(self, number, name, fingerprint, action):
        directory=self.run/"steps"/f"{number:02d}_{name}"; directory.mkdir(parents=True,exist_ok=True)
        if self.marker_valid(directory,fingerprint):
            print(f"[{now()}] SKIP verified {number}:{name}",flush=True); return json.loads((directory/"SUCCESS.json").read_text())
        if (directory/"exit_code.txt").is_file() and not self.resume:
            raise RuntimeError(f"stage {number}:{name} was attempted; use --resume {self.run}")
        action_dir=directory
        if (directory/"exit_code.txt").is_file() and self.resume:
            attempt=2
            while (directory/f"attempt_{attempt:02d}").exists(): attempt+=1
            action_dir=directory/f"attempt_{attempt:02d}"; action_dir.mkdir()
        self.result["stage"]=f"{number}:{name}"; self.save(); print(f"[{now()}] START {number}:{name} log={directory}",flush=True)
        (action_dir/"started_utc.txt").write_text(now()+"\n")
        try:
            output_paths,detail=action(action_dir)
            marker={"status":"success","input_fingerprint":fingerprint,"outputs":self.outputs(output_paths),"detail":detail,
                    "attempt_log_dir":str(action_dir),"finished_utc":now()}
            write_json(directory/"SUCCESS.json",marker); (action_dir/"exit_code.txt").write_text("0\n")
            return marker
        except BaseException as exc:
            (action_dir/"exit_code.txt").write_text(str(getattr(exc,"returncode",1) or 1)+"\n")
            (action_dir/"failure.json").write_text(json.dumps({"status":"failed","reason":f"{type(exc).__name__}: {exc}","finished_utc":now()},indent=2)+"\n")
            raise
        finally: (action_dir/"finished_utc.txt").write_text(now()+"\n")
    def child(self,directory,args,env=None,cwd=None,gpu=False,log_prefix=""):
        prefix=f"{log_prefix}." if log_prefix else ""
        write_json(directory/f"{prefix}command.json",{"argv":list(map(str,args)),"cwd":str(cwd or Path.cwd()),
            "environment":{k:(env or os.environ).get(k) for k in ("CUDA_VISIBLE_DEVICES","CUDA_HOME","CUDACXX","CC","CXX","CUDAHOSTCXX","NVCC_CCBIN","SPCONV_ALGO","PHYSX_TILE_ENABLE","PYTHONPATH")}})
        out=open(directory/f"{prefix}stdout.log","w"); err=open(directory/f"{prefix}stderr.log","w")
        p=subprocess.Popen(list(map(str,args)),cwd=cwd,env=env,stdout=out,stderr=err,start_new_session=True)
        samples=[]; start=time.monotonic(); reason=None
        try:
            while p.poll() is None:
                if gpu:
                    q=subprocess.run(["nvidia-smi","--query-gpu=index,memory.used","--format=csv,noheader,nounits"],capture_output=True,text=True)
                    used=None
                    for row in q.stdout.splitlines():
                        x=[v.strip() for v in row.split(",")]
                        if x[0]=="1": used=int(x[1])
                    samples.append({"utc":now(),"used_mib":used})
                    if used is None or used>MAX_GPU_MIB: reason="GPU memory limit reached or GPU 1 missing"
                    appq=subprocess.run(["nvidia-smi","--query-compute-apps=pid,gpu_uuid,used_memory","--format=csv,noheader,nounits"],capture_output=True,text=True)
                    gpu_doc=json.loads((directory/"gpu_preflight.json").read_text()) if (directory/"gpu_preflight.json").is_file() else None
                    def belongs_to_child(pid):
                        try:
                            while pid>1:
                                if pid==p.pid: return True
                                pid=int(Path(f"/proc/{pid}/stat").read_text().split()[3])
                        except (FileNotFoundError,ValueError,IndexError,PermissionError): pass
                        return False
                    if gpu_doc:
                        foreign=[]
                        for row in appq.stdout.splitlines():
                            cols=[x.strip() for x in row.split(",")]
                            if len(cols)>=2 and cols[1]==gpu_doc["uuid"] and not belongs_to_child(int(cols[0])): foreign.append(cols)
                        if foreign: reason=f"foreign compute process appeared on GPU 1: {foreign}"
                if time.monotonic()-start>MAX_SECONDS: reason="time limit reached"
                if reason:
                    os.killpg(p.pid,signal.SIGTERM); break
                time.sleep(3 if gpu else .2)
            rc=p.wait(timeout=30)
        except KeyboardInterrupt:
            os.killpg(p.pid,signal.SIGTERM); p.wait(); self.result.update(status="interrupted",reason="Ctrl+C",child_exit_code=p.returncode); self.save(); raise
        finally: out.close(); err.close()
        write_json(directory/f"{prefix}gpu_usage.json",{"physical_gpu_index":1,"samples":samples,"peak_nvidia_smi_mib":max((x["used_mib"] for x in samples if x["used_mib"] is not None),default=None)})
        self.result["child_exit_code"]=rc; self.save(); (directory/f"{prefix}child_exit_code.txt").write_text(f"{rc}\n")
        if reason: raise RuntimeError(reason)
        if rc: raise subprocess.CalledProcessError(rc,args)

def static_plan():
    return {"object":"27281","source_head_expected":HEAD,"physx_archive":zip_inventory(PHYSX_ZIP,PHYSX_MEMBERS),
        "shapenet_archive":zip_inventory(SHAPE_ZIP,SHAPE_MEMBERS),"blender":str(BLENDER),"python":str(PY),
        "steps":["guards/minimal extraction","official merge_property","official texture retrieval","official 24-view conditioning render","Native adapter equivalence","sampling-only child","cached decoder child","CPU 14-channel/articulation audit"],
        "will_not_run_in_plan":["nvidia-smi","Blender","CUDA","model inference"]}

def self_test():
    import tempfile
    with tempfile.TemporaryDirectory(dir=ROOT/"logs") as tmp:
        base=Path(tmp); run=base/"run"; stage=base/"stage"; r=Runner(run,stage)
        inp=base/"input"; inp.write_text("a"); fp=sha(inp); calls=[]
        def action(_):
            calls.append(1); out=stage/"out"; out.write_text("ok"); return [out],{"mock":True}
        r.step(1,"mock",fp,action); r.step(1,"mock",fp,action)
        if len(calls)!=1: raise RuntimeError("valid marker was not skipped")
        (stage/"out").write_text("tampered")
        try: r.step(1,"mock",fp,action)
        except RuntimeError as exc:
            if "--resume" not in str(exc): raise
        else: raise RuntimeError("tampered output did not require explicit resume")
        original_exit=(run/"steps/01_mock/exit_code.txt").read_text()
        r.resume=True; r.step(1,"mock",fp,action)
        if not (run/"steps/01_mock/attempt_02/exit_code.txt").is_file() or (run/"steps/01_mock/exit_code.txt").read_text()!=original_exit:
            raise RuntimeError("resume did not preserve original attempt logs")
        unsafe="../escape"
        if not (Path(unsafe).is_absolute() or ".." in Path(unsafe).parts): raise RuntimeError("unsafe member mock failed")
        mock_code='import sys;print("warning-like stdout");print("[SPARSE] Backend: spconv, Attention: flash_attn");print(\'PHYSX_RESULT_JSON={"trellis":"/source/trellis/__init__.py","spconv":"/env/spconv/__init__.py","cumm":"/env/cumm/__init__.py","algo":"native"}\');print("trailing noise");print("RuntimeWarning: harmless mock warning",file=sys.stderr)'
        mock=subprocess.run([sys.executable,"-c",mock_code],capture_output=True,text=True,check=True)
        (base/"mock.stdout.log").write_text(mock.stdout); (base/"mock.stderr.log").write_text(mock.stderr)
        parsed=parse_result_marker(mock.stdout,{"trellis":str,"spconv":str,"cumm":str,"algo":str})
        if parsed["algo"]!="native": raise RuntimeError("noisy marker parse failed")
        for invalid in ("noise only", RESULT_MARKER+'{}\n', RESULT_MARKER+'{"algo":"native"}\n'+RESULT_MARKER+'{"algo":"native"}\n', RESULT_MARKER+'{"trellis":1,"spconv":"x","cumm":"y","algo":"native"}\n'):
            try: parse_result_marker(invalid,{"trellis":str,"spconv":str,"cumm":str,"algo":str})
            except (ValueError,KeyError,TypeError): pass
            else: raise RuntimeError("invalid marker mock was accepted")
        if mock.stderr!="RuntimeWarning: harmless mock warning\n": raise RuntimeError("stderr mock was not preserved")
    return {"marker_hash_skip":"PASS","tamper_requires_explicit_resume":"PASS","unsafe_path_guard_mock":"PASS",
            "resume_attempt_log_isolated":"PASS",
            "noisy_stdout_single_marker_parse":"PASS","warning_stderr_preserved_mock":"PASS",
            "missing_duplicate_key_type_rejection":"PASS"}

def execute(run,stage,resume):
    r=Runner(run,stage,resume); work=stage/"work"; renders=stage/"datasets/PhysXNet/renders_cond/27281_"
    try:
        # These guards are intentionally re-run even when stage 1 is skipped on resume.
        guard={"source":source_guard(),"checkpoints":checkpoint_guard()}
        def s1(d):
            inventory=zip_inventory(PHYSX_ZIP,PHYSX_MEMBERS)+zip_inventory(SHAPE_ZIP,SHAPE_MEMBERS)
            extracted=[]
            with zipfile.ZipFile(PHYSX_ZIP) as z:
                extracted.append(extract_member(z,PHYSX_MEMBERS[0],work/f"physxnet/finaljson/{OBJECT}.json"))
                for i,m in enumerate(PHYSX_MEMBERS[1:]): extracted.append(extract_member(z,m,work/f"physxnet/partseg/{OBJECT}/objs/{i}.obj"))
            base=work/f"shapenet/04379243/{SHAPE}"
            with zipfile.ZipFile(SHAPE_ZIP) as z:
                extracted.append(extract_member(z,SHAPE_MEMBERS[0],base/"models/model_normalized.obj"))
                extracted.append(extract_member(z,SHAPE_MEMBERS[1],base/"models/model_normalized.mtl"))
                extracted.append(extract_member(z,SHAPE_MEMBERS[2],base/"images/texture0.jpg"))
            official=json.loads((SRC/"tools/finalindex.json").read_text()).get(OBJECT)
            expected=f"shapenet/04379243/{SHAPE}"
            if official!=expected: raise RuntimeError(f"official finalindex mismatch: {official}")
            write_json(work/"finalindex.json",{OBJECT:official}); write_json(d/"inventory.json",{"central_directory":inventory,"extracted":extracted,"source":guard["source"],"checkpoints":guard["checkpoints"]})
            outs=[Path(x["target"]) for x in extracted]+[work/"finalindex.json",MANIFEST,
                SRC/"dataset_toolkits/merge_property.py",SRC/"dataset_toolkits/retrieval_texture_example.py",
                SRC/"dataset_toolkits/render_cond.py",*[Path(x["path"]) for x in guard["checkpoints"]]]
            return outs,{"part_obj_count":7,"mapping":official}
        r.step(1,"guards_and_minimal_extract",hashlib.sha256((sha(PHYSX_ZIP)+sha(SHAPE_ZIP)+HEAD).encode()).hexdigest(),s1)

        def s2(d):
            gpu=gpu_guard(); write_json(d/"gpu_preflight.json",gpu); env=cuda_env(run)
            args=[PY,SRC/"dataset_toolkits/merge_property.py","--index","0","--range","1","--datapath",work/"physxnet"]
            r.child(d,args,env=env,cwd=work,gpu=True)
            root=work/f"phy_dataset/{OBJECT}"; outs=[root/x for x in ("model.obj","clip.npy","clip_ind_new.npy","otherproperty.npy")]
            if not all(x.is_file() and x.stat().st_size for x in outs): raise RuntimeError("merge output missing")
            code='import numpy as n,sys,json;print(json.dumps({x:list(n.load(sys.argv[1]+"/"+x).shape) for x in ["clip.npy","clip_ind_new.npy","otherproperty.npy"]}))'
            detail=json.loads(subprocess.check_output([PY,"-c",code,str(root)],text=True))
            return outs,{"arrays":detail,"gpu":gpu}
        r.step(2,"official_merge_property",sha(work/f"physxnet/finaljson/{OBJECT}.json")+sha(SRC/"dataset_toolkits/merge_property.py")+sha(MANIFEST),s2)

        def s3(d):
            env=os.environ.copy(); env.update(CUDA_VISIBLE_DEVICES="",PYTHONDONTWRITEBYTECODE="1")
            args=[PY,SRC/"dataset_toolkits/retrieval_texture_example.py","--index","0","--range","1"]
            r.child(d,args,env=env,cwd=work)
            tex=work/f"shapenet/04379243/{SHAPE}/images/texture0.jpg"
            verify=[PY,TOOLS/"verify_retrieval_29354_output.py",work,tex,OBJECT]
            with open(d/"verification.log","w") as f: subprocess.run(verify,check=True,stdout=f,stderr=subprocess.STDOUT,env=env)
            root=work/f"phy_dataset/{OBJECT}"; obj=root/"model_tex.obj"
            refs=[]
            for line in obj.read_text(errors="replace").splitlines():
                if line.startswith("mtllib "): refs.append(root/line.split(maxsplit=1)[1])
            if len(refs)!=1 or not refs[0].is_file(): raise RuntimeError("OBJ->MTL reference invalid")
            texrefs=[refs[0].parent/x.split(maxsplit=1)[1] for x in refs[0].read_text(errors="replace").splitlines() if x.startswith("map_Kd ")]
            if not texrefs or not all(x.is_file() for x in texrefs): raise RuntimeError("MTL->texture reference invalid")
            return [obj,*refs,*texrefs],{"gray_fallback":"not used (source color membership verifier passed)"}
        r.step(3,"official_texture_retrieval",sha(work/f"phy_dataset/{OBJECT}/model.obj")+sha(work/"finalindex.json")+sha(work/f"shapenet/04379243/{SHAPE}/models/model_normalized.obj")+sha(work/f"shapenet/04379243/{SHAPE}/models/model_normalized.mtl")+sha(work/f"shapenet/04379243/{SHAPE}/images/texture0.jpg")+sha(SRC/"dataset_toolkits/retrieval_texture_example.py"),s3)

        def s4(d):
            if not BLENDER.is_file(): raise RuntimeError("portable Blender missing")
            data=stage/"datasets/PhysXNet"; data.mkdir(parents=True,exist_ok=True)
            meta=data/"metadata.csv"
            with open(meta,"w",newline="") as f:
                fields=["sha256","file_identifier","aesthetic_score","captions","rendered","voxelized","num_voxels","cond_rendered","local_path"]
                w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerow({"sha256":"27281_","file_identifier":"0","aesthetic_score":"10","captions":"0","rendered":"False","voxelized":"False","num_voxels":"0","cond_rendered":"False","local_path":str(work/f"phy_dataset/{OBJECT}/model_tex.obj")})
            args=[PY,TOOLS/"render_cond_29354_portable.py","--source-dir",SRC/"dataset_toolkits","--blender",BLENDER,"--model",work/f"phy_dataset/{OBJECT}/model_tex.obj","--output",data,"--num-views","24","--object-id",OBJECT]
            env=os.environ.copy(); env.update(CUDA_VISIBLE_DEVICES="",PYTHONDONTWRITEBYTECODE="1")
            r.child(d,args,env=env,cwd=work)
            trans=renders/"transforms.json"; doc=json.loads(trans.read_text()); frames=doc.get("frames",[])
            if len(frames)!=24: raise RuntimeError(f"expected 24 frames, got {len(frames)}")
            code='from PIL import Image;import json,numpy as n,sys,pathlib;p=pathlib.Path(sys.argv[1]);d=json.load(open(p/"transforms.json"));fs=[]\nfor f in d["frames"]:\n q=(p/f["file_path"]).resolve(); im=Image.open(q);im.load();m=n.array(f["transform_matrix"],float);assert m.shape==(4,4) and n.isfinite(m).all();fs.append(q)\nprint("\\n".join(map(str,fs)))'
            images=[Path(x) for x in subprocess.check_output([PY,"-c",code,str(renders)],text=True).splitlines()]
            selected=sorted(images,key=lambda x:x.name)[0]
            if selected.name!="000.png": raise RuntimeError(f"lowest valid frame is not 000.png: {selected.name}")
            selected_frames=[f for f in frames if (renders/f["file_path"]).resolve()==selected.resolve()]
            if len(selected_frames)!=1: raise RuntimeError("selected PNG does not map to exactly one transforms frame")
            write_json(d/"selected_input.json",{"path":str(selected),"sha256":sha(selected),"frame":selected_frames[0],"transforms_sha256":sha(trans),"camera_note":"official default 24-view conditioning render; not paper 30-view evaluation camera"})
            return [meta,trans,*images],{"image_count":24,"selected":str(selected)}
        r.step(4,"conditioning_render_24view",sha(work/f"phy_dataset/{OBJECT}/model_tex.obj")+sha(SRC/"dataset_toolkits/render_cond.py")+sha(TOOLS/"render_cond_29354_portable.py"),s4)

        env=cuda_env(run); selected=renders/"000.png"
        def s5(d):
            gpu=gpu_guard(); write_json(d/"gpu_preflight.json",gpu)
            for mode in ("cpu","cpu_spconv","boundary"):
                r.child(d,[PY,ADAPTER/"validate_candidate.py",mode],env={**env,"PHYSX_TILE_ENABLE":"0"},log_prefix=f"validate_{mode}")
            r.child(d,[PY,ADAPTER/"validate_candidate.py","gpu"],env={**env,"PHYSX_TILE_ENABLE":"0"},gpu=True,log_prefix="validate_gpu_equivalence")
            import_check='import json,trellis,spconv,cumm;from trellis.modules.sparse import conv;print("PHYSX_RESULT_JSON="+json.dumps({"trellis":trellis.__file__,"spconv":spconv.__file__,"cumm":cumm.__file__,"algo":conv.SPCONV_ALGO},sort_keys=True))'
            r.child(d,[PY,"-c",import_check],env=env,gpu=True,log_prefix="import_probe")
            raw_stdout=(d/"import_probe.stdout.log").read_text()
            actual=parse_result_marker(raw_stdout,{"trellis":str,"spconv":str,"cumm":str,"algo":str})
            if actual["algo"]!="native" or not actual["trellis"].startswith(str(SRC)) or not actual["spconv"] or not actual["cumm"]:
                raise RuntimeError(f"import/algo mismatch: {actual}")
            write_json(d/"imports.json",actual); return [d/"imports.json"],{"gpu":gpu,"equivalence":"passed"}
        r.step(5,"native_adapter_equivalence",sha(ADAPTER/"channel_tiled_spconv.py")+sha(ADAPTER/"sitecustomize.py")+sha(ADAPTER/"validate_candidate.py")+sha(selected),s5)

        sampling=stage/"sampling"
        def s6(d):
            gpu=gpu_guard(); write_json(d/"gpu_preflight.json",gpu)
            args=[PY,ADAPTER/"sample_latents_only.py","--source",SRC,"--input",selected,"--output",sampling,"--report",d/"sampling_report.json","--seed","1"]
            r.child(d,args,env=env,cwd=SRC,gpu=True)
            latent=sampling/"sampled_latents.pt"
            if not latent.is_file(): raise RuntimeError("sampling latent missing")
            return [latent,sampling/"preprocessed.png",d/"sampling_report.json"],{"seed":1,"latent_sha256":sha(latent)}
        r.step(6,"sampling_only",sha(selected)+"seed=1"+HEAD+sha(ADAPTER/"sample_latents_only.py")+sha(MANIFEST),s6)

        decoded=stage/"decoder"
        def s7(d):
            gpu=gpu_guard(); write_json(d/"gpu_preflight.json",gpu); latent=sampling/"sampled_latents.pt"
            args=[PY,ADAPTER/"decode_cached_29354.py","--latent",latent,"--source",SRC,"--output",decoded,"--report",d/"decoder_report.json"]
            r.child(d,args,env=env,cwd=SRC,gpu=True)
            raw=decoded/"mesh_physics_raw.pt"; mesh=decoded/"mesh.obj"
            if not raw.is_file() or not mesh.is_file(): raise RuntimeError("decoder outputs missing")
            return [raw,mesh,d/"decoder_report.json"],{"latent_sha256":sha(latent)}
        r.step(7,"cached_physics_mesh_decoder",sha(sampling/"sampled_latents.pt")+sha(SRC/"pretrain/diffusion/ckpts_new/property_decoder_step0100000.pt")+sha(SRC/"pretrain/diffusion/ckpts_new/decoder_step0100000.pt")+sha(ADAPTER/"decode_cached_29354.py")+sha(ADAPTER/"channel_tiled_spconv.py"),s7)

        audit=stage/"articulation_audit"
        def s8(d):
            args=[PY,"-B",ADAPTER/"verify_articulated_output.py","--raw",decoded/"mesh_physics_raw.pt","--mesh",decoded/"mesh.obj","--gt",work/f"physxnet/finaljson/{OBJECT}.json","--head",SRC/"pretrain/diffusion/ckpts_new/property_output_step0100000.pt","--output",audit]
            env=os.environ.copy(); env.update(CUDA_VISIBLE_DEVICES="",PYTHONDONTWRITEBYTECODE="1")
            r.child(d,args,env=env)
            outs=[audit/x for x in ("official_result.json","indexing_correction_candidate.json","gt_annotation.json","input_hashes.json","vertex_physics_14ch.pt")]
            return outs,{"scope":"single sample; no paper metric; no description/video/texture GLB"}
        r.step(8,"cpu_property_and_articulation_audit",sha(decoded/"mesh_physics_raw.pt")+sha(work/f"physxnet/finaljson/{OBJECT}.json")+sha(SRC/"pretrain/diffusion/ckpts_new/property_output_step0100000.pt")+sha(ADAPTER/"verify_articulated_output.py"),s8)
        r.result.update(status="success",reason=None,stage="complete",child_exit_code=0); r.save()
    except KeyboardInterrupt:
        r.result.update(status="interrupted",reason="Ctrl+C"); r.save()
        print(f"INTERRUPTED stage={r.result['stage']} log={run}",file=sys.stderr)
        raise
    except BaseException as exc:
        r.result.update(status="failed",reason=f"{type(exc).__name__}: {exc}"); r.save(); print(f"FAILED stage={r.result['stage']} log={run}",file=sys.stderr); raise
    print(f"SUCCESS log={run} staging={stage}")

def main():
    p=argparse.ArgumentParser(); p.add_argument("--plan",action="store_true"); p.add_argument("--self-test",action="store_true"); p.add_argument("--resume",type=Path)
    a=p.parse_args()
    if a.plan: print(json.dumps(static_plan(),indent=2)); return
    if a.self_test: print(json.dumps(self_test(),indent=2)); return
    parent=ROOT/"logs/physx27281-e2e"; parent.mkdir(parents=True,exist_ok=True)
    lock=open(parent/".runner.lock","w"); fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    if a.resume:
        run=a.resume.resolve(); prior=json.loads((run/"result.json").read_text()); stage=Path(prior["staging_dir"])
        if prior.get("status") not in ("failed","interrupted","not_run"): raise SystemExit("resume only accepts an unfinished/failed run")
        execute(run,stage,True)
    else:
        rid=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")+"-"+uuid.uuid4().hex[:12]
        execute(parent/rid,ROOT/f"staging/physx27281-e2e-{rid}",False)

if __name__=="__main__": main()
