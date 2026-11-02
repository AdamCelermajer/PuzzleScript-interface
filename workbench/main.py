import os
import threading

import uvicorn


if __name__ == "__main__":
    # Build the diary's run index (slow: every run's token logs) before the first page asks for it.
    from workbench.diary import run_index
    threading.Thread(target=run_index, daemon=True).start()
    uvicorn.run(
        "workbench.app:app",
        host="127.0.0.1",
        port=int(os.getenv("WORKBENCH_API_PORT", "8010")),
    )
