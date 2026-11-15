# One image runs the API + UI (gunicorn), the alerter and the responder; compose picks the command.
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY backend/requirements.txt ./reqs/backend.txt
COPY oncall/requirements.txt ./reqs/oncall.txt
RUN pip install -r reqs/backend.txt -r reqs/oncall.txt
COPY backend/ ./backend/
COPY frontend/ ./frontend/
COPY oncall/ ./oncall/
COPY ops/ ./ops/
COPY openapi.yaml ./
RUN useradd --create-home --uid 10001 app && mkdir -p /app/data && chown -R app /app
USER app
ENV PYTHONPATH=/app:/app/backend FRONTEND_DIR=/app/frontend PORT=8000
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --retries=5 CMD python -c "import urllib.request,os;urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('PORT','8000')+'/health')"
WORKDIR /app/backend
CMD ["sh", "-c", "gunicorn wsgi:app --bind 0.0.0.0:${PORT} --workers 2 --threads 4 --access-logfile -"]
