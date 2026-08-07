import asyncio
import logging
import os

from src.bot import Bot
from src.pkg.db import DbContext

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)


def parse_allowed_ids(raw: str) -> set[int]:
    """Разбирает ALLOWED_IDS вида "163787127, 42" в набор telegram id."""
    return {int(chunk) for chunk in raw.replace(",", " ").split()}


def main() -> None:
    token = os.getenv("TOKEN", "")
    if not token:
        raise ValueError("Token is not set")

    DB_URI = os.getenv("DB_URI", "postgresql://local:local@localhost:5435/local")
    if not token:
        raise ValueError("DB_URI is not set")

    allowed_ids = parse_allowed_ids(os.getenv("ALLOWED_IDS", ""))
    if not allowed_ids:
        raise ValueError("ALLOWED_IDS is not set")

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    db = loop.run_until_complete(DbContext.create(DB_URI))

    Bot.create(token, db, allowed_ids).run()


if __name__ == "__main__":
    main()
