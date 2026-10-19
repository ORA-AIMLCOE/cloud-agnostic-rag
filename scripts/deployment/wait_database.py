"""Wait for the private database tunnel without logging credentials."""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402
from app.core.config import Settings  # noqa: E402


def main():
    engine = create_engine(Settings().database_url, poolclass=NullPool,
                           connect_args={"connect_timeout": 5}, hide_parameters=True)
    try:
        for _ in range(12):
            try:
                with engine.connect() as connection:
                    connection.execute(text("SELECT 1"))
                print("Private database connection ready.")
                return 0
            except Exception:
                time.sleep(2)
        print("Private database unavailable. Check AWS login and aws-rag-tunnel.service.")
        return 1
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
