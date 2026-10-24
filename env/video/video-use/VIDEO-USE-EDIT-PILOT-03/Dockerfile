# Offline project-owned helper overlay. No dependency, Codex, or model changes.
FROM video-use-task:arm64-codex-bailian-v2

COPY overlay/helpers/render.py /opt/video-use/helpers/render.py
COPY overlay/helpers/timeline_view.py /opt/video-use/helpers/timeline_view.py
COPY overlay/SKILL.md /opt/video-use/SKILL.md
COPY validation/synthetic_validation.py /opt/pilot03-checks/synthetic_validation.py

RUN python3 -m py_compile /opt/video-use/helpers/render.py \
    /opt/video-use/helpers/timeline_view.py \
    /opt/pilot03-checks/synthetic_validation.py \
    && test -L /root/.codex/skills/video-use \
    && test "$(readlink -f /root/.codex/skills/video-use)" = /opt/video-use

WORKDIR /workspace
