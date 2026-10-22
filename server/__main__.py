"""`python -m server` starts Aloud with the configuration from the environment."""

from __future__ import annotations

import uvicorn

from .config import Config


def main() -> None:
    config = Config.from_env()
    uvicorn.run(
        "server.main:app",
        host=config.host,
        port=config.port,
        log_level=config.log_level,
        access_log=False,
    )


if __name__ == "__main__":
    main()
