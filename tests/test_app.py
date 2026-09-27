"""
Unit tests for the Flask app. They use a tiny in-memory stand-in for Redis,
so they run without Docker:

    pip install -r app/requirements.txt
    python -m unittest discover -s tests -v
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import redis  # noqa: E402

from main import create_app  # noqa: E402


class FakeRedis:
    """Just enough of the redis-py API for this app, kept in memory."""

    def __init__(self):
        self.data, self.hashes = {}, {}

    def ping(self):
        return True

    def get(self, key):
        return self.data.get(key)

    def incr(self, key):
        self.data[key] = str(int(self.data.get(key, 0)) + 1)
        return int(self.data[key])

    def hincrby(self, key, field, amount=1):
        h = self.hashes.setdefault(key, {})
        h[field] = str(int(h.get(field, 0)) + amount)
        return int(h[field])

    def hgetall(self, key):
        return dict(self.hashes.get(key, {}))

    def pipeline(self):
        return FakePipeline(self)


class FakePipeline:
    """Queues commands and runs them all on execute(), like redis-py."""

    def __init__(self, backend):
        self.backend, self.queue = backend, []

    def incr(self, *args):
        self.queue.append((self.backend.incr, args))

    def hincrby(self, *args):
        self.queue.append((self.backend.hincrby, args))

    def execute(self):
        return [fn(*args) for fn, args in self.queue]


class BrokenRedis(FakeRedis):
    """Simulates Redis being down: every command raises ConnectionError."""

    def _down(self, *args, **kwargs):
        raise redis.exceptions.ConnectionError("redis is down")

    ping = get = incr = hincrby = hgetall = _down


class AppTests(unittest.TestCase):
    def setUp(self):
        self.fake = FakeRedis()
        self.client = create_app(redis_client=self.fake).test_client()

    def test_index_counts_visits(self):
        self.assertIn(b'<div class="count">1</div>', self.client.get("/").data)
        self.assertIn(b'<div class="count">2</div>', self.client.get("/").data)
        self.assertEqual(self.fake.get("visits:total"), "2")

    def test_stats_endpoint_does_not_count(self):
        self.client.get("/")
        for _ in range(3):
            stats = self.client.get("/api/stats").get_json()
        self.assertEqual(stats["visits"], 1)
        self.assertEqual(stats["redis"], "up")
        self.assertEqual(sum(stats["by_container"].values()), 1)

    def test_health(self):
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json(), {"status": "ok", "redis": "up"})

    def test_page_still_works_when_redis_is_down(self):
        client = create_app(redis_client=BrokenRedis()).test_client()
        resp = client.get("/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Redis is not reachable", resp.data)
        self.assertEqual(client.get("/health").get_json()["redis"], "down")
        self.assertEqual(client.get("/api/stats").get_json()["redis"], "down")

    def test_bad_timezone_falls_back_to_utc(self):
        old = os.environ.get("TZ")
        os.environ["TZ"] = "Not/AZone"
        try:
            stats = self.client.get("/api/stats").get_json()
        finally:
            if old is None:
                os.environ.pop("TZ", None)
            else:
                os.environ["TZ"] = old
        self.assertTrue(stats["time"].endswith("UTC"), stats["time"])


if __name__ == "__main__":
    unittest.main()
