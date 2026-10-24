FROM vimax-task-bailian:arm64-v6-planning-fixes-02

# Code-only offline derivative; no dependency or model assets are changed.
COPY adapter-src/ /opt/vimax/src/
USER root
RUN find /opt/vimax/src -name '__pycache__' -type d -prune -exec rm -rf {} + \
    && true
USER vimax
RUN cd /opt/vimax/src \
    && python3 -B -c "import agent_runtime.vimax_adapters, agent_runtime.request_ledger, utils.control_exceptions, utils.robust_json_parser, utils.video_generation_capabilities, agents.storyboard_artist, agents.camera_image_generator, pipelines.script2video_pipeline"

WORKDIR /workspace
USER vimax
CMD ["python3"]
