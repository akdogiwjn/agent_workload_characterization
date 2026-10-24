#!/usr/bin/env python3
"""Single-attempt host lifecycle for ViMax media continuation."""
from __future__ import annotations
import argparse, hashlib, json, os, subprocess, sys, threading, time, uuid
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(REPO / "src"))
from agent_workload_characterization.collectors.resource_sampler import CgroupV1FileReader, ResourceSampler

BASE = Path(__file__).resolve().parent
PREFLIGHT = BASE.parent / "preflight-02"
PLAN = BASE.parent / "preflight-01" / "staged-planning"
IMAGE = "vimax-task-bailian:arm64-v7-capability-planning-01"
IMAGE_ID = "sha256:a97ea6076fbcd456ada0d0e1267ebf50058daa52698e0996cffaf66da1f176f3"
CRED = Path("/home/lcq/.config/agent-workload-characterization/bailian.env")
LLM_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
WORK_S, CLOSEOUT_S = 5400.0, 300.0
NET_PERIOD_S = 2.0
DOCKER = ["docker", "--host", "unix:///var/run/docker.sock"]

def sha(p: Path) -> str:
    h=hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""): h.update(b)
    return h.hexdigest()

def write(path: Path, obj):
    tmp=path.with_suffix(path.suffix+".tmp")
    tmp.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    os.replace(tmp,path)

def run(argv, timeout=30):
    try: return subprocess.run(argv,capture_output=True,text=True,timeout=timeout)
    except subprocess.TimeoutExpired as e: return subprocess.CompletedProcess(argv,124,e.stdout or "", "TIMEOUT")

def image_identity():
    r=run(DOCKER+["image","inspect",IMAGE,"--format","{{.Id}} {{.Os}} {{.Architecture}}"])
    if r.returncode: raise RuntimeError("registered Docker image could not be inspected")
    parts=r.stdout.strip().split()
    actual={"id":parts[0],"platform":f"{parts[1]}/{parts[2]}"}
    if actual != {"id":IMAGE_ID,"platform":"linux/arm64"}: raise RuntimeError("fixed image ID/platform mismatch")
    return actual

def source_hashes():
    root=REPO/"env/video/vimax/adapter-src"
    return {p.relative_to(root).as_posix():sha(p) for p in sorted(root.rglob("*")) if p.is_file() and "__pycache__" not in p.parts and p.suffix!=".pyc"}

def in_image_hashes(entry: Path):
    code="import hashlib,json,pathlib; r=pathlib.Path('/opt/vimax/src'); print(json.dumps({p.relative_to(r).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(r.rglob('*')) if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc'}))"
    r=run(DOCKER+["run","--rm","--network","none","--read-only","--tmpfs","/tmp:rw,nosuid,nodev,size=128m","--mount",f"type=bind,source={entry},target=/opt/run/generation_entry.py,readonly","-e","PYTHONPATH=/opt/vimax/src:/opt/run","--entrypoint","python3",IMAGE,"-c",code],60)
    if r.returncode: raise RuntimeError("container source identity check failed")
    return json.loads(r.stdout.strip().splitlines()[-1])

def creds_runtime_only():
    values={}
    for line in CRED.read_text(encoding="utf-8").splitlines():
        line=line.strip()
        if line.startswith("export "): line=line[7:]
        if line.startswith("#") or "=" not in line: continue
        k,_,v=line.partition("=")
        if k.strip() in {"DASHSCOPE_API_KEY","BAILIAN_WORKSPACE_ID"}: values[k.strip()]=v.strip().strip("\"'")
    if not values.get("DASHSCOPE_API_KEY") or not values.get("BAILIAN_WORKSPACE_ID"):
        raise RuntimeError("registered runtime credential variables are unavailable")
    host=values["BAILIAN_WORKSPACE_ID"]+".cn-beijing.maas.aliyuncs.com"
    return values,host

