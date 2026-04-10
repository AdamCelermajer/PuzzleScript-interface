import os

from puzzlescript_arc.app import app


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("ARC_PROXY_PORT", "8000")))
