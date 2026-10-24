#!/usr/bin/env bash
# Debug: one Codex turn against the fake Responses boundary inside the task
# image. Used to iterate on the Responses SSE contract before the full chain.
set -euo pipefail
ROOT=/home/lcq/agent_workload_characterization
CASE=$ROOT/env/video/videoweaver/case/dataset
FAKE=$ROOT/env/video/videoweaver/fake/fake_responses.py
FAKECFG=$ROOT/env/video/videoweaver/runner/fake-codex-config.toml
docker run --rm -i --network bridge \
  --add-host ws-fake.cn-beijing.maas.aliyuncs.com:127.0.0.1 \
  -e DASHSCOPE_API_KEY=fake-offline-key \
  -e VW_CASE_TXT=/opt/videoweaver/case/dataset/photographer_urban_timelapses/case-photographer-urban-01/task.txt \
  -e VW_FAKE_OUTPUT_DIR=/opt/videoweaver/generate_materials \
  -e VW_FAKE_STATE_PATH=/tmp/fake-state/state.json \
  -e VW_OUTPUT_DIR=/opt/videoweaver/generate_materials \
  -e VW_IMAGE_BASE_URL=http://ws-fake.cn-beijing.maas.aliyuncs.com:8666/compatible-mode/v1 \
  -e VW_VIDEO_BASE_URL=http://ws-fake.cn-beijing.maas.aliyuncs.com:8666 \
  -e VW_VISION_BASE_URL=http://ws-fake.cn-beijing.maas.aliyuncs.com:8666/compatible-mode/v1 \
  -e VW_PYTHON=/opt/videoweaver-venv/bin/python \
  -v "$CASE":/opt/videoweaver/case/dataset:ro \
  -v "$FAKE":/opt/vw-run/fake_responses.py:ro \
  -v "$FAKECFG":/opt/codex-home/config.toml:ro \
  videoweaver-task-bailian:arm64-v1 \
  bash -c '
    mkdir -p /tmp/fake-state /opt/videoweaver/generate_materials
    export OUTPUT_DIR=/opt/videoweaver/generate_materials
    export CODEX_THREAD_NAME=debug-session
    python /opt/vw-run/fake_responses.py > /tmp/fake-state/fake-server.out 2>&1 &
    FAKE_PID=$!
    sleep 1
    set +e
    codex exec --skip-git-repo-check --json -C /opt/videoweaver/_codex_workspace \
      --dangerously-bypass-approvals-and-sandbox \
      "执行本任务的第一条生成指令。" > /tmp/fake-state/codex-out.jsonl 2> /tmp/fake-state/codex-err.txt
    RC=$?
    set -e
    kill $FAKE_PID 2>/dev/null || true
    echo "codex exit=$RC"
    echo "=== codex stdout (jsonl) last lines ==="
    tail -20 /tmp/fake-state/codex-out.jsonl
    echo "=== codex stderr ==="
    tail -20 /tmp/fake-state/codex-err.txt
    echo "=== fake state ==="
    cat /tmp/fake-state/state.json 2>/dev/null || echo "(no state)"
    echo "=== generated media ==="
    find /opt/videoweaver/generate_materials -type f 2>/dev/null | head -20
    echo "=== find firstframe jpg anywhere ==="
    find / -name "shot*_firstframe.jpg" -not -path "/proc/*" 2>/dev/null | head -10
    echo "=== find videos dir ==="
    find / -type d -name "videos" -not -path "/proc/*" 2>/dev/null | head
    echo "=== marker check ==="
    ls -la /tmp/marker.txt 2>/dev/null || echo NO_MARKER
    cat /tmp/marker.txt 2>/dev/null
    echo "=== fake-server.out ==="
    tail -30 /tmp/fake-state/fake-server.out
  '