def plan_source_summary():
    manifest=json.loads((REPO/"env/video/vimax/VIMAX-PLANNING-VALIDATE-03/manifest.json").read_text())
    expected={x["path"]:x for x in manifest["files"]}
    root=PLAN
    rows=[]
    for rel in [".vimax/sessions.json",".working_dir/planning-validation-03/script2video/script.txt",".working_dir/planning-validation-03/script2video/characters.json",".working_dir/planning-validation-03/script2video/storyboard.json",".working_dir/planning-validation-03/script2video/camera_tree.json"]+[f".working_dir/planning-validation-03/script2video/shots/{i}/shot_description.json" for i in range(8)]:
        # The mounted source is the same staged plan whose source map is bound below.
        p=root/rel
        rows.append({"path":rel,"bytes":p.stat().st_size,"sha256":sha(p)})
    source_map=json.loads((REPO/"env/video/vimax/VIMAX-GENERATION-PILOT-02/preflight-01/source-map.json").read_text())
    if len(source_map.get("files",[]))!=15: raise RuntimeError("prior staged plan source map is incomplete")
    staged_root=REPO/"env/video/vimax/VIMAX-GENERATION-PILOT-02/preflight-01/staged-planning"
    for row in source_map["files"]:
        staged_path=REPO/row["staged"]
        if staged_path.stat().st_size!=row["staged_bytes"] or sha(staged_path)!=row["staged_sha256"]:
            raise RuntimeError("staged planning source differs from its immutable source map")
        source_path=REPO/row["source"]
        if source_path.stat().st_size!=row["source_manifest_bytes"] or sha(source_path)!=row["source_manifest_sha256"]:
            raise RuntimeError("accepted planning source differs from its manifest")
    return {"run_id":"vimax-planning-validate-03-20261024T014216Z-3d8d561a","identity_sha256":"7d1f3ce8d4ad081b56e4031f93a21d93f894eef1cc759ae0ab0339eda14e26a2","source_map":"../preflight-01/source-map.json","files":rows}

