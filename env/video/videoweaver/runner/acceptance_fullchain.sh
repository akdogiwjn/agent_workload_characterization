#!/usr/bin/env bash
# VIDEO-WEAVER offline cold-start acceptance: REAL production pipeline
# (AutomaticSkillOptimization/inference_CodeX/pipeline.py) + REAL Codex binary +
# REAL skills/FFmpeg, with network=none and ONLY the external model/media API
# boundary faked. Fresh empty workspace each run.
set -euo pipefail
ROOT=/home/lcq/agent_workload_characterization
VW=$ROOT/env/video/videoweaver
CASE=$VW/case/dataset
FAKE=$VW/fake/fake_responses.py
FAKECFG=$VW/runner/fake-codex-config.toml
OUTVOL=$ROOT/env/video/videoweaver/evidence/acceptance-output
FAKEVOL=$ROOT/env/video/videoweaver/evidence/acceptance-fake
CLOSEVOL=$ROOT/env/video/videoweaver/evidence/acceptance-closeout
EXP_ID="${EXP_ID:-videoweaver-acceptance-01}"
NET="${NET:-none}"

# Container-scoped cleanup: task image runs as root, so evidence volumes are
# reset/chowned inside a throwaway container (host lcq cannot unlink root-owned
# files; ViMax/OpenStoryline permission lesson).
for VOL in "$OUTVOL" "$FAKEVOL" "$CLOSEVOL"; do
  mkdir -p "$VOL"
  docker run --rm -v "$VOL":/v videoweaver-task-bailian:arm64-v1     sh -c 'rm -rf /v/* 2>/dev/null; chmod -R 777 /v' >/dev/null 2>&1 || true
done

docker run --rm -i --network "$NET" \
  --add-host ws-fake.cn-beijing.maas.aliyuncs.com:127.0.0.1 \
  -e DASHSCOPE_API_KEY=fake-offline-key \
  -e VW_CASE_TXT=/opt/videoweaver/case/dataset/photographer_urban_timelapses/case-photographer-urban-01/task.txt \
  -e VW_FAKE_OUTPUT_DIR=/opt/videoweaver/generate_materials \
  -e VW_FAKE_STATE_PATH=/tmp/fake-state/state.json \
  -e VW_FAKE_MAX_RESPONSES=40 \
  -e VW_IMAGE_BASE_URL=http://ws-fake.cn-beijing.maas.aliyuncs.com:8666/compatible-mode/v1 \
  -e VW_VIDEO_BASE_URL=http://ws-fake.cn-beijing.maas.aliyuncs.com:8666 \
  -e VW_VISION_BASE_URL=http://ws-fake.cn-beijing.maas.aliyuncs.com:8666/compatible-mode/v1 \
  -e VW_LLM_BASE_URL=http://ws-fake.cn-beijing.maas.aliyuncs.com:8666/compatible-mode/v1 \
  -e VW_PYTHON=/opt/videoweaver-venv/bin/python \
  -e VW_OUTPUT_DIR=/opt/videoweaver/generate_materials \
  -v "$CASE":/opt/videoweaver/case/dataset:ro \
  -v "$FAKE":/opt/vw-run/fake_responses.py:ro \
  -v "$FAKECFG":/opt/codex-home/config.toml:ro \
  -v "$OUTVOL":/opt/videoweaver/generate_materials \
  -v "$FAKEVOL":/tmp/fake-state \
  -v "$CLOSEVOL":/opt/vw-closeout \
  videoweaver-task-bailian:arm64-v1 \
  bash -c '
    mkdir -p /tmp/fake-state /opt/vw-closeout
    python /opt/vw-run/fake_responses.py > /tmp/fake-state/fake-server.out 2>&1 &
    FAKE_PID=$!
    sleep 1
    echo "=== pipeline start ==="
    set +e
    /opt/videoweaver-venv/bin/python \
      /opt/videoweaver/AutomaticSkillOptimization/inference_CodeX/pipeline.py \
      --dataset /opt/videoweaver/case/dataset \
      --target_task photographer_urban_timelapses \
      --no_composition_skills true \
      --test_sample 1 \
      --max_concurrency 1 \
      --max_retries 1 \
      --task_max_retries 1 \
      --retry_delay 0 \
      --timeout_seconds 600 \
      --exp_id '"$EXP_ID"' \
      --skip_copy false \
      --dry_run false \
      --random_seed 42
    PIPELINE_RC=$?
    set -e
    echo "pipeline rc=$PIPELINE_RC"
    kill $FAKE_PID 2>/dev/null || true
    echo "=== acceptance media tree (exp_dir) ==="
    EXP=/opt/videoweaver/videoweaver-acceptance-01
    find "$EXP" -maxdepth 4 -type f 2>/dev/null | sort | head -80
    echo "=== copy exp_dir to closeout ==="
    cp -r "$EXP" /opt/vw-closeout/ 2>/dev/null || echo "no exp dir"
    echo "=== ffprobe final ==="
    FINAL=$(find /opt/videoweaver -name final.mp4 2>/dev/null | head -1)
    if [ -n "$FINAL" ]; then
      echo "FINAL=$FINAL"
      ffprobe -v error -show_entries format=duration,size -show_entries stream=codec_name,width,height,avg_frame_rate,codec_type "$FINAL"
    else
      echo "NO_FINAL_MP4"
    fi
    echo "=== clips ==="
    find /opt/videoweaver -name "shot*.mp4" 2>/dev/null | sort | while read f; do
      echo -n "$(basename $f): "; sha256sum "$f" | cut -c1-16
    done
    echo "=== rollout summary ==="
    mkdir -p /opt/vw-closeout/sessions
    cp -r /opt/codex-home/sessions/. /opt/vw-closeout/sessions/ 2>/dev/null || true
    R=$(find /opt/codex-home/sessions -name "rollout-*.jsonl" | head -1)
    python - "$R" <<PY
import json,sys
p=sys.argv[1]
if p and __import__("os").path.exists(p):
    recs=[json.loads(l) for l in open(p) if l.strip()]
    types={}
    for r in recs:
        t=r.get("type"); types[t]=types.get(t,0)+1
    print("rollout",p)
    print("record types:",types)
PY
    echo "=== fake state summary ==="
    python - <<PY
import json,os
p="/tmp/fake-state/state.json"
if os.path.exists(p):
    st=json.load(open(p))
    print("responses_calls",st.get("responses_calls"))
    print("image_creates",len(st.get("image_creates",[])))
    print("video_creates",len(st.get("video_creates",[])))
    print("media_downloads",st.get("media_downloads"))
    print("rejected",st.get("rejected_unknown_hosts"))
else:
    print("no state")
PY
    echo "=== rollout jsonl files ==="
    find /opt/codex-home/sessions -name "rollout-*.jsonl" 2>/dev/null | head
    echo "=== running logs ==="
    find /opt/videoweaver -name "000_overall.log" -o -name "*.log" 2>/dev/null | grep -v sessions | head
    exit $PIPELINE_RC
  '
