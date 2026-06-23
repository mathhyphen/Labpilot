# LabPilot Dockerfile.
#
# Best-practice image:
#   * Non-root runtime user (labpilot).
#   * Dependency layer cached on pyproject.toml/README only — editing
#     *.py does NOT re-resolve dependencies.
#   * Non-editable production install (no [dev] extras, no -e).
#   * HEALTHCHECK polls the FastAPI root endpoint.

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    LABPILOT_DB_PATH=/data/labpilot.db \
    # api/ is a namespace package (no __init__.py) and is not picked up
    # by setuptools' package finder, so it is not installed into
    # site-packages. Keeping the source tree on PYTHONPATH lets both
    # `api.main` and the package-shipped config.yaml resolve at runtime
    # under a non-editable install.
    PYTHONPATH=/app/labpilot

WORKDIR /app

# sqlite3 CLI: ad-hoc DB inspection. git: snapshot support.
RUN apt-get update \
    && apt-get install -y --no-install-recommends sqlite3 git \
    && rm -rf /var/lib/apt/lists/*

# --- Dependency layer (cached unless pyproject.toml / README change) ---
# Copy only build metadata. A throwaway package stub lets `pip install .`
# build a wheel and resolve [project].dependencies without the real
# source, so source edits never invalidate the dependency layer.
COPY pyproject.toml README.md ./
RUN mkdir -p labpilot/labpilot \
    && touch labpilot/labpilot/__init__.py \
    && pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir .

# --- Source layer ---
COPY labpilot/ ./labpilot/

# Non-editable production install of the real package. Dependencies are
# already satisfied above; --no-deps keeps this layer fast and bound to
# source changes only.
RUN pip install --no-cache-dir --no-deps --force-reinstall .

# Non-root runtime user. /data holds the persistent SQLite database.
RUN useradd --create-home --shell /bin/bash labpilot \
    && mkdir -p /data \
    && chown -R labpilot:labpilot /app /data
USER labpilot

VOLUME ["/data"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen(chr(104)+chr(116)+chr(116)+chr(112)+chr(58)+chr(47)+chr(47)+chr(108)+chr(111)+chr(99)+chr(97)+chr(108)+chr(104)+chr(111)+chr(115)+chr(116)+chr(58)+chr(56)+chr(48)+chr(48)+chr(48)+chr(47)).status==200 else 1)"

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