def preflight(out: Path):
    out.mkdir(parents=True,exist_ok=False)
    ident=image_identity()
    entry=BASE/"generation_entry.py"
    host=source_hashes(); image=in_image_hashes(entry)
    if host!=image: raise RuntimeError("fixed image adapter-src hashes do not match working source")
    src=plan_source_summary()
    # Exact branch count from accepted plan: eight cameras; seven with parents.
    cam=json.loads((PLAN/".working_dir/planning-validation-03/script2video/camera_tree.json").read_text())
    cameras=cam if isinstance(cam,list) else cam.get("camera_tree",cam.get("cameras",[]))
    if len(cameras)!=8: raise RuntimeError("accepted camera tree is not eight cameras")
    child_count=sum(1 for c in cameras if (c.get("parent_cam_idx") is not None or c.get("parent_shot_idx") is not None))
    if child_count!=7: raise RuntimeError("accepted camera tree does not require exactly seven transitions")
    # Offline preflight uses the actual production entry and capability gate.
    w=out/"workspace"; (w/"attempt").mkdir(parents=True)
    env={"PYTHONPATH":"/opt/vimax/src:/opt/run","VIMAX_BAILIAN_BUDGET_LLM_CALLS":"80","VIMAX_BAILIAN_BUDGET_LLM_ATTEMPTS":"80","VIMAX_BAILIAN_BUDGET_IMAGE_GENERATIONS":"40","VIMAX_BAILIAN_BUDGET_VIDEO_CREATES":"15","VIMAX_BAILIAN_BUDGET_TRANSITIONS":"7","VIMAX_BAILIAN_BUDGET_VIDEO_POLLS":"1800","VIMAX_BAILIAN_BUDGET_MEDIA_DOWNLOADS":"80","VIMAX_BAILIAN_BUDGET_SINGLE_REQUEST_OUTPUT_TOKENS":"8192","VIMAX_BAILIAN_BUDGET_DEADLINE_SECONDS":"5400","VIMAX_VIDEO_CAPABILITY_PROFILE":"bailian-wan26-i2v-first-frame","VIMAX_VIDEO_MODEL":"wan2.6-i2v-flash","VIMAX_IMAGE_NUM_CANDIDATES":"2"}
    argv=DOCKER+["run","--rm","--network","none","--read-only","--tmpfs","/tmp:rw,nosuid,nodev,size=256m","--mount",f"type=bind,source={w},target=/workspace","--mount",f"type=bind,source={PLAN},target=/planning,readonly","--mount",f"type=bind,source={entry},target=/opt/run/generation_entry.py,readonly","--user",f"{os.getuid()}:{os.getgid()}"]
    for k,v in env.items(): argv += ["-e",f"{k}={v}"]
    argv += [IMAGE,"python3","/opt/run/generation_entry.py","--self-check"]
    # User/group applies before image and command; reorder --user already before image.
    check=run(argv,60)
    if check.returncode: raise RuntimeError("network-none production render preflight failed")
    media_cfg={"image_model":"qwen-image-3.0","portrait_outputs":3,"portrait_image_size":"provider default, native config","shot_candidates_per_shot":2,"shot_frame_size":"1600x900","shot_frame_candidates":16,"image_create_estimate":19,"image_create_cap":40,"image_attempt_retry_cap":2,"max_image_create_sends_estimate":38,"video_model":"wan2.6-i2v-flash","shot_video_creates":8,"transition_edges":[{"from_camera":int(c.get("parent_cam_idx",c.get("parent_shot_idx"))),"to_camera":int(c.get("idx",c.get("camera_idx",-1))),"create_cap":1} for c in cameras if (c.get("parent_cam_idx") is not None or c.get("parent_shot_idx") is not None)],"transition_video_creates":7,"total_video_creates":15,"video_duration_s":5,"resolution":"720P","fps":30,"audio":False,"concat_order":"eight shots by storyboard order; transition videos seed child-camera frame continuity and are excluded from final concat","expected_final_duration_s":40,"duration_tolerance":{"segment_seconds":0.25,"final_seconds":1.0}}
    model_cfg={"llm_model":"qwen3.7-plus","llm_base_url":LLM_URL,"protocol":"OpenAI-compatible Chat Completions","internal_enable_thinking":False,"single_request_output_tokens":8192,"sdk_max_retries":0,"image_model":"qwen-image-3.0","video_model":"wan2.6-i2v-flash","video_route_region":"cn-beijing","workspace_route_host":"registered workspace host matches cn-beijing.maas.aliyuncs.com; value redacted"}
    budget={"llm_calls":80,"llm_attempts":80,"image_creates":40,"image_create_http_sends":40,"video_creates":15,"polls_per_task":120,"poll_interval_min_s":10,"poll_window_s":900,"polls_global_cap":1800,"media_downloads":80,"single_request_output_tokens":8192,"observed_total_tokens_soft":500000,"work_deadline_s":WORK_S,"closeout_reserve_s":CLOSEOUT_S,"sdk_retries":0}
    costs={"currency":"CNY","basis":"Beijing list prices: 15 video creates × 5 s × ¥0.15/s; 19 image outputs × ¥0.18/output; up to 57 image input references × ¥0.02/reference","known_media_list_price_upper_estimate":15.81,"image_input_reference_estimate_max":57,"language_vision_tokens_not_included":True,"actual_bill":"unknown","target_20_cny_is_not_hard_cap":True,"source":"https://help.aliyun.com/zh/model-studio/model-pricing"}
    res={"ok":True,"image":ident,"adapter_source_files":len(host),"adapter_hash_match":True,"generation_entry_sha256":sha(entry),"planning_source":src,"camera_count":8,"transition_count":child_count,"media_config":media_cfg,"model_config":model_cfg,"budget":budget,"cost_estimate":costs,"network":"bridge container namespace required for per-interface sampling","credentials_file_readable":os.access(CRED,os.R_OK),"api_requests_sent":0}
    if not res["credentials_file_readable"]: raise RuntimeError("registered runtime credential file not readable")
    write(out/"preflight.json",res)
    if (PREFLIGHT/"preflight-report.json").exists(): raise RuntimeError("preflight-02 report already exists; refusing overwrite")
    write(PREFLIGHT/"preflight-report.json",res)
    (PREFLIGHT/"summary.md").write_text(
        "# ViMax generation pilot 02 preflight 02\n\n"
        "通过固定 v7 镜像的禁网生产入口检查。固定规划的 camera tree 有8台 camera、7条父子边；原生 pipeline 因此需要8个主体视频和7个过渡视频。主体片段按 storyboard 顺序拼接，过渡片段用于子 camera 的首帧连续性，不进入最终 concat。图片配置沿用默认每个首帧2个候选，共16个首帧候选与3张人物肖像；图片发送由独立40次发送门禁保护。\n\n"
        "原生输出时长依配置为8×5秒，预期40秒，最终容差±1秒；每段5秒容差±0.25秒。北京 list-price 媒体成本估计最多约15.81元（含最高57张输入参考图的估算，不含 qwen3.7-plus tokens）；实际账单未知，20元只是参考。镜像、规划、路由、权限和预算详见 `preflight-report.json`。\n",
        encoding="utf-8")
    make_manifest(PREFLIGHT)
    return res

