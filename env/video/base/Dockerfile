# VIDEO-USE-ENV-01: video common base image (linux/arm64, native build)
#
# Pinned identity (LOCAL arm64 image, no re-pull; digest verified on this host):
#   tag python:3.12-slim  image ID sha256:ce9a404c2c0138e747a43e6ea022d2f7e670ed868df35d627a663ba7fb940ea9
#   repo digest python@sha256:05cda9777409a9c3ffddd94a4c476b79f0769a0b4857f0c7ed9226b6800b0d6f
# Shared layer for the four video repos (video-use, OpenStoryline, ViMax,
# VideoWeaver): FFmpeg/ffprobe media engine + base process tools only.
# Repo-specific Python dependencies are NOT installed here; every task image
# owns an isolated venv. No credentials, host configs or media are copied in.
FROM python:3.12-slim@sha256:05cda9777409a9c3ffddd94a4c476b79f0769a0b4857f0c7ed9226b6800b0d6f

RUN sed -i 's|deb.debian.org|mirrors.aliyun.com|g' /etc/apt/sources.list.d/debian.sources \
    && apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg procps ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Build-time encoder verification (not just "command exists"): the CPU paths
# used by video-use (libx264 video + aac audio) must be real encoders.
RUN ffmpeg -hide_banner -encoders 2>/dev/null | grep -q ' libx264 ' \
    && ffmpeg -hide_banner -encoders 2>/dev/null | grep -q ' aac ' \
    && ffmpeg -version | head -1 > /etc/video-common-base.txt \
    && ffprobe -version | head -1 >> /etc/video-common-base.txt \
    && cat /etc/video-common-base.txt
