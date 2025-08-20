# Builds and runs `API` backend.
FROM python:3.12
WORKDIR /app

# Install Poetry
RUN curl -sSL https://install.python-poetry.org | python3 - \
    && ln -s $HOME/.local/bin/poetry /usr/local/bin/poetry

# Copy project files
COPY . .

# Install dependencies and project
RUN poetry config virtualenvs.create false \
    && poetry install --extras server --no-root

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--reload"]
