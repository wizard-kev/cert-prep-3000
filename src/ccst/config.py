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


@dataclass(frozen=True)
class Settings:
    provider: str = os.environ.get("CCST_PROVIDER", "ollama")
    ollama_url: str = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
    ollama_model: str = os.environ.get("OLLAMA_MODEL", "qwen3:4b")
    ollama_num_ctx: int = int(os.environ.get("OLLAMA_NUM_CTX", "12288"))
    ollama_timeout_s: float = float(os.environ.get("OLLAMA_TIMEOUT_S", "1800"))
    batch_size: int = int(os.environ.get("CCST_BATCH_SIZE", "5"))
    max_batch_size: int = 10
    # Minimum seconds between generation runs (SR5).
    generate_cooldown_s: float = float(os.environ.get("CCST_GENERATE_COOLDOWN_S", "10"))
    objectives_dir: Path = _path("CCST_OBJECTIVES_DIR", "Objective Documents")
    data_dir: Path = _path("CCST_DATA_DIR", "data")

    @property
    def questions_dir(self) -> Path:
        return self.data_dir / "questions"


settings = Settings()
