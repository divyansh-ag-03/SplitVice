# ── Stage 1: builder ──────────────────────────────────────────────────────────
# Install all dependencies into a virtual environment so we can copy only
# the installed packages into the final image (keeps the image small).
FROM python:3.12-slim AS builder

WORKDIR /build

# Install build tools needed for some packages (e.g. bcrypt, asyncpg)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency manifest first for better layer caching
COPY pyproject.toml ./

# Create a venv and install runtime dependencies into it
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

RUN pip install --upgrade pip && \
    pip install --no-cache-dir .


# ── Stage 2: final ────────────────────────────────────────────────────────────
# Minimal runtime image — no build tools, no cache
FROM python:3.12-slim AS final

WORKDIR /app

# Runtime system deps (libpq for asyncpg)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Copy the virtual environment from the builder stage
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy application source
COPY alembic.ini ./
COPY migrations/ ./migrations/
COPY app/ ./app/

# Non-root user for security
RUN useradd --no-create-home --shell /bin/false appuser && \
    chown -R appuser:appuser /app
USER appuser

# Expose the application port
EXPOSE 8000

# Run migrations then start the server
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
