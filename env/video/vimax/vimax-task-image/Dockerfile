# ViMax Bailian task image (independent tag; never overwrites history).
# Base: registered video-common-base:arm64-v1
#   sha256:d414b4270fec6ec2dd245982a522099d8941d8cd114ccd5ec2c6730815f3a706
# Source: adapter-src (ViMax fd4b72e7731be6e5f88486206d25ea59849b0285 + Bailian
#         adaptation patches, see adapter-src/ADAPTATION-DIFF.md)
# Lockfile: uv.lock installed verbatim with `uv sync --locked --no-dev`
#           (pinned uv version; Tsinghua PyPI mirror for download speed)
# Build context is whitelisted via .dockerignore: ONLY adapter-src/ may enter.
# No credentials, no .env, no data/, no other repos, no caches are copied.
FROM video-common-base:arm64-v1

RUN pip3 install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple uv==0.9.7

WORKDIR /opt/vimax/src
COPY vimax-task-image/requirements.txt /opt/vimax/requirements.txt
COPY adapter-src/ /opt/vimax/src/

# Dependency installation (registered deviation from `uv sync --locked`):
# uv downloads wheels from the pypi.org URLs recorded in uv.lock and
# files.pythonhosted.org is unreachable from this host (hangs); pip honors
# the mirror index for BOTH metadata and wheel downloads. Versions are still
# pinned EXACTLY by exporting uv.lock with `uv export --frozen` (see
# vimax-task-image/requirements.txt, generated from the verbatim lockfile).
RUN pip3 install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple \
      -r /opt/vimax/requirements.txt

ENV PATH="/usr/local/bin:${PATH}" \
    PYTHONDONTWRITEBYTECODE=1 \
    VIMAX_BAILIAN_EVENT_LOG=/workspace/events/bailian-events.jsonl

# Interpreter sanity is verified for plain shell, bash -lc and the ViMax tool
# shell inside the network-gated validation; the venv python is first on PATH
# in all of them via the absolute PATH above.
RUN useradd --uid 2000 --create-home vimax \
    && mkdir -p /workspace \
    && chown -R vimax:vimax /workspace \
    && python3 -c "import sys; assert sys.executable == '/usr/local/bin/python3'" \
    && cd /opt/vimax/src && python3 -c "import agent_runtime, pipelines, tools, agents, interfaces, utils; import tools.image_generator_bailian_api, tools.video_generator_bailian_api" \
    && cd /opt/vimax/src && python3 -c "import PIL, moviepy, langchain, aiohttp; print('deps ok')" \
    && ffmpeg -version | head -1

WORKDIR /workspace
USER vimax
CMD ["python3"]
