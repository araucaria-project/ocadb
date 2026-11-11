import logging
from email.message import EmailMessage as MimeMessage

import aiosmtplib

from api.services.email.base import EmailMessage, EmailSender

log = logging.getLogger(__name__)


class SmtpEmailSender(EmailSender):
    def __init__(self, host: str, port: int, username: str, password: str, start_tls: bool, sender: str):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.start_tls = start_tls
        self.sender = sender

    async def send(self, message: EmailMessage) -> None:
        mime = MimeMessage()
        mime["From"] = self.sender
        mime["To"] = message.to
        mime["Subject"] = message.subject
        mime.set_content(message.text)
        if message.html:
            mime.add_alternative(message.html, subtype="html")
        try:
            await aiosmtplib.send(
                mime,
                hostname=self.host,
                port=self.port,
                username=self.username or None,
                password=self.password or None,
                start_tls=self.start_tls,
                timeout=30,
            )
        except (aiosmtplib.SMTPException, OSError):
            log.exception("Sending email to %s failed", message.to)