def now(): return datetime.now(timezone.utc).isoformat(timespec="seconds")

def net_snapshot(cid):
    r=run(DOCKER+["exec",cid,"cat","/proc/net/dev"],10); ts=time.monotonic_ns()
    if r.returncode:return {"t_monotonic_ns":ts,"read_status":"error","error":"container_netdev_read_failed"}
    interfaces={}
    for line in r.stdout.splitlines()[2:]:
        if ":" not in line:continue
        name,vals=line.split(":",1); nums=vals.split()
        if len(nums)>=9:interfaces[name.strip()]={"rx_bytes":int(nums[0]),"tx_bytes":int(nums[8])}
    return {"t_monotonic_ns":ts,"read_status":"ok","scope":"container_netns_interfaces","interfaces":interfaces}

def read_creds_and_route():
    values,host=creds_runtime_only()
    if not host.endswith(".cn-beijing.maas.aliyuncs.com"): raise RuntimeError("registered WorkspaceId route is not cn-beijing")
    return values,host

def freeze_identity(out: Path):
    pre=json.loads((out/"preflight.json").read_text())
    # Credential availability and route structure are verified without retaining values.
    values,host=creds_runtime_only()
    route_ok=host.endswith(".cn-beijing.maas.aliyuncs.com")
    values.clear()
    if not route_ok: raise RuntimeError("registered workspace route preflight failed")
    rid="vimax-generation-pilot-02-20261024T"+datetime.now(timezone.utc).strftime("%H%M%SZ")+"-"+uuid.uuid4().hex[:8]
    ident={"task":"VIMAX-GENERATION-PILOT-02","run_id":rid,"attempt":1,"retry":0,"image":pre["image"],"adapter_source_sha256_map":{k:v for k,v in sorted(source_hashes().items())},"generation_entry_sha256":pre["generation_entry_sha256"],"host_runner_sha256":sha(Path(__file__).resolve()),"planning_source":pre["planning_source"],"models":{"language_vision":"qwen3.7-plus","image":"qwen-image-3.0","video":"wan2.6-i2v-flash","region":"cn-beijing","workspace_id":"registered value verified in memory; not retained"},"routes":{"llm_base_url":LLM_URL,"image_base_url":"https://<registered-workspace>.cn-beijing.maas.aliyuncs.com/compatible-mode/v1","video_base_url":"https://<registered-workspace>.cn-beijing.maas.aliyuncs.com","fallback":"disabled"},"media_config":pre["media_config"],"model_config":pre["model_config"],"budget":pre["budget"],"tool_policy":{"allowed_tools":["vimax_render_video"],"planning_tools":False,"shell":False,"image_create_cap":40,"video_create_cap":15},"resource_policy":{"cgroup_period_target_s":0.5,"netns_period_target_s":NET_PERIOD_S,"network_mode":"bridge","cpus":8,"memory_bytes":8589934592},"approval_scope":{"one_attempt":True,"retry":0,"media_generation_authorized":True,"provider_bill":"unknown; user accepts within call caps"},"frozen_at_utc":now()}
    path=out/"identity-01.json";write(path,ident)
    approval={"task":ident["task"],"run_id":rid,"attempts_authorized":1,"retry":0,"identity_sha256":sha(path),"authorized_operations":["native render tool","image generation and selection","8 shot + 7 transition video creates","native ffmpeg concat","independent technical audit","resource sampling and cleanup"],"hard_caps":pre["budget"],"cost_estimate":pre["cost_estimate"],"created_before_first_paid_request":True,"credentials_saved":False}
    write(out/"APPROVAL-01.json",approval)
    return ident,approval

