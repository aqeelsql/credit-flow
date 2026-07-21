from __future__ import annotations

import asyncio
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr, make_msgid, parseaddr

from app.config import Settings
from app.errors import NotificationError


class EmailClient:
    def __init__(self, settings: Settings):
        self.settings = settings

    def ensure_configured(self) -> None:
        if not self.settings.smtp_host:
            raise NotificationError("smtp_not_configured", "SMTP host is not configured.", 503)
        if not self.settings.smtp_username:
            raise NotificationError("smtp_not_configured", "SMTP username is not configured.", 503)
        if not self.settings.smtp_password:
            raise NotificationError("smtp_not_configured", "SMTP password is not configured. For Gmail, use a Google App Password.", 503)

    def _sender(self) -> tuple[str, str]:
        name, address = parseaddr(self.settings.email_from)
        if not address:
            address = self.settings.smtp_username
        if not name:
            name = "CreditFlow"
        return name, address

    async def send_email(self, *, to: str, subject: str, html: str, text: str | None = None) -> str | None:
        self.ensure_configured()
        message_id = make_msgid(domain="creditflow.local")
        sender_name, sender_email = self._sender()

        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = formataddr((sender_name, sender_email))
        message["To"] = to
        message["Message-ID"] = message_id
        message.set_content(text or "")
        message.add_alternative(html, subtype="html")

        try:
            await asyncio.to_thread(self._send_sync, message)
        except smtplib.SMTPAuthenticationError as exc:
            raise NotificationError("smtp_auth_failed", "Gmail SMTP authentication failed. Use the Gmail address as SMTP_USERNAME and a Google App Password as SMTP_PASSWORD.", 401) from exc
        except smtplib.SMTPRecipientsRefused as exc:
            raise NotificationError("smtp_recipient_refused", f"SMTP recipient refused: {to}", 400) from exc
        except smtplib.SMTPResponseException as exc:
            status_code = 502 if int(exc.smtp_code or 0) >= 500 else 400
            detail = exc.smtp_error.decode("utf-8", errors="replace") if isinstance(exc.smtp_error, bytes) else str(exc.smtp_error)
            raise NotificationError("email_dispatch_failed", f"SMTP dispatch failed ({exc.smtp_code}): {detail[:500]}", status_code) from exc
        except OSError as exc:
            raise NotificationError("smtp_connection_failed", f"SMTP connection failed: {exc}", 503) from exc

        return message_id.strip("<>")

    def _send_sync(self, message: EmailMessage) -> None:
        context = ssl.create_default_context()
        if self.settings.smtp_use_ssl:
            with smtplib.SMTP_SSL(self.settings.smtp_host, self.settings.smtp_port, timeout=self.settings.smtp_timeout_seconds, context=context) as smtp:
                smtp.login(self.settings.smtp_username, self.settings.smtp_password)
                smtp.send_message(message)
            return

        with smtplib.SMTP(self.settings.smtp_host, self.settings.smtp_port, timeout=self.settings.smtp_timeout_seconds) as smtp:
            smtp.ehlo()
            if self.settings.smtp_use_tls:
                smtp.starttls(context=context)
                smtp.ehlo()
            smtp.login(self.settings.smtp_username, self.settings.smtp_password)
            smtp.send_message(message)
