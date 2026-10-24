# VIDEO-USE-ENV-01: video-use task image (derived from video-common-base).
#
# video-use (upstream https://github.com/browser-use/video-use @ commit
# 43cfc566833548093455c9d4a46bd69913b7e552, staged in source/ — see
# source-manifest.json) is a skill/toolkit, not a standalone agent. The outer
# agent (Codex CLI, project decision 2026-10-21) is NOT installed in this
# image; CLI + model routing are added in a future separately-authorized
# round. No credentials, .env, host config or media are copied in.
FROM video-common-base:arm64-v1

# Isolated venv for this repo only (never shared with other video repos).
RUN python -m venv /opt/video-use-venv
ENV PATH="/opt/video-use-venv/bin:$PATH"
COPY requirements-frozen.txt /tmp/requirements-frozen.txt
RUN pip install --no-cache-dir -i https://mirrors.aliyun.com/pypi/simple/ \
        -r /tmp/requirements-frozen.txt \
    && rm -f /tmp/requirements-frozen.txt

# Source copy (skill + helpers + tests; .git and any .env excluded at staging).
COPY source/ /opt/video-use/

# Register the skill directory for supported outer agents (symlinks only).
RUN mkdir -p /root/.claude/skills /root/.codex/skills \
    && ln -sfn /opt/video-use /root/.claude/skills/video-use \
    && ln -sfn /opt/video-use /root/.codex/skills/video-use

# Build-time import verification of the resolved dependency set.
RUN python -c "import requests, librosa, matplotlib, PIL, numpy; print('video-use deps import OK')"

WORKDIR /task
