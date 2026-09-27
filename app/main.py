"""
docker-vps-starter — a tiny Flask app that proves a multi-container stack works.

Every time someone opens "/", the app:
  1. increments a total visit counter stored in Redis (another container), and
  2. records which app container answered (useful when you scale to 3 copies).

Because the counter lives in Redis (with a Docker volume), it survives
container restarts, rebuilds and server reboots.
"""

import os
import platform
import socket
import time
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import redis
from flask import Flask, jsonify, render_template

STARTED_AT = time.time()
VISITS_KEY = "visits:total"
HITS_KEY = "visits:by_container"


def _timezone():
    """Use the TZ environment variable (set in .env), fall back to UTC."""
    try:
        return ZoneInfo(os.environ.get("TZ", "UTC"))
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("UTC")


def _uptime(seconds):
    seconds = int(seconds)
    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    if days:
        return f"{days}d {hours}h {minutes}m"
    if hours:
        return f"{hours}h {minutes}m"
    return f"{minutes}m {seconds}s"


def create_app(redis_client=None):
    """Application factory. Gunicorn calls this: gunicorn "main:create_app()"."""
    app = Flask(__name__)

    # "redis" is not a hostname on the internet: Docker Compose gives every
    # service a DNS name on its network, so the app finds Redis by service name.
    r = redis_client or redis.Redis(
        host=os.environ.get("REDIS_HOST", "redis"),
        port=int(os.environ.get("REDIS_PORT", "6379")),
        decode_responses=True,
        socket_connect_timeout=2,
        socket_timeout=2,
    )
    hostname = socket.gethostname()  # inside Docker this is the container ID
    title = os.environ.get("APP_TITLE", "Docker VPS Starter")

    def collect_stats(count_visit):
        stats = {
            "title": title,
            "container": hostname,
            "python": platform.python_version(),
            "uptime": _uptime(time.time() - STARTED_AT),
            "time": datetime.now(_timezone()).strftime("%Y-%m-%d %H:%M:%S %Z"),
            "redis": "up",
            "visits": None,
            "by_container": {},
        }
        try:
            if count_visit:
                pipe = r.pipeline()
                pipe.incr(VISITS_KEY)
                pipe.hincrby(HITS_KEY, hostname, 1)
                stats["visits"] = pipe.execute()[0]
            else:
                stats["visits"] = int(r.get(VISITS_KEY) or 0)
            hits = r.hgetall(HITS_KEY)
            stats["by_container"] = dict(
                sorted(((k, int(v)) for k, v in hits.items()), key=lambda kv: -kv[1])
            )
        except redis.exceptions.RedisError:
            # The page still loads if Redis is down; it just says so.
            stats["redis"] = "down"
        return stats

    @app.get("/")
    def index():
        return render_template("index.html", s=collect_stats(count_visit=True))

    @app.get("/api/stats")
    def api_stats():
        return jsonify(collect_stats(count_visit=False))

    @app.get("/health")
    def health():
        # Used by Docker's healthcheck. It answers "is the web process alive?".
        # Redis has its own healthcheck in compose.yaml.
        try:
            redis_ok = bool(r.ping())
        except redis.exceptions.RedisError:
            redis_ok = False
        return jsonify(status="ok", redis="up" if redis_ok else "down")

    return app
