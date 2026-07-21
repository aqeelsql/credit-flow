from __future__ import annotations

import asyncio
from email.message import EmailMessage
from email.utils import formataddr, parseaddr
import smtplib
import ssl

import httpx

from app.config import Settings
from app.errors import NotificationError


class EmailClient:
    def __init__(self, settings: Settings):
        self.settings = settings

    @property
    def provider(self) -> str:
        return "smtp" if self.settings.smtp_configured else "resend"

    def ensure_configured(self) -> None:
        if self.settings.smtp_configured:
            return
        if self.settings.resend_api_key:
            return
        raise NotificationError("email_not_configured", "SMTP or Resend email configuration is required.", 503)

    async def send_email(self, *, to: str, subject: str, html: str, text: str | None = None) -> str | None:
        self.ensure_configured()
        if self.settings.smtp_configured:
            return await asyncio.to_thread(self._send_smtp, to=to, subject=subject, html=html, text=text)
        return await self._send_resend(to=to, subject=subject, html=html, text=text)

    def _sender(self) -> tuple[str, str]:
        name, address = parseaddr(self.settings.resend_from_email)
        if not address:
            address = self.settings.smtp_username
        return name or "CreditFlow", address

    def _send_smtp(self, *, to: str, subject: str, html: str, text: str | None = None) -> str | None:
        sender_name, sender_email = self._sender()
        message = EmailMessage()
        message["From"] = formataddr((sender_name, sender_email))
        message["To"] = to
        message["Subject"] = subject
        message.set_content(text or "This email requires an HTML capable email client.")
        message.add_alternative(html, subtype="html")

        try:
            if self.settings.smtp_use_ssl:
                context = ssl.create_default_context()
                with smtplib.SMTP_SSL(self.settings.smtp_host, self.settings.smtp_port, timeout=30, context=context) as smtp:
                    smtp.login(self.settings.smtp_username, self.settings.smtp_password)
                    smtp.send_message(message)
            else:
                with smtplib.SMTP(self.settings.smtp_host, self.settings.smtp_port, timeout=30) as smtp:
                    smtp.ehlo()
                    if self.settings.smtp_use_tls:
                        smtp.starttls(context=ssl.create_default_context())
                        smtp.ehlo()
                    smtp.login(self.settings.smtp_username, self.settings.smtp_password)
                    smtp.send_message(message)
        except smtplib.SMTPAuthenticationError as exc:
            raise NotificationError("smtp_auth_failed", "SMTP authentication failed. For Gmail, use a Google App Password, not your normal Gmail password.", 400) from exc
        except smtplib.SMTPRecipientsRefused as exc:
            raise NotificationError("smtp_recipient_refused", f"SMTP recipient refused: {to}", 400) from exc
        except smtplib.SMTPException as exc:
            raise NotificationError("smtp_dispatch_failed", f"SMTP email dispatch failed: {exc}", 502) from exc
        except OSError as exc:
            raise NotificationError("smtp_unavailable", f"SMTP server is unavailable: {exc}", 503) from exc
        return None

    async def _send_resend(self, *, to: str, subject: str, html: str, text: str | None = None) -> str | None:
        payload = {"from": self.settings.resend_from_email, "to": [to], "subject": subject, "html": html}
        if text:
            payload["text"] = text
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(self.settings.resend_api_url, headers={"Authorization": f"Bearer {self.settings.resend_api_key}", "Content-Type": "application/json"}, json=payload)
        if response.status_code >= 400:
            detail = response.text[:500]
            try:
                body = response.json()
                if isinstance(body, dict):
                    message = body.get("message") or body.get("error") or body.get("name")
                    if message:
                        detail = str(message)[:500]
            except ValueError:
                pass
            status_code = 502 if response.status_code >= 500 else 400
            raise NotificationError("email_dispatch_failed", f"Resend email dispatch failed ({response.status_code}): {detail}", status_code)
        body = response.json()
        return str(body.get("id")) if isinstance(body, dict) and body.get("id") else None
