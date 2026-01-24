FROM python:3.12-slim

# Creates a clean "folder" for the project inside the container.
WORKDIR /app

# Install system deps
RUN apt-get update && apt-get install -y build-essential curl && rm -rf /var/lib/apt/lists/*

# Install Poetry
RUN pip install poetry
RUN poetry config virtualenvs.create false

# 1. Copy config files
COPY pyproject.toml poetry.lock* .

RUN ls
RUN pwd

# 2. Install Dependencies (Libraries only)
RUN poetry install --no-root --no-interaction --no-ansi

# 3. Copy source code
COPY . .

RUN ls
RUN pwd

# 4. Install current project
RUN poetry install --no-interaction --no-ansi