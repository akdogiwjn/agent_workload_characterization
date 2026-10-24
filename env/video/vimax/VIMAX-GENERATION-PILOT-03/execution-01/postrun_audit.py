#!/usr/bin/env python3
"""Offline ffprobe/decode and artifact audit for the one media attempt."""
from __future__ import annotations
import csv, hashlib, json, math, subprocess, sys
from pathlib import Path

BASE=Path(__file__).resolve().parent
RUN=BASE/"run-01"
WORK=RUN/"workspace"
SESSION="generation-pilot-03-media-01"
SCRIPT=WORK/".working_dir"/SESSION/"script2video"
OUT=RUN/"audit"

def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()

def cmd(argv,timeout=600):
 try:return subprocess.run(argv,capture_output=True,text=True,timeout=timeout)
 except subprocess.TimeoutExpired as e:return subprocess.CompletedProcess(argv,124,e.stdout or '',e.stderr or 'TIMEOUT')

def probe(path):
 r=cmd(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(path)],60)
 if r.returncode:return {'ok':False,'returncode':r.returncode,'stderr':r.stderr[-2000:]}
 try:d=json.loads(r.stdout)
 except Exception:return {'ok':False,'returncode':r.returncode,'stderr':'invalid ffprobe JSON'}
 streams=d.get('streams',[]); v=next((s for s in streams if s.get('codec_type')=='video'),None); a=[s for s in streams if s.get('codec_type')=='audio']
 if not v:return {'ok':False,'reason':'no_video_stream','format':d.get('format')}
 def fps(val):
  try:x,y=val.split('/');return float(x)/float(y)
  except Exception:return None
 return {'ok':True,'duration_s':float(d.get('format',{}).get('duration',0) or 0),'size_bytes':int(d.get('format',{}).get('size',0) or 0),'video':{'codec':v.get('codec_name'),'width':v.get('width'),'height':v.get('height'),'pix_fmt':v.get('pix_fmt'),'r_fps':fps(v.get('r_frame_rate','')),'avg_fps':fps(v.get('avg_frame_rate',''))},'audio_stream_count':len(a)}

def decode(path,log):
 r=cmd(['ffmpeg','-hide_banner','-v','error','-i',str(path),'-f','null','-'],600)
 log.write_text(r.stderr or '',encoding='utf-8')
 return {'returncode':r.returncode,'ok':r.returncode==0,'stderr_bytes':len(r.stderr or '')}

def video_row(path,kind,idx,parent=None):
 if not path.is_file():return {'kind':kind,'index':idx,'parent':parent,'exists':False,'path':str(path)}
 q=probe(path); dec=decode(path,OUT/f"decode-{kind}-{idx}.log")
 black=cmd(['ffmpeg','-hide_banner','-i',str(path),'-vf','blackdetect=d=0.1:pix_th=0.10','-an','-f','null','-'],600)
 (OUT/f"blackdetect-{kind}-{idx}.log").write_text(black.stderr or '',encoding='utf-8')
 black_segments=[line.strip() for line in (black.stderr or '').splitlines() if 'black_start:' in line]
 checks={'probe_ok':q.get('ok') is True,'h264':(q.get('video') or {}).get('codec')=='h264','720p':(q.get('video') or {}).get('width')==1280 and (q.get('video') or {}).get('height')==720,'yuv420p':(q.get('video') or {}).get('pix_fmt')=='yuv420p','30fps':abs(((q.get('video') or {}).get('avg_fps') or -99)-30)<0.05,'duration_5s':abs((q.get('duration_s') or 0)-5)<=.25,'no_audio':q.get('audio_stream_count')==0,'full_decode':dec['ok'],'blackdetect_ran':black.returncode==0}
 return {'kind':kind,'index':idx,'parent':parent,'exists':True,'path':str(path.relative_to(WORK)),'bytes':path.stat().st_size,'sha256':sha(path),'probe':q,'decode':dec,'blackdetect_returncode':black.returncode,'black_segments_at_least_0_1s':black_segments,'checks':checks,'ok':all(checks.values())}

