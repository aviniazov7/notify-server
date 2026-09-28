import time

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from .conftest import USERNAME, token_for


def ws_url(token: str) -> str:
    return f"/api/v1/ws?token={token}"


def test_bad_token_is_closed_with_1008(client):
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect(ws_url("not-a-real-token")):
            pass

    assert exc.value.code == status.WS_1008_POLICY_VIOLATION


def test_connect_sends_connected_notification(client):
    with client.websocket_connect(ws_url(token_for(client))) as ws:
        msg = ws.receive_json()

    assert msg["type"] == "notification"
    assert msg["notification"]["type"] == "connected"
    assert msg["notification"]["username"] == USERNAME


def test_notification_gets_ack(client):
    with client.websocket_connect(ws_url(token_for(client))) as ws:
        ws.receive_json()  # connected
        ws.send_json({"type": "trade_signal", "message": "BTC long", "data": {"rr": 2.5}})
        ack = ws.receive_json()

    assert ack["type"] == "ack"
    note = ack["notification"]
    assert note["type"] == "trade_signal"
    assert note["message"] == "BTC long"
    assert note["data"] == {"rr": 2.5}
    assert note["username"] == USERNAME
    assert note["id"]


@pytest.mark.parametrize(
    "payload",
    [
        {"message": "missing type"},
        {"type": "info", "message": "x" * 1001},
        ["not", "an", "object"],
    ],
)
def test_invalid_notification_gets_error_and_socket_stays_open(client, payload):
    with client.websocket_connect(ws_url(token_for(client))) as ws:
        ws.receive_json()  # connected
        ws.send_json(payload)
        assert ws.receive_json() == {"type": "error", "message": "invalid notification"}

        # Same socket still works.
        ws.send_json({"type": "info", "message": "still here"})
        assert ws.receive_json()["type"] == "ack"


def test_expired_token_is_rejected_at_handshake(make_client):
    client = make_client(session_ttl_seconds=0)
    token = token_for(client)

    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect(ws_url(token)):
            pass

    assert exc.value.code == status.WS_1008_POLICY_VIOLATION


def test_session_expiring_mid_connection_is_rejected(make_client):
    client: TestClient = make_client(session_ttl_seconds=1)

    with client.websocket_connect(ws_url(token_for(client))) as ws:
        ws.receive_json()  # connected
        time.sleep(1.1)  # let the 1s session expire
        ws.send_json({"type": "info", "message": "too late"})

        assert ws.receive_json() == {"type": "error", "message": "session expired"}
        with pytest.raises(WebSocketDisconnect) as exc:
            ws.receive_json()
        assert exc.value.code == status.WS_1008_POLICY_VIOLATION


@pytest.mark.parametrize("send", ["text", "bytes"])
def test_malformed_frame_gets_error_and_socket_stays_open(client, send):
    with client.websocket_connect(ws_url(token_for(client))) as ws:
        ws.receive_json()  # connected
        if send == "text":
            ws.send_text("{not valid json")
        else:
            ws.send_bytes(b"\x00\x01")
        assert ws.receive_json() == {"type": "error", "message": "invalid JSON"}

        ws.send_json({"type": "info", "message": "still here"})
        assert ws.receive_json()["type"] == "ack"
