FROM python:3.12-slim

# Stockfish is installed from Debian; it lands in /usr/games.
RUN apt-get update \
    && apt-get install -y --no-install-recommends stockfish \
    && rm -rf /var/lib/apt/lists/*
ENV PATH="/usr/games:${PATH}"

COPY --from=ghcr.io/astral-sh/uv:0.11.32 /uv /usr/local/bin/uv

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/opt/venv
ENV PATH="/opt/venv/bin:${PATH}"

# Install dependencies first so this layer is cached between code changes.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY README.md LICENSE ./
COPY src ./src
COPY dbt ./dbt
RUN uv sync --frozen --no-dev

# Run as a normal user, not root.
RUN useradd --create-home chessguru && mkdir -p /app/data && chown chessguru /app/data
USER chessguru
VOLUME ["/app/data"]

# The dashboard: docker run -p 8501:8501 -v "$PWD/data:/app/data" chessguru dashboard
ENV STREAMLIT_SERVER_HEADLESS=true
EXPOSE 8501

ENTRYPOINT ["chessguru"]
CMD ["--help"]