def resources():
 p=RUN/'resource-evidence.json'; csv_path=RUN/'resource-points.csv'
 if not p.exists():return {'status':'missing'}
 raw=json.loads(p.read_text()); scope=next(iter(raw.values()),{}); pts=scope.get('samples',[]); rows=[]
 with csv_path.open('w',newline='',encoding='utf-8') as f:
  w=csv.writer(f);w.writerow(['t_monotonic_ns','elapsed_s','interval_s','cpu_usage_usec','cpu_avg_cores','memory_current_bytes','memory_current_GiB','memory_peak_bytes','io_read_bytes','io_write_bytes','io_read_Bps','io_write_Bps','read_status_json'])
  for i,x in enumerate(pts):
   prev=pts[i-1] if i else None; dt=(x['t_monotonic_ns']-prev['t_monotonic_ns'])/1e9 if prev else None
   dc=(x.get('cpu_usage_usec')-prev.get('cpu_usage_usec')) if prev and None not in (x.get('cpu_usage_usec'),prev.get('cpu_usage_usec')) else None
   dr=(x.get('io_read_bytes')-prev.get('io_read_bytes')) if prev and None not in (x.get('io_read_bytes'),prev.get('io_read_bytes')) else None
   dw=(x.get('io_write_bytes')-prev.get('io_write_bytes')) if prev and None not in (x.get('io_write_bytes'),prev.get('io_write_bytes')) else None
   cores=(dc/1e6/dt) if dt and dt>0 and dc is not None and dc>=0 else None
   row={'t_monotonic_ns':x.get('t_monotonic_ns'),'elapsed_s':((x.get('t_monotonic_ns',0)-pts[0].get('t_monotonic_ns',0))/1e9 if pts else None),'interval_s':dt,'cpu_usage_usec':x.get('cpu_usage_usec'),'cpu_avg_cores':cores,'memory_current_bytes':x.get('mem_current_bytes'),'memory_current_GiB':x.get('mem_current_bytes')/1073741824 if isinstance(x.get('mem_current_bytes'),int) else None,'memory_peak_bytes':x.get('mem_peak_bytes'),'io_read_bytes':x.get('io_read_bytes'),'io_write_bytes':x.get('io_write_bytes'),'io_read_Bps':(dr/dt if dt and dt>0 and dr is not None and dr>=0 else None),'io_write_Bps':(dw/dt if dt and dt>0 and dw is not None and dw>=0 else None),'read_status':x.get('read_status')}
   rows.append(row);w.writerow([row.get(k) if k!='read_status' else json.dumps(row[k]) for k in ['t_monotonic_ns','elapsed_s','interval_s','cpu_usage_usec','cpu_avg_cores','memory_current_bytes','memory_current_GiB','memory_peak_bytes','io_read_bytes','io_write_bytes','io_read_Bps','io_write_Bps','read_status']])
 net=[]; nfile=RUN/'netns-samples.jsonl'
 if nfile.exists():
  for ln in nfile.read_text().splitlines():
   try:net.append(json.loads(ln))
   except:pass
 with (RUN/'netns-points.csv').open('w',newline='',encoding='utf-8') as f:
  w=csv.writer(f);w.writerow(['t_monotonic_ns','interface','rx_bytes','tx_bytes','interval_s','rx_Bps','tx_Bps','read_status'])
  for i,x in enumerate(net):
   y=net[i-1] if i else None;dt=(x['t_monotonic_ns']-y['t_monotonic_ns'])/1e9 if y else None
   for iface,v in (x.get('interfaces') or {}).items():
    prev=(y.get('interfaces') or {}).get(iface,{}) if y else {}
    rx=(v['rx_bytes']-prev.get('rx_bytes'))/dt if dt and prev and v['rx_bytes']>=prev.get('rx_bytes',v['rx_bytes']) else None
    tx=(v['tx_bytes']-prev.get('tx_bytes'))/dt if dt and prev and v['tx_bytes']>=prev.get('tx_bytes',v['tx_bytes']) else None
    w.writerow([x.get('t_monotonic_ns'),iface,v.get('rx_bytes'),v.get('tx_bytes'),dt,rx,tx,x.get('read_status')])
 return {'scope':scope.get('scope_kind'),'interval_target_s':scope.get('interval_target_s'),'sample_count':len(pts),'boundary_start':scope.get('boundary_start'),'boundary_end':scope.get('boundary_end'),'missing_or_gaps':sum(1 for r in rows if r['interval_s'] is None or r['interval_s']>0.75),'netns_sample_count':len(net),'netns_scope':'container netns per-interface; no cross-interface aggregation','points_csv':'resource-points.csv','netns_csv':'netns-points.csv'}

