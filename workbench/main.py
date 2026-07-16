import os

import uvicorn


if __name__ == "__main__":
    uvicorn.run(
        "workbench.app:app",
        host="127.0.0.1",
        port=int(os.getenv("WORKBENCH_API_PORT", "8010")),
    )
