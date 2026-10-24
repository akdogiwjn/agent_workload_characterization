# VIDEO-WEAVER-ENV-01: VideoWeaver task image (derived from video-common-base).
# From the registered public base image ONLY; no new base pull.
# Includes: fixed source copy, isolated venv with the minimal frozen deps,
# and the official Codex CLI 0.163.0 static arm64 musl binary from the local
# verified tarball (SHA-256 a7261e65f4a96d8f4ca65a069c6cf2dc2c33defc341e48078acefda9461fffe4).
# No credentials, host configs, media, dataset cases or other repos are baked in.
FROM video-common-base:arm64-v1

RUN python -m venv /opt/videoweaver-venv
ENV PATH="/opt/videoweaver-venv/bin:$PATH" \
    IMAGEIO_FFMPEG_EXE=/usr/bin/ffmpeg
# Login-shell (bash -lc, Codex exec_command) wiring: Debian /etc/profile resets
# PATH to system dirs, so re-export the venv first at the END of /etc/profile
# (video-use codex-bailian-integration-02 verified pattern).
RUN printf '%s\n' 'export PATH="/opt/videoweaver-venv/bin:$PATH"' >> /etc/profile
COPY build/requirements.txt /tmp/vw-requirements.txt
RUN pip install --no-cache-dir -i https://mirrors.aliyun.com/pypi/simple/ \
        -r /tmp/vw-requirements.txt \
    && rm -f /tmp/vw-requirements.txt

# Codex CLI 0.163.0 static arm64 musl (local verified artifact, not re-downloaded).
COPY build/codex-aarch64-unknown-linux-musl.tar.gz /tmp/codex.tar.gz
RUN tar xzf /tmp/codex.tar.gz -C /tmp \
    && mv /tmp/codex-aarch64-unknown-linux-musl /usr/local/bin/codex \
    && chmod +x /usr/local/bin/codex \
    && rm -f /tmp/codex.tar.gz \
    && codex --version

# Container-scoped CODEX_HOME with the explicit Bailian provider config.
ENV CODEX_HOME=/opt/codex-home
COPY build/codex-config.toml /opt/codex-home/config.toml
RUN mkdir -p /opt/codex-home/sessions

# Fixed VideoWeaver source copy (isolated adaptation; reference repo untouched).
COPY source/ /opt/videoweaver/
RUN mkdir -p /opt/videoweaver/_codex_workspace

# Build-time verification of the resolved environment.
RUN python -c "import requests, httpx, PIL, cv2, numpy, tqdm, yaml, imageio_ffmpeg; print('videoweaver deps import OK')" \
    && ffmpeg -hide_banner -encoders 2>/dev/null | grep -q ' libx264 ' \
    && echo "ffmpeg encoders OK"

WORKDIR /opt/videoweaver
