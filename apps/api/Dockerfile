FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml .
RUN pip install --no-cache-dir fastapi==0.115.6 uvicorn==0.34.0 httpx==0.28.1 pydantic==2.10.4
COPY apps/api/verityforge ./verityforge
RUN useradd -u 10001 app
USER app
CMD ["uvicorn", "verityforge.main:app", "--host", "0.0.0.0", "--port", "8000"]
