"""Run the server with host/port from settings: python -m app"""

import uvicorn

from .config import settings

if __name__ == "__main__":
    uvicorn.run("app.main:app", host=settings.host, port=settings.port)
