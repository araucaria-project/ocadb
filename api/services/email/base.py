from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class EmailMessage:
    to: str
    subject: str
    text: str
    html: str | None = None


class EmailSender(ABC):
    """Sends one email. Implementations must not raise for delivery problems
    the caller cannot act on; they log them instead."""

    @abstractmethod
    async def send(self, message: EmailMessage) -> None:
        ...
