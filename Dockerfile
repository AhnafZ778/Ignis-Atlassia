# The image rebuilds authored frontend source; local generated output is excluded.
FROM node:22-bookworm-slim AS frontend
WORKDIR /app/studio-app
COPY studio-app/package.json studio-app/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY studio-app/ ./
COPY fireatlas/studio/audience_templates.json /app/fireatlas/studio/audience_templates.json
COPY studio-render/camera.mjs studio-render/camera.d.mts /app/studio-render/
RUN npm run build

FROM python:3.12-slim-bookworm AS runtime
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PYDANTIC_AI_NO_BANNER=1 \
    FIREATLAS_DATA_DIR=/tmp/fireatlas PORT=10000
WORKDIR /app
# Node and its installed native helpers are required for native board export.
COPY --from=frontend /usr/local/bin/node /usr/local/bin/node
COPY pyproject.toml README.md ./
COPY earth.html Globe.html ./
COPY docs/DATA.md docs/AI_USE.md docs/NATIVE_MASK_VALIDATION.md docs/NASA_DATA_IMPORT.md docs/
COPY requirements/ requirements/
COPY fireatlas/ fireatlas/
COPY --from=frontend /app/fireatlas/static/studio-assets/ fireatlas/static/studio-assets/
COPY --from=frontend /app/studio-app/node_modules/ studio-app/node_modules/
COPY --from=frontend /app/studio-app/scripts/ studio-app/scripts/
COPY deployment/ deployment/
RUN pip install --no-cache-dir -r requirements/assistant.lock .
# Small public Park sources support the existing welcome/example workflow.
COPY site/data/park-platforms/v1/ site/data/park-platforms/v1/
COPY site/data/replay/cases/park-2024.json.gz site/data/replay/cases/
EXPOSE 10000
CMD ["python", "-m", "fireatlas.hosted"]