def start_attempt(out: Path, approval_path: Path):
    pre=json.loads((out/"preflight.json").read_text())
    identity_path=out/"identity-01.json"
    approval=json.loads(approval_path.read_text())
    if approval.get("identity_sha256")!=sha(identity_path):raise RuntimeError("approval identity mismatch")
    identity=json.loads(identity_path.read_text())
    if identity.get("image")!=pre["image"] or identity.get("generation_entry_sha256")!=pre["generation_entry_sha256"]:raise RuntimeError("frozen identity drift")
    work=out/"workspace"; attempt=work/"attempt"
    if (out/"ATTEMPT-STARTED").exists():raise RuntimeError("attempt already started")
    # This timestamp and monotonic start are persisted before runtime credentials or model requests.
    t0=time.monotonic(); start_utc=now(); run_id=identity["run_id"]
    (out/"ATTEMPT-STARTED").write_text(start_utc+"\n",encoding="utf-8")
    record={"task":"VIMAX-GENERATION-PILOT-02","run_id":run_id,"attempt":1,"retry":0,"started_utc":start_utc,"t0_monotonic":t0,"identity_sha256":sha(identity_path),"approval_sha256":sha(approval_path),"image":pre["image"],"route":pre["model_config"],"budgets":pre["budget"],"container":{"network_mode":"bridge","cpus":8,"memory_bytes":8589934592},"phase_boundaries":{},"termination":"starting","cleanup_errors":[],"http_exchange_count":"unknown"}
    write(out/"run-record.json",record)
    before={"workspace_bytes":sum(p.stat().st_size for p in work.rglob("*") if p.is_file()),"attempt_bytes":sum(p.stat().st_size for p in attempt.rglob("*") if p.is_file()),"planning_input_bytes":sum(p.stat().st_size for p in PLAN.rglob("*") if p.is_file()),"execution_output_root_bytes":sum(p.stat().st_size for p in out.rglob("*") if p.is_file())}
    write(out/"directory-before.json",before)
    sampler=ResourceSampler(interval_s=.5); sampler_started=False; cid=""; stop=threading.Event(); net_rows=[]; net_lock=threading.Lock(); thread=None
    errors=record["cleanup_errors"]; work_deadline=t0+WORK_S; close_deadline=work_deadline+CLOSEOUT_S
    try:
        creds,host=read_creds_and_route()
        env={"HOME":"/tmp","PYTHONPATH":"/opt/vimax/src:/opt/run","VIMAX_LLM_MODEL":"qwen3.7-plus","VIMAX_LLM_MODEL_PROVIDER":"openai","VIMAX_LLM_BASE_URL":LLM_URL,"VIMAX_LLM_API_KEY":creds["DASHSCOPE_API_KEY"],"VIMAX_AGENT_MAX_TOKENS":"8192","VIMAX_NARRATIVE_MAX_TOKENS":"8192","VIMAX_IMAGE_MODEL":"qwen-image-3.0","VIMAX_IMAGE_BASE_URL":f"https://{host}/compatible-mode/v1","VIMAX_IMAGE_API_KEY":creds["DASHSCOPE_API_KEY"],"VIMAX_VIDEO_MODEL":"wan2.6-i2v-flash","VIMAX_VIDEO_BASE_URL":f"https://{host}","VIMAX_VIDEO_API_KEY":creds["DASHSCOPE_API_KEY"],"VIMAX_BAILIAN_EVENT_LOG":"/workspace/attempt/model-events.jsonl","VIMAX_BAILIAN_BUDGET_LLM_CALLS":"80","VIMAX_BAILIAN_BUDGET_LLM_ATTEMPTS":"80","VIMAX_BAILIAN_BUDGET_IMAGE_GENERATIONS":"40","VIMAX_BAILIAN_BUDGET_VIDEO_CREATES":"15","VIMAX_BAILIAN_BUDGET_TRANSITIONS":"7","VIMAX_BAILIAN_BUDGET_VIDEO_POLLS":"1800","VIMAX_BAILIAN_BUDGET_MEDIA_DOWNLOADS":"80","VIMAX_BAILIAN_BUDGET_SINGLE_REQUEST_OUTPUT_TOKENS":"8192","VIMAX_BAILIAN_BUDGET_OBSERVED_OUTPUT_TOKENS_TOTAL":"500000","VIMAX_BAILIAN_BUDGET_DEADLINE_SECONDS":"5400","VIMAX_BAILIAN_VIDEO_POLL_INTERVAL_SECONDS":"10","VIMAX_BAILIAN_VIDEO_QUERY_TIMEOUT_SECONDS":"900","VIMAX_BAILIAN_VIDEO_DURATION":"5","VIMAX_BAILIAN_VIDEO_RESOLUTION":"720P","VIMAX_BAILIAN_VIDEO_AUDIO":"false","VIMAX_BAILIAN_VIDEO_PROMPT_EXTEND":"false","VIMAX_BAILIAN_VIDEO_CREATE_TIMEOUT_SECONDS":"60","VIMAX_BAILIAN_HTTP_MAX_ATTEMPTS":"2","VIMAX_IMAGE_NUM_CANDIDATES":"2","VIMAX_VIDEO_CAPABILITY_PROFILE":"bailian-wan26-i2v-first-frame","VIMAX_ENABLE_RUN_SHELL":"0"}
        name="vimax-gen02-"+uuid.uuid4().hex[:10]
        args=DOCKER+["run","-d","--name",name,"--label",f"org.agent-workload.task={run_id}","--network","bridge","--read-only","--tmpfs","/tmp:rw,nosuid,nodev,size=1g","--memory","8g","--cpus","8","--pids-limit","512","--user",f"{os.getuid()}:{os.getgid()}","--workdir","/workspace","--mount",f"type=bind,source={work},target=/workspace","--mount",f"type=bind,source={PLAN},target=/planning,readonly","--mount",f"type=bind,source={BASE/'generation_entry.py'},target=/opt/run/generation_entry.py,readonly"]
        for k,v in env.items():args += ["-e",f"{k}={v}"]
        args += [IMAGE,"python3","/opt/run/generation_entry.py"]
        started=run(args,60); creds.clear(); env={k:("<redacted>" if "API_KEY" in k else v) for k,v in env.items()}
        if started.returncode:raise RuntimeError("container start failed; sensitive runtime output suppressed")
        cid=started.stdout.strip(); record["container"].update({"name":name,"id":cid}); record["termination"]="running"; record["route_workspace_host_value"]="redacted; matches registered cn-beijing workspace host"
        write(out/"run-record.json",record)
        owned=run(DOCKER+["inspect","-f",'{{index .Config.Labels "org.agent-workload.task"}}',cid],10)
        if owned.returncode or owned.stdout.strip()!=run_id:raise RuntimeError("container ownership verification failed")
        sampler.register(run_id,"agent_container",CgroupV1FileReader(run_id,"agent_container",cid));sampler.start(run_id);sampler.start_background_sampling();sampler_started=True
        def netloop():
            deadline=time.monotonic()
            while not stop.is_set():
                with net_lock:net_rows.append(net_snapshot(cid))
                deadline+=NET_PERIOD_S;stop.wait(max(0,deadline-time.monotonic()))
        thread=threading.Thread(target=netloop,daemon=True);thread.start()
        complete=attempt/"COMPLETE"
        while time.monotonic()<work_deadline:
            if complete.is_file():record["termination"]="native_agent_done";break
            state=run(DOCKER+["inspect","-f","{{.State.Running}}",cid],8)
            if state.returncode==0 and state.stdout.strip()=="false":record["termination"]="container_exited_without_complete";break
            time.sleep(.5)
        else:record["termination"]="work_deadline"
        record["phase_boundaries"]["agent_work"]={"start_monotonic":t0,"end_monotonic":time.monotonic(),"deadline_reached":record["termination"]=="work_deadline"}
        with net_lock:net_rows.append(net_snapshot(cid))
        if record["termination"]=="work_deadline":run(DOCKER+["kill",cid],10)
    except BaseException as exc:
        record["termination"]="runner_exception";record["primary_error"]={"type":type(exc).__name__,"message":str(exc)[:500]}
    finally:
        stop.set()
        if thread:
            thread.join(timeout=10)
            if thread.is_alive():errors.append("netns_sampler_thread_join_timeout")
        if sampler_started:
            try:sampler.stop_background_sampling();sampler.stop(record["run_id"])
            except Exception as exc:errors.append("sampler_stop:"+type(exc).__name__)
        try:
            if cid:
                deadline=time.monotonic()+CLOSEOUT_S
                if time.monotonic()<deadline:run(DOCKER+["stop","-t","15",cid],20)
                waited=run(DOCKER+["wait",cid],15);record["container_exit_code"]=int(waited.stdout.strip()) if waited.returncode==0 and waited.stdout.strip().isdigit() else None
                rm=run(DOCKER+["rm","-f",cid],20);record["container_rm_returncode"]=rm.returncode
                record["container_removed_verified"]=run(DOCKER+["inspect",cid],8).returncode!=0
                if not record["container_removed_verified"]:errors.append("container_removal_not_verified")
        except Exception as exc:errors.append("container_cleanup:"+type(exc).__name__)
        record["phase_boundaries"]["closeout_end_monotonic"]=time.monotonic();record["total_wall_s"]=time.monotonic()-t0
        record["attempt_wall_s"]=record["total_wall_s"]
        if sampler_started:
            try:
                evidence=sampler.all_scope_evidence();write(out/"resource-evidence.json",evidence)
                samples=evidence.get(record["run_id"],{}).get("samples",[])
                (out/"resource-samples.jsonl").write_text("".join(json.dumps(x,ensure_ascii=False)+"\n" for x in samples))
                record["resource_summary"]=sampler.all_scope_summaries()
            except Exception as exc:errors.append("resource_export:"+type(exc).__name__)
        with net_lock: nrows=list(net_rows)
        (out/"netns-samples.jsonl").write_text("".join(json.dumps(x)+"\n" for x in nrows))
        (out/"directory-after.json").write_text(json.dumps({"workspace_bytes":sum(p.stat().st_size for p in work.rglob("*") if p.is_file()),"attempt_bytes":sum(p.stat().st_size for p in (work/"attempt").rglob("*") if p.is_file()),"planning_input_bytes":sum(p.stat().st_size for p in PLAN.rglob("*") if p.is_file()),"execution_output_root_bytes":sum(p.stat().st_size for p in out.rglob("*") if p.is_file())},indent=2)+"\n")
        if (work/"attempt/COMPLETE").exists():
            try:record["agent_complete"]=json.loads((work/"attempt/COMPLETE").read_text())
            except Exception:record["agent_complete"]="corrupt"
        record["network_scope"]="container netns per-interface RX/TX; not API-specific bytes"
        record["http_exchange_count"]="unknown; no transport-level counter"
        record["cleanup_errors"]=errors
        write(out/"run-record.json",record)
        try:write(out/"run-report.json",summarize(out,record))
        except Exception as exc:record["report_generation"]={"status":"failed","error_type":type(exc).__name__}
        write(out/"run-record.json",record)
    make_manifest(out.parent)
    return 0 if record.get("termination")=="native_agent_done" and not errors else 1

