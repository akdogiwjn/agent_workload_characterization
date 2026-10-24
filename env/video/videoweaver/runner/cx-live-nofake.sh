#!/usr/bin/env bash
# Counter-example 1: live branch must NOT load fake services/config by itself.
set -euo pipefail
ROOT=/home/lcq/agent_workload_characterization
cd "$ROOT"
# 1) live config with NO injection -> use_fake_upstream must be False
OUT=$(python3 - <<'PY'
import sys
sys.path.insert(0,"env/video/videoweaver/runner")
import os
os.environ.pop("VW_LIVE_FAKE_TRANSPORT",None)
import host_runner as hr
cfg=hr.load_config("env/video/videoweaver/runner/offline-config.json","live")
print("use_fake_upstream=%s" % cfg.get("use_fake_upstream"))
print("gateway_upstream=%s" % cfg.get("gateway_upstream"))
print("network=%s" % cfg.get("network"))
PY
)
echo "$OUT"
echo "$OUT" | grep -q "use_fake_upstream=False" || { echo "FAIL: live loads fake"; exit 1; }
# 2) production codex config must not contain a fake domain
grep -q "ws-fake\|127.0.0.1:8666" env/video/videoweaver/runner/production-codex-config.toml \
  && { echo "FAIL: config has fake"; exit 1; }
echo "CX-LIVE-NOFAKE PASS"
