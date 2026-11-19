# Operation Snowfall v2.9.1: Discord worker (no public HTTP listener).
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src/ ./src/
RUN python -m pip install --no-cache-dir .
# Attach a Railway volume at /data. The entry point refuses ephemeral storage.
CMD ["python", "-m", "snowfall.railway"]
