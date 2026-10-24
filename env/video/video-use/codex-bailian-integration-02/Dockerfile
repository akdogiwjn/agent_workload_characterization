# Offline environment-only derivation from the registered Codex + Bailian image.
# Restore the venv PATH after Debian's /etc/profile resets PATH in `bash -lc`.
FROM video-use-task:arm64-codex-bailian-v1

ENV PATH="/opt/video-use-venv/bin:${PATH}"
RUN printf '%s\n' 'export PATH="/opt/video-use-venv/bin:$PATH"' >> /etc/profile

WORKDIR /task
