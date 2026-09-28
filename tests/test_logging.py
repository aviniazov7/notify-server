import logging

from app.logging_config import RedactTokenFilter

from .conftest import PASSWORD, token_for


def test_redact_filter_masks_token_in_uvicorn_style_record():
    record = logging.LogRecord(
        "uvicorn.error",
        logging.INFO,
        __file__,
        1,
        '%s - "WebSocket %s" [accepted]',
        (("127.0.0.1", 5000), "/api/v1/ws?token=abc123SECRET&x=1"),
        None,
    )

    RedactTokenFilter().filter(record)

    assert "abc123SECRET" not in record.getMessage()
    assert "token=***&x=1" in record.getMessage()


def test_full_flow_never_logs_token_or_password(client, caplog):
    caplog.set_level(logging.DEBUG)

    client.put("/api/v1/auth/session", json={"username": "tester", "password": "wrong-pass"})
    token = token_for(client)
    with client.websocket_connect(f"/api/v1/ws?token={token}") as ws:
        ws.receive_json()
        ws.send_text("not json")
        ws.receive_json()
        ws.send_json({"type": "info", "message": "hi"})
        ws.receive_json()
    client.get("/api/v1/notifications", headers={"Authorization": "Bearer nope"})
    client.delete("/api/v1/auth/session", headers={"Authorization": f"Bearer {token}"})

    text = caplog.text
    assert "login failed" in text
    assert "ws connected" in text
    assert "ws disconnected" in text
    assert "logout" in text
    assert token not in text
    assert PASSWORD not in text
    assert "wrong-pass" not in text
