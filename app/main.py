from fastapi import FastAPI

from .config import settings
from .routes import router

app = FastAPI(title=settings.app_name)
app.include_router(router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
