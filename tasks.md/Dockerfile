# syntax=docker/dockerfile:1
# tasks.md — self-hosted, markdown-based task board
# https://github.com/BaldissaraMatheus/Tasks.md
#
# Differences vs. the upstream Dockerfile (deliberate):
#   - Frontend is built HERE at image build time, not at container startup
#     (upstream runs `npm run build` in entrypoint.sh on every start/restart).
#   - Runtime stage is the same node image — no `apk add nodejs` second runtime.
#   - Stacks-Editor comes in via `git clone --recurse-submodules` instead of
#     a separate mid-build clone.
#   - Pinned to an official release tag (REPO_REF), not main.
#
# Build:            docker build -t tasks-md:latest .
# Upgrade release:  docker build --build-arg REPO_REF=<tag> -t tasks-md:latest .
# Subpath proxy:    docker build --build-arg BASE_PATH=/tasks -t tasks-md:latest .
#                   (BASE_PATH is fixed at build time; PWA requires "/")

ARG NODE_IMAGE=node:20-alpine
ARG REPO_REF=3.3.0
ARG BASE_PATH=/

# ---------------------------------------------------------------------------
# Build stage — clone pinned release, install deps, build frontend
# ---------------------------------------------------------------------------
FROM ${NODE_IMAGE} AS build
# Re-declare: ARGs declared before FROM are global-only (FROM instructions);
# without this, ${REPO_REF}/${BASE_PATH} expand to empty inside the stage.
ARG REPO_REF
ARG BASE_PATH
RUN apk add --no-cache git
WORKDIR /src
RUN git clone --depth 1 --recurse-submodules --shallow-submodules --branch ${REPO_REF} \
      https://github.com/BaldissaraMatheus/Tasks.md .
WORKDIR /src/frontend
RUN npm ci --no-audit
RUN npm run build -- --base=${BASE_PATH}
WORKDIR /src/backend
RUN npm ci --no-audit

# ---------------------------------------------------------------------------
# Runtime stage — prebuilt static frontend + Koa backend, starts in ~1s
# ---------------------------------------------------------------------------
FROM ${NODE_IMAGE}

# Entrypoint inlined (single-file image): dir setup, default custom.css,
# CSS sync between config/ and static/, ownership, start server.
COPY <<'ENTRYPOINT' /entrypoint.sh
#!/bin/sh
set -e

TASKS_DIR=/tasks
CONFIG_DIR=/config
export TASKS_DIR CONFIG_DIR

mkdir -p "${TASKS_DIR}" "${CONFIG_DIR}/stylesheets" "${CONFIG_DIR}/images" "${CONFIG_DIR}/sort"

# Default custom CSS (first start only)
if [ ! -f "${CONFIG_DIR}/stylesheets/custom.css" ]; then
  echo "@import url(${BASE_PATH}/stylesheets/color-themes/adwaita.css)" > "${CONFIG_DIR}/stylesheets/custom.css"
fi

# Serve user CSS from config/, keep built-in themes available in config/
cp -r "${CONFIG_DIR}/stylesheets/." /api/static/stylesheets/
cp -r /api/static/stylesheets/. "${CONFIG_DIR}/stylesheets/"

if [ -n "${PUID}" ] || [ -n "${PGID}" ]; then
  chown -R "${PUID}:${PGID}" "${CONFIG_DIR}" "${TASKS_DIR}"
fi

cd /api
exec node server.js
ENTRYPOINT
RUN chmod +x /entrypoint.sh

COPY --from=build /src/frontend/dist /api/static
COPY --from=build /src/backend /api

WORKDIR /api
EXPOSE 8080
ENTRYPOINT ["/entrypoint.sh"]
