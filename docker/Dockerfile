FROM python:3.11-slim

WORKDIR /app

# System deps for psycopg2 + selenium
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev chromium chromium-driver \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
COPY web/ ./web/

ENV PYTHONUNBUFFERED=1
ENV APP_PORT=8000

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]