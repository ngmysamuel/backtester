######
# First phase
######
FROM python:3.12-slim as builder

# Create a "folder" for the project inside the container.
WORKDIR /app

# Install system deps
RUN apt-get update && apt-get install -y build-essential curl && rm -rf /var/lib/apt/lists/*

# Install Poetry
RUN pip install poetry

RUN poetry config virtualenvs.create false

# Create the a virtual environment at the same path we will be using later on
RUN python -m venv /opt/venv

# Add it to the path
ENV PATH="/opt/venv/bin:$PATH"
ENV VIRTUAL_ENV=/opt/venv/

# 1. Copy config files
COPY pyproject.toml poetry.lock* .

# 2. Install Dependencies (Libraries only)
RUN poetry install --no-root --no-interaction --no-ansi

# 3. Copy source code
COPY . .

# 4. Install current project
RUN poetry install --no-interaction --no-ansi

######
# Second phase
######
FROM python:3.12-slim

WORKDIR /app

# Slimmed down version of what's needed
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

# Bring the environment over
COPY --from=builder /opt/venv /opt/venv

# Run without having to prefix with "poetry run"
ENV PATH="/opt/venv/bin:$PATH"

COPY . .