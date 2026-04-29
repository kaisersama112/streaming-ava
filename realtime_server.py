#!/usr/bin/env python3

from app import app

if __name__ == "__main__":
    import uvicorn
    from config import settings

    host = getattr(settings.server, "host", "0.0.0.0")
    port = int(getattr(settings.server, "port", 7000))
    uvicorn.run(app, host=host, port=port, reload=getattr(settings.server, "reload", False))

