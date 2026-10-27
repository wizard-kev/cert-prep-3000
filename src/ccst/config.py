"""Settings, read from environment variables (and an optional .env file at the project root)."""

import os
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _load_dotenv(path: Path) -> None:
    """Minimal .env loader: KEY=VALUE lines; real environment variables win."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv(PROJECT_ROOT / ".env")


def _path(name: str, default: str) -> Path:
    p = Path(os.environ.get(name, default))
    return p if p.is_absolute() else PROJECT_ROOT / p


def _port(default: int = 8000) -> int:
    raw = os.environ.get("CCST_PORT", "").strip()
    if not raw:
        return default
    if not raw.isdigit() or not 1024 <= int(raw) <= 65535:
        raise ValueError(f"CCST_PORT must be a number from 1024 to 65535, got {raw!r}")
    return int(raw)


@dataclass(frozen=True)
class Settings:
    # The app always listens on 127.0.0.1 only; this is just the port.
    port: int = _port()
    objectives_dir: Path = _path("CCST_OBJECTIVES_DIR", "Objective Documents")
    data_dir: Path = _path("CCST_DATA_DIR", "data")

    @property
    def questions_dir(self) -> Path:
        return self.data_dir / "questions"


settings = Settings()
