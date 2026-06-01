# Combined single-service image for the DSA Code Visualizer.
#
# One container runs the FastAPI backend AND serves the built React SPA, so the
# whole app lives at a single origin (no CORS to configure for the web app).
#
# Build from the REPO ROOT:  docker build -t code-viz .
# (The old packages/backend/Dockerfile assumed a narrower context and is kept
#  only for reference — this is the file Render builds.)

# ---------------------------------------------------------------------------
# Stage 1 — build the frontend (Vite) into static assets.
# ---------------------------------------------------------------------------
FROM node:20-slim AS web
WORKDIR /repo

# Install workspace deps against the lockfile. Copying the manifests first lets
# Docker cache `npm ci` across source-only changes.
COPY package.json package-lock.json ./
COPY packages ./packages
RUN npm ci

# Build in dependency order: schema -> core -> web-app. npm runs workspaces in
# the order given on the CLI, which matches the import graph.
RUN npm run build \
    --workspace=@dsa-viz/trace-schema \
    --workspace=@dsa-viz/visualizer-core \
    --workspace=@dsa-viz/web-app

# ---------------------------------------------------------------------------
# Stage 2 — Python backend + language toolchains, serving the built SPA.
# ---------------------------------------------------------------------------
FROM python:3.11-slim

# Toolchains the tracers shell out to at runtime:
#   g++/gdb -> C++ tracing,  nodejs -> JavaScript tracing.
# Java tracing intentionally stays unavailable (a JDK would balloon the image);
# the /trace route returns 501 for Java by design.
RUN apt-get update && apt-get install -y --no-install-recommends \
        g++ gdb nodejs \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install the four local tracer packages BEFORE the backend. The backend depends
# on dsa-tracer{,-cpp,-js,-java} by name; installing them first means pip finds
# them already satisfied instead of trying (and failing) to fetch from PyPI.
COPY packages/tracer-python /app/tracer-python
COPY packages/tracer-cpp    /app/tracer-cpp
COPY packages/tracer-js     /app/tracer-js
COPY packages/tracer-java   /app/tracer-java
COPY packages/backend       /app/backend

RUN pip install --no-cache-dir /app/tracer-python \
 && pip install --no-cache-dir /app/tracer-cpp \
 && pip install --no-cache-dir /app/tracer-js \
 && pip install --no-cache-dir /app/tracer-java \
 && pip install --no-cache-dir /app/backend

# Bring in the compiled SPA and tell the app where to find it.
COPY --from=web /repo/packages/web-app/dist /app/static
ENV STATIC_DIR=/app/static

# Drop privileges — this process compiles and runs untrusted user code.
RUN useradd -m runner
USER runner

# Render (and most PaaS) inject $PORT; default to 8000 for local runs.
EXPOSE 8000
CMD ["sh", "-c", "uvicorn server.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
