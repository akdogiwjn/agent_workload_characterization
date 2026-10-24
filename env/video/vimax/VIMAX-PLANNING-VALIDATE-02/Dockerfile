FROM vimax-task-bailian:arm64-v5-callback-fixes-02

# Code-only offline derivative. No package installation or model/API assets.
COPY adapter-src/ /opt/vimax/src/
USER root
RUN find /opt/vimax/src -name '__pycache__' -type d -prune -exec rm -rf {} + \
    && true
USER vimax
RUN cd /opt/vimax/src \
    && python3 -B -c "import agent_runtime.vimax_adapters, agent_runtime.request_ledger, utils.control_exceptions, utils.robust_json_parser, agents.storyboard_artist"

WORKDIR /workspace
USER vimax
CMD ["python3"]
