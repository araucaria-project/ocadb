"""Resend backend: request shape and failures that must not raise."""
import json

import httpx
import pytest

from api.services.email import resend
from api.services.email.base import EmailMessage
from api.services.email.resend import ResendEmailSender


@pytest.fixture
def requests(monkeypatch):
    seen = []
    status = {"code": 200}

    def handler(request: httpx.Request):
        seen.append(request)
        return httpx.Response(status["code"], json={"id": "x"})

    real_client = httpx.AsyncClient
    monkeypatch.setattr(resend.httpx, "AsyncClient",
                        lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw))
    return seen, status


async def test_resend_posts_message(requests):
    seen, _ = requests
    sender = ResendEmailSender(api_key="re_test", sender="OCADB <no-reply@mail.ocadb.space>")
    await sender.send(EmailMessage(to="a@example.com", subject="Hi", text="plain", html="<p>html</p>"))
    assert seen[0].url == ResendEmailSender.URL
    assert seen[0].headers["Authorization"] == "Bearer re_test"
    assert json.loads(seen[0].content) == {
        "from": "OCADB <no-reply@mail.ocadb.space>", "to": ["a@example.com"],
        "subject": "Hi", "text": "plain", "html": "<p>html</p>",
    }


async def test_resend_error_is_logged_not_raised(requests, caplog):
    _, status = requests
    status["code"] = 403
    await ResendEmailSender(api_key="bad", sender="x@y.z").send(EmailMessage(to="a@example.com", subject="s", text="t"))
    assert "Resend answered 403" in caplog.text
