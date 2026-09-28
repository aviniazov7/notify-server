"""CLI test client.

Flow:
  1. PUT /auth/session  -> get a token
  2. open WS /ws?token=...
  3. stream notifications, print server acks

Credentials come from DEMO_USERNAME / DEMO_PASSWORD (env or .env), the same
values the server seeds on startup.

Run the server first, then from the repo root: python -m client.test_client
"""

import asyncio
import json

import httpx
import websockets

from app.config import settings

BASE = f"http://localhost:{settings.port}{settings.api_prefix}"
WS_BASE = f"ws://localhost:{settings.port}{settings.api_prefix}"


async def main() -> None:
    if not (settings.demo_username and settings.demo_password):
        raise SystemExit("Set DEMO_USERNAME and DEMO_PASSWORD (see .env.example)")

    # 1) Authenticate via PUT -> receive session token
    async with httpx.AsyncClient() as client:
        resp = await client.put(
            f"{BASE}/auth/session",
            json={
                "username": settings.demo_username,
                "password": settings.demo_password.get_secret_value(),
            },
        )
        resp.raise_for_status()
        session = resp.json()
        token = session["token"]
        print(f"[auth] session_id={session['session_id']}")

    # 2) Open the persistent WebSocket
    async with websockets.connect(f"{WS_BASE}/ws?token={token}") as ws:
        print(f"[ws]   {await ws.recv()}")

        # 3) Send a few notifications
        samples = [
            {"type": "trade_signal", "message": "BTC long @ 65000",
             "data": {"symbol": "BTCUSDT", "rr": 2.5}},
            {"type": "alert", "message": "ETH crossed 3500"},
            {"type": "info", "message": "system heartbeat"},
        ]
        for note in samples:
            await ws.send(json.dumps(note))
            ack = json.loads(await ws.recv())
            print(f"[ack]  {ack['notification']['type']}: {ack['notification']['message']}")


if __name__ == "__main__":
    asyncio.run(main())
