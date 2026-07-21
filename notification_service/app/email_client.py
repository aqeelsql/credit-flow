from __future__ import annotations

import asyncio
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr, make_msgid, parseaddr

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

        if self.settings.resend_configured:
            return

        raise NotificationError(
            "email_not_configured",
            "SMTP or Resend email configuration is required.",
            503,
        )

    def _sender(self) -> tuple[str, str]:
        name, address = parseaddr(self.settings.resend_from_email)

        if not address:
            address = self.settings.smtp_username

        if not name:
            name = "CreditFlow"

        return name, address

    async def send_email(
        self,
        *,
        to: str,
        subject: str,
        html: str,
        text: str | None = None,
    ) -> str | None:
        self.ensure_configured()

        if self.settings.smtp_configured:
            message_id = make_msgid(domain="creditflow.local")

            sender_name, sender_email = self._sender()

            message = EmailMessage()
            message["Subject"] = subject
            message["From"] = formataddr((sender_name, sender_email))
            message["To"] = to
            message["Message-ID"] = message_id

            message.set_content(
                text or "This email requires an HTML capable email client."
            )
            message.add_alternative(html, subtype="html")

            try:
                await asyncio.to_thread(self._send_sync, message)

            except smtplib.SMTPAuthenticationError as exc:
                raise NotificationError(
                    "smtp_auth_failed",
                    "SMTP authentication failed. For Gmail, use a Google App Password.",
                    401,
                ) from exc

            except smtplib.SMTPRecipientsRefused as exc:
                raise NotificationError(
                    "smtp_recipient_refused",
                    f"SMTP recipient refused: {to}",
                    400,
                ) from exc

            except smtplib.SMTPResponseException as exc:
                status = 502 if int(exc.smtp_code or 0) >= 500 else 400

                detail = (
                    exc.smtp_error.decode("utf-8", errors="replace")
                    if isinstance(exc.smtp_error, bytes)
                    else str(exc.smtp_error)
                )

                raise NotificationError(
                    "email_dispatch_failed",
                    f"SMTP dispatch failed ({exc.smtp_code}): {detail[:500]}",
                    status,
                ) from exc

            except OSError as exc:
                raise NotificationError(
                    "smtp_connection_failed",
                    f"SMTP connection failed: {exc}",
                    503,
                ) from exc

            return message_id.strip("<>")

        return await self._send_resend(
            to=to,
            subject=subject,
            html=html,
            text=text,
        )

    def _send_sync(self, message: EmailMessage) -> None:
        context = ssl.create_default_context()

        if self.settings.smtp_use_ssl:
            with smtplib.SMTP_SSL(
                self.settings.smtp_host,
                self.settings.smtp_port,
                timeout=self.settings.smtp_timeout_seconds,
                context=context,
            ) as smtp:
                smtp.login(
                    self.settings.smtp_username,
                    self.settings.smtp_password,
                )
                smtp.send_message(message)
            return

        with smtplib.SMTP(
            self.settings.smtp_host,
            self.settings.smtp_port,
            timeout=self.settings.smtp_timeout_seconds,
        ) as smtp:
            smtp.ehlo()

            if self.settings.smtp_use_tls:
                smtp.starttls(context=context)
                smtp.ehlo()

            smtp.login(
                self.settings.smtp_username,
                self.settings.smtp_password,
            )

            smtp.send_message(message)

    async def _send_resend(
        self,
        *,
        to: str,
        subject: str,
        html: str,
        text: str | None = None,
    ) -> str | None:

        payload = {
            "from": self.settings.resend_from_email,
            "to": [to],
            "subject": subject,
            "html": html,
        }

        if text:
            payload["text"] = text

        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(
                self.settings.resend_api_url,
                headers={
                    "Authorization": f"Bearer {self.settings.resend_api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )

        if response.status_code >= 400:
            detail = response.text[:500]

            try:
                body = response.json()

                if isinstance(body, dict):
                    message = (
                        body.get("message")
                        or body.get("error")
                        or body.get("name")
                    )

                    if message:
                        detail = str(message)[:500]

            except ValueError:
                pass

            status = 502 if response.status_code >= 500 else 400

            raise NotificationError(
                "email_dispatch_failed",
                f"Resend email dispatch failed ({response.status_code}): {detail}",
                status,
            )

        body = response.json()

        if isinstance(body, dict):
            return body.get("id")

        return None