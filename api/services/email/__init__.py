"""Outgoing email. Pick the backend with the ``EMAIL_BACKEND`` setting: "console", "smtp" or "resend"."""
from functools import lru_cache

from api import config
from api.services.email.base import EmailMessage, EmailSender
from api.services.email.console import ConsoleEmailSender


@lru_cache
def get_email_sender() -> EmailSender:
    """FastAPI dependency; override it in tests."""
    settings = config.Settings()
    if settings.EMAIL_BACKEND == "smtp":
        from api.services.email.smtp import SmtpEmailSender
        return SmtpEmailSender(
            host=settings.SMTP_HOST,
            port=settings.SMTP_PORT,
            username=settings.SMTP_USER,
            password=settings.SMTP_PASSWORD,
            start_tls=settings.SMTP_STARTTLS,
            sender=settings.EMAIL_FROM,
        )
    if settings.EMAIL_BACKEND == "resend":
        from api.services.email.resend import ResendEmailSender
        if not settings.RESEND_API_KEY:
            raise ValueError("EMAIL_BACKEND is 'resend' but RESEND_API_KEY is not set")
        return ResendEmailSender(api_key=settings.RESEND_API_KEY, sender=settings.EMAIL_FROM)
    if settings.EMAIL_BACKEND != "console":
        raise ValueError(f"Unknown EMAIL_BACKEND {settings.EMAIL_BACKEND!r}")
    return ConsoleEmailSender()


__all__ = ["EmailMessage", "EmailSender", "get_email_sender"]
