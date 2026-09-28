# Notify Server

[![CI](https://github.com/aviniazov7/notify-server/actions/workflows/ci.yml/badge.svg)](https://github.com/aviniazov7/notify-server/actions/workflows/ci.yml)

A real-time notification server built with **FastAPI** and **WebSockets**, using
session-based authentication. A client logs in once over REST to get a token, then
opens a persistent WebSocket and streams notifications. The server validates and
stores each one and replies with an `ack`. It also pushes its own `connected` and
`heartbeat` events.

```
client ──PUT /auth/session {username, password}──▶ server
client ◀──────────── {session_id, token, expires_at} ── server
client ──WS /ws?token=...─────────────────────────▶ server   (connection stays open)
client ◀──────────── {type: "notification", connected} ─ server
client ──{type, message, data}────────────────────▶ server
client ◀──────────── {type: "ack", notification} ──── server
client ◀──────────── {type: "notification", heartbeat} ─ server   (every HEARTBEAT_SECONDS)
client ──DELETE /auth/session (Bearer token)──────▶ server   (socket closed: 1000 "logged out")
```

## API

All routes except `/health` are under `API_PREFIX` (default `/api/v1`).
Interactive docs are served at `/docs`.

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/health` | – | Liveness check → `{"status": "ok"}` |
| `PUT` | `/api/v1/auth/session` | – | Log in with `{username, password}` → `{session_id, token, expires_at}`. `401` on bad credentials. |
| `DELETE` | `/api/v1/auth/session` | Bearer | Log out: invalidates the token and closes WebSockets opened with it. `204`. |
| `GET` | `/api/v1/notifications` | Bearer | The caller's stored notification history, oldest first. |
| `WS` | `/api/v1/ws?token=<token>` | Query token | Persistent channel. Invalid or expired token → close code `1008`. |

Bearer endpoints expect `Authorization: Bearer <token>` and return `401` with
`WWW-Authenticate: Bearer` when the token is missing, invalid or expired.

### WebSocket messages

Client → server:

```json
{"type": "trade_signal", "message": "BTC long @ 65000", "data": {"rr": 2.5}}
```

Server → client:

| `type` | When |
|---|---|
| `notification` | Server push: `connected` on open (stored), `heartbeat` periodically (not stored) |
| `ack` | Your notification was validated and stored. Includes the stored record. |
| `error` | `invalid JSON`, `invalid notification` (the socket stays open), or `session expired` (then closed with `1008`) |

## Running

### Locally

Requires Python 3.12 (see `.python-version`).

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # sets the demo account DEMO_USERNAME / DEMO_PASSWORD

python -m app                 # serves on HOST:PORT from settings (default 0.0.0.0:8000)
# or, with auto-reload:
uvicorn app.main:app --reload
```

In a second terminal, run the demo client. It logs in with the demo account, sends
notifications (including one invalid one), prints acks and skips pushed heartbeats:

```bash
python -m client.test_client
```

### With Docker

```bash
cp .env.example .env
docker compose up --build
curl localhost:8000/health
```

The image is based on `python:3.12-slim`, runs as an unprivileged user and has a
`HEALTHCHECK` on `/health`.

### Tests and lint

```bash
pip install -r requirements-dev.txt
pytest -v
ruff check . && ruff format --check .
```

The tests use FastAPI's `TestClient` (including `websocket_connect`) against isolated
app instances. They cover login, bad and expired tokens (handshake and mid-connection),
acks, invalid payloads and malformed frames, notification history, logout, and a
check that tokens and passwords never reach the logs. CI runs both on every PR.

## Configuration

Settings come from environment variables or `.env` (see `.env.example`).

| Variable | Default | Description |
|---|---|---|
| `API_PREFIX` | `/api/v1` | Prefix for API routes |
| `SESSION_TTL_SECONDS` | `3600` | Session lifetime |
| `HEARTBEAT_SECONDS` | `10` | Interval of the heartbeat push |
| `LOG_LEVEL` | `INFO` | Level for the `app` loggers |
| `DEMO_USERNAME` / `DEMO_PASSWORD` | unset | Demo account seeded on startup, only if both are set |
| `HOST` / `PORT` | `0.0.0.0` / `8000` | Bind address for `python -m app` |

## Project structure

```
notify-server/
├── app/
│   ├── __main__.py            # `python -m app` → uvicorn with settings host/port
│   ├── main.py                # create_app() factory: state, lifespan seed, routes, /health
│   ├── config.py              # env-based settings (pydantic-settings)
│   ├── routes.py              # auth, notifications history, WebSocket endpoint
│   ├── schemas.py             # Pydantic request/response models
│   ├── security.py            # bcrypt hashing + token generation
│   ├── store.py               # store interfaces + in-memory implementations
│   ├── connection_manager.py  # live sockets indexed by user and by session
│   └── logging_config.py      # logging setup + token redaction filter
├── client/test_client.py      # CLI demo client
├── tests/                     # pytest suite
├── Dockerfile, docker-compose.yml
└── .github/workflows/ci.yml   # ruff + pytest
```

## Design decisions

**Opaque session tokens instead of JWT.** The token is 256 bits from
`secrets.token_urlsafe(32)` and means nothing on its own. The server looks it up in
the session store. The trade-off is one store lookup per request, and in return:

- **Instant revocation.** Logout deletes the session, and the token stops working
  immediately, even for an already open WebSocket. A JWT stays valid until it expires
  unless you add a denylist, which is a server-side lookup anyway.
- **Long-lived connections.** A WebSocket can outlive any token expiry checked at the
  handshake. Because the session is re-checked on every message, expiry and logout
  take effect mid-connection.
- **No signing key to manage or rotate, and no claims to leak.**

JWT becomes the better fit when many independent services must verify identity
without a shared session store.

**Repository pattern for storage.** Routes depend only on the abstract `UserStore`,
`SessionStore` and `NotificationStore` interfaces in `store.py`. Today they are
in-memory. A Redis session store or a database-backed notification store can replace
them in `create_app()` without touching route logic. The same seam keeps the tests
fast and hermetic.

**App factory with per-app state.** `create_app(settings)` builds an app with its own
stores and connection manager, so every test gets a fresh, isolated instance and can
override settings (for example a 1-second session TTL for the expiry tests).

**Secrets stay out of logs.** Only `session_id` (which cannot authenticate) is
logged. Uvicorn logs the raw WebSocket URL including `?token=...`, so a logging
filter redacts it to `token=***`. Passwords are stored only as bcrypt hashes, and the
demo password is held as a `SecretStr`.

## Next steps

- **Redis-backed stores.** Sessions with native TTL expiry, plus Redis Pub/Sub so
  multiple workers or instances can close and push to sockets they don't own. Today
  the state is in-memory and lives in a single process.
- **Rate limiting** on `PUT /auth/session` to slow down credential stuffing, for
  example per IP and per username.
- **Token out of the URL.** Pass the WebSocket token in a first message or in
  `Sec-WebSocket-Protocol` instead of the query string, and serve over `wss://` (TLS).
- Persistent notification storage with pagination on `GET /notifications`.

## License

[MIT](LICENSE)
