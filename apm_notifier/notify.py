from __future__ import annotations

from dataclasses import dataclass
from html import escape
import json
import re
from urllib.parse import quote
from urllib.request import Request, urlopen

from .fetch import trusted_ssl_context
from .models import Job, SourceResult


def _health_error_summary(errors: tuple[str, ...]) -> str:
    summaries: list[str] = []
    for error in errors:
        http_error = re.search(r"HTTP Error (\d+): ([^;]+)", error)
        if http_error:
            summary = f"HTTP {http_error.group(1)}: {http_error.group(2).strip()}"
        elif "browser render" in error.casefold() and "timed out" in error.casefold():
            summary = "Browser rendering timed out after retries"
        elif "timed out" in error.casefold():
            summary = "Network request timed out after retries"
        elif "response contained no job records" in error.casefold():
            summary = "Career page returned no readable job data"
        else:
            summary = re.sub(r"^https?://\S+\s*", "Career feed: ", error).strip()
        if summary and summary not in summaries:
            summaries.append(summary)
    return "; ".join(summaries)[:400] or "Unknown career-feed error"


@dataclass(frozen=True)
class NotificationOutcome:
    delivered: bool
    errors: tuple[str, ...] = ()


class NotificationManager:
    def __init__(
        self,
        telegram_bot_token: str,
        telegram_chat_id: str,
        ntfy_topic: str,
        ntfy_server: str,
        timeout_seconds: int,
    ) -> None:
        self.telegram_bot_token = telegram_bot_token
        self.telegram_chat_id = telegram_chat_id
        self.ntfy_topic = ntfy_topic
        self.ntfy_server = ntfy_server
        self.timeout_seconds = timeout_seconds
        self.ssl_context = trusted_ssl_context()

    @property
    def configured_channels(self) -> tuple[str, ...]:
        channels: list[str] = []
        if self.telegram_bot_token and self.telegram_chat_id:
            channels.append("Telegram")
        if self.ntfy_topic:
            channels.append("ntfy")
        return tuple(channels)

    def send_job(self, job: Job) -> NotificationOutcome:
        telegram_text = (
            "🚨 <b>New product role</b>\n\n"
            f"<b>{escape(job.company)}</b>\n"
            f"{escape(job.title)}\n"
            + (f"📍 {escape(job.location)}\n" if job.location else "")
            + f'\n<a href="{escape(job.url, quote=True)}">Open the application</a>'
        )
        plain_text = f"{job.company}\n{job.title}"
        if job.location:
            plain_text += f"\n{job.location}"
        return self._send_all(telegram_text, plain_text, job.url, f"New role at {job.company}")

    def send_health(self, result: SourceResult) -> NotificationOutcome:
        detail = _health_error_summary(result.errors)
        telegram_text = (
            "⚠️ <b>APM Notifier coverage degraded</b>\n\n"
            f"<b>{escape(result.source.name)}</b> has remained unavailable for at least 6 hours.\n"
            "Monitoring and retries are continuing automatically. You do not need to do anything.\n\n"
            f"Latest error: {escape(detail)}\n\n"
            f'<a href="{escape(result.source.career_url, quote=True)}">Open career page</a>'
        )
        plain_text = (
            f"{result.source.name} has remained unavailable for at least 6 hours.\n"
            "Monitoring continues automatically; no action is needed.\n"
            f"Latest error: {detail}"
        )
        return self._send_all(
            telegram_text,
            plain_text,
            result.source.career_url,
            "APM Notifier source warning",
        )

    def send_test(self) -> NotificationOutcome:
        job = Job(
            source_id="test",
            company="Example Tech Company",
            title="Associate Product Manager Intern — Summer 2027",
            url="https://example.com/apply",
            location="Toronto, Canada / Remote",
        )
        return self.send_job(job)

    def _send_all(self, telegram_text: str, plain_text: str, click_url: str, title: str) -> NotificationOutcome:
        errors: list[str] = []
        delivered = False
        if self.telegram_bot_token and self.telegram_chat_id:
            try:
                self._send_telegram(telegram_text)
                delivered = True
            except Exception as error:  # Channel failures must not stop other channels.
                errors.append(f"Telegram: {error}")
        if self.ntfy_topic:
            try:
                self._send_ntfy(plain_text, click_url, title)
                delivered = True
            except Exception as error:
                errors.append(f"ntfy: {error}")
        return NotificationOutcome(delivered=delivered, errors=tuple(errors))

    def _send_telegram(self, message: str) -> None:
        endpoint = f"https://api.telegram.org/bot{quote(self.telegram_bot_token, safe=':')}/sendMessage"
        body = json.dumps(
            {
                "chat_id": self.telegram_chat_id,
                "text": message,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            }
        ).encode("utf-8")
        request = Request(endpoint, data=body, headers={"Content-Type": "application/json"}, method="POST")
        with urlopen(request, timeout=self.timeout_seconds, context=self.ssl_context) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if not payload.get("ok"):
            raise RuntimeError(payload.get("description", "Telegram rejected the message"))

    def _send_ntfy(self, message: str, click_url: str, title: str) -> None:
        endpoint = f"{self.ntfy_server}/{quote(self.ntfy_topic, safe='')}"
        request = Request(
            endpoint,
            data=message.encode("utf-8"),
            headers={
                "Title": title.encode("ascii", errors="ignore").decode("ascii") or "APM Notifier",
                "Priority": "4",
                "Tags": "rotating_light,briefcase",
                "Click": click_url,
            },
            method="POST",
        )
        with urlopen(request, timeout=self.timeout_seconds, context=self.ssl_context) as response:
            if response.status >= 300:
                raise RuntimeError(f"ntfy returned HTTP {response.status}")
