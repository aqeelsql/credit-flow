from __future__ import annotations

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
        return {
            "notification_type": "signup_verification",
            "subject": "Verify your CreditFlow account",
            "text": f"Welcome to CreditFlow. Verify your account here: {url}",
            "html": f"<h2>Welcome to CreditFlow</h2><p>Verify your account to start using your workspace.</p><p><a href='{url}'>Verify account</a></p>",
        }
    if event_type == "invoice.paid":
        amount = payload.get("amount_paid") or payload.get("amount") or ""
        currency = str(payload.get("currency") or "usd").upper()
        invoice_id = payload.get("stripe_invoice_id") or payload.get("invoice_id") or ""
        return {"notification_type": "payment_receipt", "subject": "Your CreditFlow payment receipt", "text": f"Payment received for {amount} {currency}. Invoice: {invoice_id}", "html": f"<h2>Payment received</h2><p>Amount: {amount} {currency}</p><p>Invoice: {invoice_id}</p>"}
    if event_type == "payment.failed":
        reason = payload.get("reason") or "payment failed"
        return {"notification_type": "payment_failed", "subject": "CreditFlow payment failed", "text": f"A payment failed for {account_name}. Reason: {reason}", "html": f"<h2>Payment failed</h2><p>Workspace: {account_name}</p><p>Reason: {reason}</p>"}
    if event_type in {"member.joined", "team.invite.created"}:
        invite_url = payload.get("invite_url") or payload.get("accept_url") or f"{settings.frontend_base_url.rstrip('/')}/login"
        return {"notification_type": "workspace_invite", "subject": f"You have been invited to {account_name}", "text": f"Open your CreditFlow workspace invitation: {invite_url}", "html": f"<h2>Workspace invitation</h2><p>You have been invited to {account_name}.</p><p><a href='{invite_url}'>Open invitation</a></p>"}
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
