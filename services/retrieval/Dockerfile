FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir .

RUN useradd --create-home appuser
USER appuser

EXPOSE 8002
CMD ["uvicorn", "retrieval_service.main:app", "--host", "0.0.0.0", "--port", "8002"]
