#!/usr/bin/env bash
# VIDEO-WEAVER offline counter-examples: unverified modes must be rejected
# BEFORE sending, and the fake boundary must see ZERO extra media requests.
set -euo pipefail
ROOT=/home/lcq/agent_workload_characterization
VW=$ROOT/env/video/videoweaver
FAKE=$VW/fake/fake_responses.py
FAKECFG=$VW/runner/fake-codex-config.toml
FAKEVOL=$ROOT/env/video/videoweaver/evidence/counterexamples-fake
mkdir -p "$FAKEVOL"

docker run --rm -i --network none \
  --add-host ws-fake.cn-beijing.maas.aliyuncs.com:127.0.0.1 \
  -e DASHSCOPE_API_KEY=fake-offline-key \
  -e VW_CASE_TXT=/opt/videoweaver/case/dataset/photographer_urban_timelapses/case-photographer-urban-01/task.txt \
  -e VW_FAKE_OUTPUT_DIR=/opt/videoweaver/generate_materials \
  -e VW_FAKE_STATE_PATH=/tmp/fake-state/state.json \
  -e VW_IMAGE_BASE_URL=http://127.0.0.1:8899/compatible-mode/v1 \
  -e VW_VIDEO_BASE_URL=http://127.0.0.1:8899 \
  -e VW_VISION_BASE_URL=http://127.0.0.1:8899/compatible-mode/v1 \
  -e VW_PYTHON=/opt/videoweaver-venv/bin/python \
  -e VW_OUTPUT_DIR=/opt/videoweaver/generate_materials \
  -v "$VW/case/dataset":/opt/videoweaver/case/dataset:ro \
  -v "$FAKE":/opt/vw-run/fake_responses.py:ro \
  -v "$FAKECFG":/opt/codex-home/config.toml:ro \
  -v "$FAKEVOL":/tmp/fake-state \
  videoweaver-task-bailian:arm64-v1 \
  bash -c '
    mkdir -p /tmp/fake-state /opt/videoweaver/generate_materials
    python /opt/vw-run/fake_responses.py > /tmp/fake-state/fake-server.out 2>&1 &
    FAKE_PID=$!
    sleep 1
    PY=/opt/videoweaver-venv/bin/python
    OUT=/opt/videoweaver/generate_materials
    export CODEX_THREAD_NAME=cx NAME=counter CODEX_THREAD_ID=counter-test
    run_case() {
      local label="$1"; shift
      set +e
      "$@" > /tmp/cx.out 2>&1
      rc=$?
      set -e
      echo "CASE $label rc=$rc (expected non-zero)"
      tail -4 /tmp/cx.out
      echo "---"
    }
    # video-gen: last frame -> reject before send
    run_case "video-last-frame" $PY /opt/videoweaver/skills/video-gen/scripts/generate.py \
      --prompt "p" --first-image /opt/videoweaver/skills/video-gen/scripts/generate.py \
      --last-image /opt/videoweaver/skills/video-gen/scripts/generate.py --output x.mp4
    # video-gen: reference video -> reject
    run_case "video-ref-video" $PY /opt/videoweaver/skills/video-gen/scripts/generate.py \
      --prompt "p" --reference-video /opt/videoweaver/skills/video-gen/scripts/generate.py --output x.mp4
    # video-gen: text-to-video (no first frame) -> reject
    run_case "video-text2video" $PY /opt/videoweaver/skills/video-gen/scripts/generate.py \
      --prompt "p" --output x.mp4
    # video-gen: unsupported model -> reject
    run_case "video-model" $PY /opt/videoweaver/skills/video-gen/scripts/generate.py \
      --prompt "p" --first-image /opt/videoweaver/skills/video-gen/scripts/generate.py \
      --model seedance --output x.mp4
    # image-gen: max_images>1 -> reject
    run_case "image-max-images" $PY /opt/videoweaver/skills/image-gen/scripts/generate.py \
      --prompt "p" --max_images 2 --output_file_name x.jpg
    # image-gen: web_search -> reject
    run_case "image-web-search" $PY /opt/videoweaver/skills/image-gen/scripts/generate.py \
      --prompt "p" --web_search --output_file_name x.jpg
    # image-gen: gpt-image-2 model -> reject
    run_case "image-model-gpt" $PY /opt/videoweaver/skills/image-gen/scripts/generate.py \
      --prompt "p" --model gpt-image-2 --output_file_name x.jpg
    kill $FAKE_PID 2>/dev/null || true
    echo "=== fake state after counterexamples ==="
    python - <<PY
import json,os
p="/tmp/fake-state/state.json"
if os.path.exists(p):
    st=json.load(open(p))
    print("image_creates", len(st.get("image_creates",[])))
    print("video_creates", len(st.get("video_creates",[])))
    print("media_downloads", st.get("media_downloads"))
    print("responses_calls", st.get("responses_calls"))
    print("rejected", st.get("rejected_unknown_hosts"))
else:
    print("no state (nothing sent)")
PY
  '
