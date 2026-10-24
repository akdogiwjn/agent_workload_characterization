# VIDEO-USE-CODEX-BAILIAN-INTEGRATION-01 task image (derived from the
# registered video-use task image). Installs the FIXED official Codex CLI
# 0.163.0 arm64 musl binary (GitHub release rust-v0.163.0, sha256 registered
# in image-manifest.json) with a container-scoped CODEX_HOME and explicit
# Bailian provider config. No Node needed (static musl binary). No
# credentials, host configs or media baked in.
FROM video-use-task:arm64-v1

COPY build/codex-aarch64-unknown-linux-musl.tar.gz /tmp/codex.tar.gz
RUN tar xzf /tmp/codex.tar.gz -C /tmp \
    && mv /tmp/codex-aarch64-unknown-linux-musl /usr/local/bin/codex \
    && chmod +x /usr/local/bin/codex \
    && rm -f /tmp/codex.tar.gz \
    && codex --version

# Container-scoped CODEX_HOME with the explicit Bailian provider config
ENV CODEX_HOME=/opt/codex-home
COPY config.toml /opt/codex-home/config.toml
RUN mkdir -p /opt/codex-home/skills \
    && ln -sfn /opt/video-use /opt/codex-home/skills/video-use \
    && mkdir -p /task

WORKDIR /task
