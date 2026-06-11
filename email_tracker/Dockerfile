# Inbox Tracker — read-only deal tracker + to-do dashboard.
# Build from the repo root:  docker build -f email_tracker/Dockerfile -t inbox-tracker .
FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY email_tracker/ ./email_tracker/
WORKDIR /app/email_tracker

# Defaults — override at runtime (ANTHROPIC_API_KEY, EMAIL_SOURCE, etc.)
ENV PORT=5000 \
    EMAIL_SOURCE=sample \
    POLL_INTERVAL=30 \
    TRACKER_DB=/data/tracker.db \
    GRAPH_TOKEN_CACHE=/data/.graph_token_cache.json

# /data is a volume so the tracker DB and Outlook token cache survive restarts.
VOLUME ["/data"]
EXPOSE 5000

# Single worker so the background poller is a singleton; threads handle the
# (light) concurrent browser/API requests. create_app() starts the poller.
CMD ["sh", "-c", "gunicorn -w 1 --threads 8 -b 0.0.0.0:${PORT} 'app:create_app()'"]
