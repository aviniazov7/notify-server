from fastapi import FastAPI

from .config import Settings
from .config import settings as default_settings
from .connection_manager import ConnectionManager
from .routes import router
from .store import InMemoryNotificationStore, InMemorySessionStore, InMemoryUserStore


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build an app with its own settings and stores.

    Each instance gets fresh state, so tests can run isolated apps with
    overridden settings (e.g. a short session TTL).
    """
    settings = settings or default_settings

    app = FastAPI(title=settings.app_name)
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
