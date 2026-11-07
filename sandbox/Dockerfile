# Execution sandbox image: Python + pytest preinstalled, because the sandbox runs with --network none
# (nothing can be pip-installed at run time). Build:  docker build -t verityforge-sandbox sandbox/
# Use:  VERITYFORGE_SANDBOX_IMAGE=verityforge-sandbox
FROM python:3.12-slim
RUN pip install --no-cache-dir pytest==8.3.4
# Run as an unprivileged user; the runtime also passes --user 65534 and --read-only.
USER 65534:65534
WORKDIR /workspace
