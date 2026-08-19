# syntax=docker/dockerfile:1

FROM python:3.11-slim

# Prevent Python from writing bytecode and buffering stdout
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Hard-coded Neo4j service URL for Docker virtual network.
# Credentials (NEO4J_USER, NEO4J_PASSWORD, NEO4J_DATABASE) must be passed at runtime.
ENV NEO4J_URI=bolt://neo4j:7687

WORKDIR /app

# Install build dependencies first
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy build files
COPY pyproject.toml README.md ./
COPY src/ ./src/

# Install the package so both `panoramix` and `panoramix-mcp` are available
RUN pip install --no-cache-dir .

# Default to running the MCP server; override with `panoramix` for the CLI
ENTRYPOINT ["panoramix-mcp"]
