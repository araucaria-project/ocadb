# Builds and runs `API` backend.
# Uses local version of ocadb subproject

# Stage 1: Build Poetry Dependences
FROM python:3.12 AS builder
WORKDIR /app
RUN curl -sSL https://install.python-poetry.org | python3 - \
    && ln -s $HOME/.local/bin/poetry /usr/local/bin/poetry

COPY pyproject.toml poetry.lock* ./
RUN poetry export -f requirements.txt --output requirements.txt --without-hashes --extras server

# Stage 2: Final image
FROM python:3.12
WORKDIR /app
COPY --from=builder /app/requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt
# Copy whole project
COPY . .
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--reload"]
