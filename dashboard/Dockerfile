# jobhunt dashboard: one image for the app (portal) and the sync worker.
FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/src

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY src/ src/

RUN useradd --system --uid 10001 jobhunt
USER jobhunt

EXPOSE 4110
CMD ["python", "-m", "uvicorn", "jobhunt.web.app:app", "--host", "0.0.0.0", "--port", "4110", "--no-server-header", "--no-access-log"]