def summarize(out,record):
    a=out/"workspace/attempt";rows=[]
    for p in (a/"model-events.jsonl",):
        if p.exists():
            for line in p.read_text().splitlines():
                try:rows.append(json.loads(line))
                except:rows.append({"parse_error":True})
    opened=[r for r in rows if r.get("kind")=="open"]
    llm=[r for r in opened if r.get("op")=="llm_chat"]
    media={op:sum(r.get("op")==op and r.get("kind")=="open" for r in rows) for op in ("image_generation","video_create","video_poll","media_download")}
    usage=[r.get("usage") for r in rows if r.get("kind")=="close" and isinstance(r.get("usage"),dict)]
    totals=[u.get("total_tokens") for u in usage if isinstance(u,dict)]
    agent=[]
    p=a/"agent-events.jsonl"
    if p.exists():
        for line in p.read_text().splitlines():
            try:agent.append(json.loads(line))
            except:pass
    return {"task":"VIMAX-GENERATION-PILOT-02","run_id":record["run_id"],"attempt":1,"retry":0,"result":{"native_agent_completed":record.get("termination")=="native_agent_done","render_tool_ok":(record.get("agent_complete") or {}).get("render_tool_ok"),"media_acceptance":"pending_offline_audit"},"requests":{"logical_llm_requests":len(llm),"llm_project_attempts":sum(r.get("op")=="llm_attempt" for r in opened),"http_exchanges":"unknown","usage_records":usage,"observed_total_tokens":sum(totals) if len(totals)==len(usage) else None,"unclosed_request_ids":[r.get("request_id") for r in opened if r.get("request_id") not in {x.get("request_id") for x in rows if x.get("kind") in ("close","error")} ]},"media_events":media,"agent":{"events":len(agent),"tool_results":[r.get("tool_result") for r in agent if r.get("type")=="tool_result"]},"time":{"attempt_wall_s":record.get("attempt_wall_s"),"phase_boundaries":record.get("phase_boundaries")},"resources":record.get("resource_summary"),"network_scope":record.get("network_scope"),"cleanup":{"removed_verified":record.get("container_removed_verified"),"errors":record.get("cleanup_errors")},"billing":"unknown; list-price media-output estimate 14.67 CNY excludes image inputs and LLM/VLM"}

