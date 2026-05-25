# Notify Server

A WebSocket server with session-based authentication. The client authenticates
once over REST to get a token, then opens a persistent WebSocket connection and
streams `notifications` in real time. The server always listens, stores each
notification, and replies with an `ack`.

## Architecture

The system separates two responsibilities:

| Layer        | Protocol                    | Role                                              |
|--------------|-----------------------------|---------------------------------------------------|
| Auth         | `PUT /auth/session` (REST)  | One-off request: username + password → token      |
| Notifications| `WS /ws?token=...` (WebSocket) | Persistent connection: client pushes notifications |

The `session` is the bridge: the `PUT` issues a `token`, and the `token` opens
the WebSocket.

```
client ──PUT /auth/session (user, pass)──▶ server
client ◀──────── { session_id, token } ──── server
client ──WS connect ?token=...──────────▶ server   (connection stays open)
client ──{ type, message, data }────────▶ server
client ◀──────────────── { ack, ... } ──── server
```

Once connected, the server also pushes a periodic heartbeat notification so the
client knows it is still connected.

## Project structure

```
notify-server/
├── app/
│   ├── main.py                # FastAPI entrypoint + /health
│   ├── config.py              # env-based settings
│   ├── schemas.py             # Pydantic models (auth + notifications)
│   ├── security.py            # bcrypt hashing + token generation
│   ├── store.py               # interfaces + in-memory implementation (swappable)
│   ├── connection_manager.py  # live WebSocket connection management
│   └── routes.py              # PUT endpoint + WebSocket endpoint
├── client/
│   └── test_client.py         # CLI test client
├── requirements.txt
└── .env.example
```

## Running

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Run the server
uvicorn app.main:app --reload --port 8000

# 3. In a second terminal — run the test client
python client/test_client.py
```

Demo user: `avi` / `secret123` (defined in `store.py`).

## Notes for production (next steps)

- **Storage**: currently in-memory — data is wiped on every restart. The
  implementations sit behind `SessionStore` / `NotificationStore`, so you can
  swap to Redis (sessions) and Firestore (notifications) without touching the
  logic.
- **Bidirectional push**: `ConnectionManager.send_to_user()` is already in place —
  the hook for when you want the server to push notifications *to* a user.
- **Scale**: multiple uvicorn workers will need Redis Pub/Sub to sync WS
  connections across processes.
- **Security**: rate-limit the `PUT`, use `wss://` (TLS) in production, and add
  token refresh.
