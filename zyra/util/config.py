import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


class ZyraConfig(dict):
    def __init__(self) -> None:
        env_path = Path("config.env")
        if not env_path.exists():
            env_path = Path(".env")

        load_dotenv(env_path, override=True)

        get = os.environ.get

        try:
            owner_id = int(get("OWNER_ID") or 0)
        except ValueError:
            raise SystemExit("Invalid OWNER_ID")

        if not owner_id:
            raise SystemExit("Missing OWNER_ID environment variable")

        bot_token = get("BOT_TOKEN") or SystemExit(
            "Missing BOT_TOKEN environment variable"
        )
        db_uri = get("DB_URI") or SystemExit("Missing DB_URI environment variable")

        prefix = get("COMMAND_PREFIX", "/")
        prefix = [p.strip() for p in prefix.split(",")] if "," in prefix else prefix

        config = {
            "bot": {
                "db_uri": db_uri,
                "prefix": prefix,
                "colorlog": get("COLORLOG", "false").lower() in ("true", "1", "yes"),
                "download_path": str(
                    Path(get("DOWNLOAD_PATH", Path.home() / "downloads"))
                ),
            },
            "telegram": {"token": bot_token, "base_url": get("TELEGRAM_BASE_URL")},
            "rank": {"owner_id": owner_id},
        }

        super().__init__(config)

    def __setitem__(self, *_: Any) -> None:
        raise RuntimeError("Configuration is read-only during runtime.")

    def __delitem__(self, *_: Any) -> None:
        raise RuntimeError("Configuration is read-only during runtime.")
