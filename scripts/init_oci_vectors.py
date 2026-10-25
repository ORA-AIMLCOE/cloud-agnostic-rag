"""Initialize Oracle metadata, history and native vector tables in the application schema."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.providers.oci.database import create_oracle_engine, initialize_schema

if __name__ == "__main__":
    engine = create_oracle_engine()
    try:
        initialize_schema(engine)
    except Exception:
        print("Oracle schema initialization failed. Check connectivity, privileges, storage quota and AI Vector Search support.", file=sys.stderr)
        raise SystemExit(1) from None
    finally:
        engine.dispose()
    print("Oracle metadata, history and AI Vector Search schema initialized.")
