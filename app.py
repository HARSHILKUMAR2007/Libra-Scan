"""Application entrypoint for running the LibraScan server."""

import os
import uvicorn
from app.main import app

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    host = os.environ.get("HOST", "0.0.0.0" if os.environ.get("PORT") else "127.0.0.1")
    reload = os.environ.get("APP_ENV", "development").lower() != "production" and not os.environ.get("PORT")
    uvicorn.run("app.main:app", host=host, port=port, reload=reload)