def main():
 OUT.mkdir(parents=True,exist_ok=True)
 plan=json.loads((SCRIPT/'camera_tree.json').read_text()); story=json.loads((SCRIPT/'storyboard.json').read_text())
 shots=[]
 for i in range(8):shots.append(video_row(SCRIPT/'shots'/str(i)/'video.mp4','shot',i))
 transitions=[]
 for c in plan:
  if c.get('parent_cam_idx') is not None:
   child=c['idx'];parent=c.get('parent_shot_idx')
   transitions.append(video_row(SCRIPT/'shots'/str(child)/f"transition_video_from_shot_{parent}.mp4",'transition',child,parent))
 final=video_row(SCRIPT/'final_video.mp4','final',None)
 if final.get('exists'):
  q=final.get('probe') or {}; final['checks']={'probe_ok':q.get('ok') is True,'h264':(q.get('video') or {}).get('codec')=='h264','720p':(q.get('video') or {}).get('width')==1280 and (q.get('video') or {}).get('height')==720,'yuv420p':(q.get('video') or {}).get('pix_fmt')=='yuv420p','30fps':abs(((q.get('video') or {}).get('avg_fps') or -99)-30)<.05,'duration_about_40s':abs((q.get('duration_s') or 0)-40)<=1.0,'no_audio':q.get('audio_stream_count')==0,'full_decode':final.get('decode',{}).get('ok') is True};final['ok']=all(final['checks'].values())
 timed=[]; p=WORK/'attempt/agent-events-timed.jsonl'
 if p.exists():
  for ln in p.read_text().splitlines():
   try:timed.append(json.loads(ln))
   except:pass
 task_scopes={}
 for row in timed:
  e=row.get('event',{}); prog=e.get('progress') or {}; meta=prog.get('metadata') or {}
  if prog.get('stage')=='video_poll_succeeded' and meta.get('task_id'):
   task_scopes[meta['task_id']]={k:meta.get(k) for k in ('shot_idx','parent_shot_idx','artifact','camera_idx')}
 ledger=[];p=WORK/'attempt/model-events.jsonl'
 if p.exists():
  for ln in p.read_text().splitlines():
   try:ledger.append(json.loads(ln))
   except:pass
 task_rows=[]
 for r in ledger:
  if r.get('kind')=='close' and r.get('op')=='video_create':task_rows.append({'task_id':r.get('task_id'),'status':r.get('status'),'mapping_from_progress':task_scopes.get(r.get('task_id'))})
 selected=[];selection_files=list(SCRIPT.rglob('selection.json'))
 for sf in selection_files:
  try:d=json.loads(sf.read_text())
  except:continue
  chosen=d.get('selected_candidate_index'); candidates=d.get('candidates') or []; chosen_row=next((x for x in candidates if x.get('index')==chosen),None)
  chosen_path=(sf.parent/chosen_row.get('path')).resolve() if chosen_row and chosen_row.get('path') else None
  selected.append({'selection_file':str(sf.relative_to(WORK)),'status':d.get('status'),'candidates':d.get('candidates'),'chosen_index':chosen,'selected_image_path':str(chosen_path.relative_to(WORK.resolve())) if chosen_path and chosen_path.exists() else None,'selected_image_sha256':sha(chosen_path) if chosen_path and chosen_path.exists() else None,'selection_method':d.get('selection_method'),'reason':d.get('reason')})
 media=[]
 for p in sorted(SCRIPT.rglob('*')):
  if p.is_file() and p.suffix.lower() in {'.png','.jpg','.jpeg','.mp4'}:media.append({'path':str(p.relative_to(WORK)),'bytes':p.stat().st_size,'sha256':sha(p)})
 keyframes=[];keydir=OUT/'keyframes';keydir.mkdir(exist_ok=True)
 for row in shots+transitions:
  if not row.get('exists'):continue
  src=WORK/row['path'];dest=keydir/f"{row['kind']}-{row['index']}.jpg";dur=(row.get('probe') or {}).get('duration_s',5)
  r=cmd(['ffmpeg','-hide_banner','-loglevel','error','-y','-ss',str(float(dur)/2),'-i',str(src),'-frames:v','1','-q:v','2',str(dest)],60)
  if r.returncode==0 and dest.exists():keyframes.append({'source':row['path'],'keyframe':str(dest.relative_to(RUN)),'sha256':sha(dest),'bytes':dest.stat().st_size})
 resource=resources()
 hashes={}
 for k in keyframes:hashes.setdefault(k['sha256'],[]).append(k['source'])
 duplicates=[v for v in hashes.values() if len(v)>1]
 audit={'schema':'vimax-generation-postrun-audit-v1','run_id':json.loads((RUN/'run-record.json').read_text()).get('run_id'),'source_plan_identity':'7d1f3ce8d4ad081b56e4031f93a21d93f894eef1cc759ae0ab0339eda14e26a2','storyboard_count':len(story),'camera_count':len(plan),'shot_videos':shots,'transition_videos':transitions,'final_video':final,'video_task_map':task_rows,'video_task_create_event_count':sum(r.get('op')=='video_create' and r.get('kind')=='open' for r in ledger),'image_create_logical_count':sum(r.get('op')=='image_generation' and r.get('kind')=='open' for r in ledger),'image_create_http_send_count':sum(r.get('op')=='image_create_http_send' and r.get('kind')=='open' for r in ledger),'media_download_open_count':sum(r.get('op') in ('media_download','video_download') and r.get('kind')=='open' for r in ledger),'video_poll_count':sum(r.get('op')=='video_poll' and r.get('kind')=='open' for r in ledger),'selected_image_candidate_records':selected,'media_file_manifest':media,'keyframes':keyframes,'exact_duplicate_keyframes':duplicates,'resource_observation':resource,'agent_event_count':len(timed),'model_ledger_event_count':len(ledger),'semantic_quality':'not formally scored; extracted keyframes permit visual inspection only'}
 audit['acceptance']={'all_8_shots_valid':len(shots)==8 and all(x.get('ok') is True for x in shots),'all_7_transitions_valid':len(transitions)==7 and all(x.get('ok') is True for x in transitions),'final_video_valid':final.get('ok') is True,'expected_concat_order':'storyboard index 0 through 7; transition clips not in final concat','expected_final_duration_s':sum((x.get('probe') or {}).get('duration_s',0) for x in shots),'actual_final_duration_s':(final.get('probe') or {}).get('duration_s')}
 audit['acceptance']['overall_technical_pass']=all(audit['acceptance'][k] for k in ('all_8_shots_valid','all_7_transitions_valid','final_video_valid'))
 (RUN/'postrun-audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({'audit':str(RUN/'postrun-audit.json'),'overall_technical_pass':audit['acceptance']['overall_technical_pass'],'shots_valid':sum(x.get('ok') is True for x in shots),'transitions_valid':sum(x.get('ok') is True for x in transitions),'final_valid':final.get('ok') is True,'keyframes':len(keyframes)},ensure_ascii=False))
 return 0 if audit['acceptance']['overall_technical_pass'] else 1
if __name__=='__main__':raise SystemExit(main())
