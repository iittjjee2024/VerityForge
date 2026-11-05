"""Live entrypoint: loads .env BEFORE the app builds its gateway. Run: uvicorn verityforge.live:app.

Kept separate from main.py so the test suite (which imports main) never picks up real keys or live mode."""
import os
from pathlib import Path


def load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    for line in path.read_text("utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


load_dotenv(Path(os.getenv("VERITYFORGE_ENV_FILE", ".env")))

from .main import app  # noqa: E402,F401
