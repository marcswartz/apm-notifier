from __future__ import annotations

import json
from pathlib import Path
import random
import os
import shutil
import ssl
import subprocess
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .models import FetchResult


DEFAULT_HEADERS = {
    "Accept": "text/html,application/json;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.8",
    "Cache-Control": "no-cache",
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
}
BLOCK_MARKERS = (
    "access denied",
    "attention required! | cloudflare",
    "please enable javascript and cookies to continue",
    "request unsuccessful. incapsula incident id",
)


class FetchError(RuntimeError):
    pass


def trusted_ssl_context() -> ssl.SSLContext:
    """Build a verified TLS context, including framework Pythons without a CA path."""
    defaults = ssl.get_default_verify_paths()
    candidates = (
        defaults.cafile,
        defaults.openssl_cafile,
        "/etc/ssl/cert.pem",
        "/etc/ssl/certs/ca-certificates.crt",
        "/etc/pki/tls/certs/ca-bundle.crt",
    )
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return ssl.create_default_context(cafile=candidate)
    return ssl.create_default_context()


class HttpClient:
    def __init__(self, timeout_seconds: int, attempts: int = 2) -> None:
        self.timeout_seconds = timeout_seconds
        self.attempts = attempts
        self.ssl_context = trusted_ssl_context()

    def fetch(self, url: str, extra_headers: dict[str, str] | None = None) -> FetchResult:
        headers = dict(DEFAULT_HEADERS)
        headers.update(extra_headers or {})
        last_error: Exception | None = None
        for attempt in range(self.attempts):
            try:
                request = Request(url, headers=headers, method="GET")
                with urlopen(request, timeout=self.timeout_seconds, context=self.ssl_context) as response:
                    body = response.read()
                    content_type = response.headers.get("Content-Type", "")
                    charset = response.headers.get_content_charset() or "utf-8"
                    text = body.decode(charset, errors="replace")
                    self._check_for_block_page(text, content_type)
                    return FetchResult(
                        requested_url=url,
                        final_url=response.geturl(),
                        content_type=content_type,
                        text=text,
                    )
            except HTTPError as error:
                last_error = error
                if error.code not in {408, 425, 429, 500, 502, 503, 504}:
                    break
                retry_after = error.headers.get("Retry-After", "")
                delay = int(retry_after) if retry_after.isdigit() else 1.5 * (attempt + 1)
                time.sleep(min(delay, 10) + random.random() / 4)
            except (TimeoutError, URLError, OSError, FetchError, json.JSONDecodeError) as error:
                last_error = error
                if "CERTIFICATE_VERIFY_FAILED" in str(error) and shutil.which("curl"):
                    try:
                        return self._fetch_with_curl(url, headers)
                    except FetchError as curl_error:
                        last_error = curl_error
                if attempt + 1 < self.attempts:
                    time.sleep(1.5 * (attempt + 1) + random.random() / 4)
        detail = str(last_error) if last_error else "unknown fetch error"
        raise FetchError(f"{url}: {detail}") from last_error

    def _fetch_with_curl(self, url: str, headers: dict[str, str]) -> FetchResult:
        """Use curl's native trust store when a framework Python lacks an intermediate CA."""
        marker = "\n__APM_NOTIFIER_CURL_METADATA__"
        command = [
            shutil.which("curl") or "curl",
            "--fail",
            "--location",
            "--compressed",
            "--silent",
            "--show-error",
            "--max-time",
            str(self.timeout_seconds),
        ]
        for key, value in headers.items():
            command.extend(("--header", f"{key}: {value}"))
        command.extend(("--write-out", f"{marker}%{{url_effective}}\t%{{content_type}}", url))
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds + 5,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise FetchError(f"{url}: curl fallback failed: {error}") from error
        if completed.returncode != 0:
            raise FetchError(f"{url}: curl fallback failed: {completed.stderr.strip()}")
        if marker not in completed.stdout:
            raise FetchError(f"{url}: curl fallback returned malformed output")
        text, metadata = completed.stdout.rsplit(marker, 1)
        final_url, _, content_type = metadata.partition("\t")
        self._check_for_block_page(text, content_type)
        return FetchResult(
            requested_url=url,
            final_url=final_url or url,
            content_type=content_type,
            text=text,
        )

    @staticmethod
    def _check_for_block_page(text: str, content_type: str) -> None:
        if "html" not in content_type.casefold():
            return
        lowered = text[:200_000].casefold()
        marker = next((item for item in BLOCK_MARKERS if item in lowered), None)
        if marker:
            raise FetchError(f"site returned a bot-protection page ({marker})")


class BrowserRenderer:
    """Render the small set of JavaScript-only career searches with local Chromium."""

    def __init__(self, timeout_seconds: int) -> None:
        self.timeout_seconds = timeout_seconds
        configured = os.getenv("BROWSER_EXECUTABLE", "").strip()
        candidates = (
            configured,
            shutil.which("chromium") or "",
            shutil.which("chromium-browser") or "",
            shutil.which("google-chrome") or "",
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        )
        self.executable = next((item for item in candidates if item and Path(item).is_file()), "")
        self._render_lock = threading.Lock()

    def fetch(self, url: str) -> FetchResult:
        if not self.executable:
            raise FetchError(
                f"{url}: this source needs Chromium; set BROWSER_EXECUTABLE or use the Docker image"
            )
        command = [
            self.executable,
            "--headless=new",
            "--disable-gpu",
            "--disable-dev-shm-usage",
            "--no-sandbox",
            "--incognito",
            "--dump-dom",
            url,
        ]
        with self._render_lock:
            try:
                completed = subprocess.run(
                    command,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout_seconds + 20,
                    check=False,
                )
            except (OSError, subprocess.TimeoutExpired) as error:
                raise FetchError(f"{url}: browser render failed: {error}") from error
        html = completed.stdout.strip()
        if completed.returncode != 0 or not html:
            detail = completed.stderr.strip().splitlines()[-1:] or ["empty browser response"]
            raise FetchError(f"{url}: browser render failed: {detail[0]}")
        HttpClient._check_for_block_page(html, "text/html")
        return FetchResult(
            requested_url=url,
            final_url=url,
            content_type="text/html; charset=utf-8",
            text=html,
        )
