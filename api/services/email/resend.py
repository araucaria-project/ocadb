import logging

import httpx

from api.services.email.base import EmailMessage, EmailSender

log = logging.getLogger(__name__)


class ResendEmailSender(EmailSender):
    """Sends through the Resend HTTP API, for hosts that block outgoing SMTP (Railway)."""

    URL = "https://api.resend.com/emails"

    def __init__(self, api_key: str, sender: str):
        self.api_key = api_key
        self.sender = sender

    async def send(self, message: EmailMessage) -> None:
        payload = {"from": self.sender, "to": [message.to], "subject": message.subject, "text": message.text}
        if message.html:
            payload["html"] = message.html
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(self.URL, json=payload, headers={"Authorization": f"Bearer {self.api_key}"})
        except httpx.HTTPError:
            log.exception("Sending email to %s failed", message.to)
            return
        if resp.is_error:
            log.error("Sending email to %s failed: Resend answered %s %s", message.to, resp.status_code, resp.text)
