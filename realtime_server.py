#!/usr/bin/env python3

# from app import app
import uvicorn
from configs import settings
from app import create_app

if __name__ == "__main__":
    host = settings.server.host
    port = settings.server.port
    uvicorn.run(create_app(), host=host, port=port)
