FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir .

RUN useradd --create-home appuser \
    && mkdir -p /home/appuser/.cache/fastembed \
    && chown -R appuser:appuser /home/appuser/.cache
USER appuser

EXPOSE 8002
CMD ["uvicorn", "retrieval_service.main:app", "--host", "0.0.0.0", "--port", "8002"]
