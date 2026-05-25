FROM python:3.11-slim

# C++ toolchain for tracer-cpp (kept minimal).
RUN apt-get update && apt-get install -y --no-install-recommends \
    g++ gdb && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install our own packages first so that layer caching is effective.
COPY ../tracer-python /app/tracer-python
COPY ../tracer-cpp    /app/tracer-cpp
COPY .                /app/backend

RUN pip install --no-cache-dir /app/tracer-python && \
    pip install --no-cache-dir /app/tracer-cpp || true && \
    pip install --no-cache-dir /app/backend

# Drop privileges.
RUN useradd -m runner
USER runner

EXPOSE 8000
CMD ["uvicorn", "server.main:app", "--host", "0.0.0.0", "--port", "8000"]
