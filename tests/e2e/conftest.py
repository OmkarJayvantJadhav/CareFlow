"""Starts the app (tests/e2e/server.py) and a headless Chromium for the browser tests."""

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest
from playwright.sync_api import expect

expect.set_options(timeout=10_000)

ROOT = Path(__file__).resolve().parents[2]


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def base_url():
    if not (ROOT / "ui" / "dist" / "index.html").exists():
        pytest.fail("Build the UI first: cd ui && npm ci && npm run build")
    port = _free_port()
    log = open(ROOT / "tests" / "e2e" / "server.log", "w")  # noqa: SIM115 - closed below
    proc = subprocess.Popen([sys.executable, "-m", "tests.e2e.server", str(port)], cwd=ROOT, stdout=log,
                            stderr=subprocess.STDOUT, env={**os.environ})  # fmt: skip
    url = f"http://127.0.0.1:{port}"
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            log.close()
            pytest.fail("the test server exited:\n" + (ROOT / "tests" / "e2e" / "server.log").read_text()[-3000:])
        try:
            if httpx.get(f"{url}/api/v1/health", timeout=2).status_code == 200:
                break
        except httpx.HTTPError:
            pass
        time.sleep(0.5)
    else:
        proc.terminate()
        pytest.fail("the test server did not start in time")
    yield url
    proc.terminate()
    proc.wait(timeout=10)
    log.close()


@pytest.fixture(scope="session")
def browser():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


@pytest.fixture
def page(browser, base_url):
    context = browser.new_context(base_url=base_url, viewport={"width": 1280, "height": 900})
    pg = context.new_page()
    pg.set_default_timeout(15000)
    yield pg
    context.close()


@pytest.fixture
def phone(browser, base_url):
    context = browser.new_context(base_url=base_url, viewport={"width": 360, "height": 740}, is_mobile=True)
    pg = context.new_page()
    pg.set_default_timeout(15000)
    yield pg
    context.close()


class Api:
    """Direct API calls for test setup (as staff or admin), outside the browser."""

    def __init__(self, base_url: str, role: str):
        self.base = f"{base_url}/api/v1"
        token = httpx.post(f"{self.base}/auth/demo-login", json={"role": role}).json()["token"]
        self.headers = {"Authorization": f"Bearer {token}"}

    def get(self, path: str, **params):
        response = httpx.get(f"{self.base}{path}", params=params, headers=self.headers, timeout=30)
        response.raise_for_status()
        return response.json()

    def post(self, path: str, body: dict | None = None):
        response = httpx.post(f"{self.base}{path}", json=body or {}, headers=self.headers, timeout=60)
        response.raise_for_status()
        return response.json()


@pytest.fixture
def staff_api(base_url):
    return Api(base_url, "staff")


@pytest.fixture
def admin_api(base_url):
    return Api(base_url, "admin")
