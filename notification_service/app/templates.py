from __future__ import annotations

from html import escape
from typing import Any

from app.config import Settings


def _first(payload: dict[str, Any], keys: list[str]) -> str | None:
    for key in keys:
        value = payload.get(key)
        if value:
            return str(value)
    nested = payload.get("user") if isinstance(payload.get("user"), dict) else {}
    for key in keys:
        value = nested.get(key)
        if value:
            return str(value)
    return None


def recipient_for_event(event_type: str, payload: dict[str, Any], settings: Settings) -> str | None:
    if event_type in {"post.failed", "payment.failed"}:
        return _first(payload, ["recipient", "email", "owner_email", "user_email", "account_email"]) or settings.ops_email
    return _first(payload, ["recipient", "email", "owner_email", "user_email", "invitee_email", "member_email", "account_email"])


def _verify_url(payload: dict[str, Any], settings: Settings) -> str:
    token = payload.get("verification_token") or payload.get("token") or ""
    if payload.get("verification_url"):
        return str(payload["verification_url"])
    return f"{settings.frontend_base_url.rstrip('/')}/verify-email?token={token}"


def build_email(event_type: str, payload: dict[str, Any], settings: Settings) -> dict[str, str]:
    account_name = str(payload.get("account_name") or payload.get("workspace_name") or "CreditFlow")
    if event_type == "user.registered":
        url = _verify_url(payload, settings)
        safe_url = escape(url, quote=True)
        safe_account = escape(account_name, quote=True)
        return {
            "notification_type": "signup_verification",
            "subject": "Verify your CreditFlow account",
            "text": f"Welcome to CreditFlow. Verify your account here: {url}",
            "html": (
                "<div style='font-family:Inter,Arial,sans-serif;line-height:1.6;color:#0f172a'>"
                "<h2 style='margin:0 0 12px'>Verify your CreditFlow account</h2>"
                f"<p>Welcome to {safe_account}. Confirm your email address to activate your workspace and sign in.</p>"
                f"<p><a href='{safe_url}' style='display:inline-block;background:#2563eb;color:#fff;text-decoration:none;padding:12px 18px;border-radius:10px;font-weight:700'>Verify account</a></p>"
                f"<p style='font-size:13px;color:#64748b'>If the button does not work, copy and paste this link into your browser:<br>{safe_url}</p>"
                "</div>"
            ),
        }
    if event_type == "user.password_reset_requested":
        otp = str(payload.get("otp") or payload.get("code") or "")
        expires_seconds = int(payload.get("otp_expires_in") or payload.get("expires_in") or 600)
        expires_minutes = max(1, round(expires_seconds / 60))
        reset_url = f"{settings.frontend_base_url.rstrip('/')}/forgot-password?email={payload.get('email', '')}"
        safe_otp = escape(otp, quote=True)
        safe_reset_url = escape(reset_url, quote=True)
        return {
            "notification_type": "password_reset",
            "subject": "Reset your CreditFlow password",
            "text": f"Use this one-time code to reset your CreditFlow password: {otp}. It expires in {expires_minutes} minutes.",
            "html": (
                "<div style='font-family:Inter,Arial,sans-serif;line-height:1.6;color:#0f172a'>"
                "<h2 style='margin:0 0 12px'>Reset your CreditFlow password</h2>"
                "<p>Use this one-time code to reset your password. It can be used once.</p>"
                f"<p style='font-size:28px;letter-spacing:8px;font-weight:800;background:#eef6ff;color:#1d4ed8;padding:14px 18px;border-radius:12px;display:inline-block'>{safe_otp}</p>"
                f"<p style='font-size:13px;color:#64748b'>This code expires in {expires_minutes} minutes.</p>"
                f"<p><a href='{safe_reset_url}' style='display:inline-block;background:#2563eb;color:#fff;text-decoration:none;padding:12px 18px;border-radius:10px;font-weight:700'>Open reset page</a></p>"
                "<p style='font-size:13px;color:#64748b'>If you did not request this, you can ignore this email.</p>"
                "</div>"
            ),
        }
    if event_type == "invoice.paid":
        amount = payload.get("amount_paid") or payload.get("amount") or ""
        currency = str(payload.get("currency") or "usd").upper()
        invoice_id = payload.get("stripe_invoice_id") or payload.get("invoice_id") or ""
        return {"notification_type": "payment_receipt", "subject": "Your CreditFlow payment receipt", "text": f"Payment received for {amount} {currency}. Invoice: {invoice_id}", "html": f"<h2>Payment received</h2><p>Amount: {amount} {currency}</p><p>Invoice: {invoice_id}</p>"}
    if event_type == "payment.failed":
        reason = payload.get("reason") or "payment failed"
        return {"notification_type": "payment_failed", "subject": "CreditFlow payment failed", "text": f"A payment failed for {account_name}. Reason: {reason}", "html": f"<h2>Payment failed</h2><p>Workspace: {account_name}</p><p>Reason: {reason}</p>"}
    if event_type in {"member.invited", "team.invite.created"}:
        code = str(payload.get("code") or payload.get("invite_code") or payload.get("token") or "")
        invite_url = str(payload.get("invite_url") or payload.get("accept_url") or f"{settings.frontend_base_url.rstrip('/')}/signup?invite={code}")
        safe_invite_url = escape(invite_url, quote=True)
        safe_code = escape(code, quote=True)
        safe_account = escape(account_name, quote=True)
        return {
            "notification_type": "workspace_invite",
            "subject": f"You have been invited to {account_name}",
            "text": f"You have been invited to {account_name}. Open: {invite_url}. Invite code: {code}",
            "html": (
                "<div style='font-family:Inter,Arial,sans-serif;line-height:1.6;color:#0f172a'>"
                f"<h2>You have been invited to {safe_account}</h2>"
                "<p>Create or log in to your CreditFlow account, then accept this invite.</p>"
                f"<p><a href='{safe_invite_url}' style='display:inline-block;background:#2563eb;color:#fff;text-decoration:none;padding:12px 18px;border-radius:10px;font-weight:700'>Accept invite</a></p>"
                f"<p style='font-size:13px;color:#64748b'>Invite code: <strong>{safe_code}</strong></p>"
                "</div>"
            ),
        }
    if event_type == "member.joined":
        safe_account = escape(account_name, quote=True)
        return {"notification_type": "member_joined", "subject": f"A member joined {account_name}", "text": f"A member joined {account_name}.", "html": f"<h2>Member joined</h2><p>A member joined {safe_account}.</p>"}
    if event_type == "post.published":
        post_url = payload.get("post_url") or payload.get("linkedin_post_url") or payload.get("post_id") or ""
        return {"notification_type": "post_published", "subject": "Your scheduled post was published", "text": f"Your scheduled post was published. {post_url}", "html": f"<h2>Post published</h2><p>Your scheduled post was published.</p><p>{post_url}</p>"}
    if event_type == "post.failed":
        reason = payload.get("reason") or payload.get("error") or "unknown failure"
        return {"notification_type": "post_failed", "subject": "A scheduled post failed", "text": f"A scheduled post failed. Reason: {reason}", "html": f"<h2>Post failed</h2><p>Reason: {reason}</p>"}
    if event_type == "usage.threshold_reached":
        threshold = payload.get("threshold") or payload.get("percentage") or payload.get("threshold_percent") or ""
        return {"notification_type": "usage_threshold", "subject": "CreditFlow usage quota warning", "text": f"Your AI usage has reached {threshold}% of quota.", "html": f"<h2>Usage quota warning</h2><p>Your AI usage has reached {threshold}% of quota.</p>"}
    return {"notification_type": "generic_event", "subject": f"CreditFlow event: {event_type}", "text": str(payload), "html": f"<pre>{payload}</pre>"}


