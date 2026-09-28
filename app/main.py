from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from .config import Settings
from .config import settings as default_settings
from .connection_manager import ConnectionManager
from .logging_config import setup_logging
from .routes import router
from .store import InMemoryNotificationStore, InMemorySessionStore, InMemoryUserStore


def _seed_demo_user(app: FastAPI) -> None:
    """Create the demo account from DEMO_USERNAME / DEMO_PASSWORD, if configured."""
    settings: Settings = app.state.settings
    if settings.demo_username and settings.demo_password:
        app.state.users.add(settings.demo_username, settings.demo_password.get_secret_value())


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build an app with its own settings and stores.

    Each instance gets fresh state, so tests can run isolated apps with
    overridden settings (e.g. a short session TTL).
    """
    settings = settings or default_settings
    setup_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        _seed_demo_user(app)
        yield

    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    app.state.settings = settings

    # Swap these to move to Redis/Firestore — routes only depend on the interfaces.
    app.state.users = InMemoryUserStore()
    app.state.sessions = InMemorySessionStore()
    app.state.notifications = InMemoryNotificationStore()
    app.state.manager = ConnectionManager()

    app.include_router(router, prefix=settings.api_prefix)

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    return app


app = create_app()
