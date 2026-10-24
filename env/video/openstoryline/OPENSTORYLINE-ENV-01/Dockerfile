FROM video-common-base:arm64-v1

ENV VIRTUAL_ENV=/opt/openstoryline-venv \
    PATH=/opt/openstoryline-venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN printf '%s\n' 'export PATH=/opt/openstoryline-venv/bin:$PATH' > /etc/profile.d/openstoryline-venv.sh && \
    python3 -m venv "$VIRTUAL_ENV"
COPY requirements.in /tmp/requirements.in
# torch/torchaudio come from the official CPU-only index: the generic PyPI
# Linux wheels drag in multi-GB CUDA runtime packages (cudnn 433MB+,
# cuda-toolkit extras) that a CPU-only arm64 environment never uses.
# torch==2.11.0+cpu satisfies the ==2.11.0 pin (PEP 440 local version).
RUN "$VIRTUAL_ENV/bin/python" -m pip install --no-cache-dir \
        --index-url https://download.pytorch.org/whl/cpu \
        torch==2.11.0 torchaudio==2.11.0 && \
    "$VIRTUAL_ENV/bin/python" -m pip install --no-cache-dir \
        -i https://pypi.tuna.tsinghua.edu.cn/simple \
        -r /tmp/requirements.in && \
    "$VIRTUAL_ENV/bin/python" -m pip freeze > /opt/openstoryline-freeze.txt

COPY source/ /opt/openstoryline/
WORKDIR /workspace
ENV PYTHONPATH=/opt/openstoryline/src:/opt/openstoryline

# Verify both ordinary and login shells resolve the same task interpreter.
RUN python3 -c 'import sys; assert sys.prefix == "/opt/openstoryline-venv"; import torch, torchaudio, funasr, langchain_openai, mcp, av, moviepy; print(sys.executable, torch.__version__, torchaudio.__version__)' && \
    bash -lc 'python3 -c "import sys; assert sys.prefix == \"/opt/openstoryline-venv\"; import requests, torch, funasr"' && \
    ffmpeg -hide_banner -encoders 2>/dev/null | grep -q libx264 && \
    ffmpeg -hide_banner -encoders 2>/dev/null | grep -q aac

CMD ["python3", "/opt/openstoryline/openstoryline_task_entry.py"]
