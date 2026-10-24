FROM video-common-base:arm64-v1
RUN python3 -m pip install --no-cache-dir \
        -i https://pypi.tuna.tsinghua.edu.cn/simple \
        "numpy<3" "scikit-image>=0.22,<1.0" "scipy>=1.10"
COPY judge.py /tests/judge.py
COPY gt-cuts.json /tests/cuts.json
ENTRYPOINT ["python3", "/tests/judge.py"]