def make_manifest(root):
    files=[]
    for p in sorted(root.rglob("*")):
        if not p.is_file() or p.name=="manifest.json" or "__pycache__" in p.parts or p.suffix==".pyc":continue
        files.append({"path":p.relative_to(root).as_posix(),"bytes":p.stat().st_size,"sha256":sha(p)})
    write(root/"manifest.json",{"task":"VIMAX-GENERATION-PILOT-02","files":files,"self_hash":"omitted"})

def main():
    p=argparse.ArgumentParser();p.add_argument("mode",choices=("preflight","run","execute"));p.add_argument("--out",required=True);p.add_argument("--approval");a=p.parse_args();out=Path(a.out).resolve()
    if a.mode=="preflight":
        result=preflight(out);print(json.dumps(result,ensure_ascii=False,indent=2));return 0
    if a.mode=="execute":
        result=preflight(out)
        ident,approval=freeze_identity(out)
        # Preflight and authorization are durably saved before the live attempt starts.
        (out/"ATTEMPT-STARTED").unlink(missing_ok=True)
        rc=start_attempt(out,out/"APPROVAL-01.json")
        make_manifest(out.parent)
        return rc
    if not a.approval:raise SystemExit("--approval required")
    return start_attempt(out,Path(a.approval))
if __name__=="__main__":raise SystemExit(main())
