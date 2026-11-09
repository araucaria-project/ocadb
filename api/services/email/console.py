import logging

from api.services.email.base import EmailMessage, EmailSender

log = logging.getLogger(__name__)


class ConsoleEmailSender(EmailSender):
    """Development and test sender: logs the message and keeps it in ``outbox``."""

    def __init__(self):
        self.outbox: list[EmailMessage] = []

    async def send(self, message: EmailMessage) -> None:
        self.outbox.append(message)
        log.warning("Email (console backend, not sent) to %s: %s\n%s", message.to, message.subject, message.text)
