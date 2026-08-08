"""Locust load test for the /lookup endpoint.

Usage:
    locust -f tests/locustfile.py --headless -u 10 -r 1 --run-time 30s
    locust -f tests/locustfile.py  # opens web UI at http://localhost:8089
"""

import pathlib
from locust import HttpUser, task, between

BASE_URL = "http://0.0.0.0:7860"
URLS_FILE = pathlib.Path(__file__).parent / "1000urls.txt"

# Load test URLs once at import time
with open(URLS_FILE) as f:
    URLS = [line.strip() for line in f if line.strip()]


class LookupUser(HttpUser):
    """Simulate a user randomly querying the /lookup endpoint."""

    host = BASE_URL
    wait_time = between(1, 3)

    @task
    def lookup_random_url(self):
        """Pick a random URL from 1000urls.txt and query /lookup."""
        import random

        url = random.choice(URLS)
        self.client.get(
            "/lookup",
            name="/lookup",
            params={"url": url},
        )

    @task(1)
    def lookup_exact(self):
        """Query /lookup with exact=True for a random URL."""
        import random

        url = random.choice(URLS)
        self.client.get(
            "/lookup",
            name="/lookup (exact)",
            params={"url": url, "exact": True},
        )

    @task(1)
    def lookup_with_limit(self):
        """Query /lookup with a small limit for a random URL."""
        import random

        url = random.choice(URLS)
        limit = random.randint(1, 5)
        self.client.get(
            "/lookup",
            name="/lookup (limited)",
            params={"url": url, "limit": limit},
        )
