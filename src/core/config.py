"""
Environment-level configuration: .env loading and base path resolution.

Single source of truth for env vars and data paths. YAML config remains in
src/utils/config_manager.py. All values are computed at module import time.
"""
from pathlib import Path
import os

from dotenv import load_dotenv

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(dotenv_path=_PROJECT_ROOT / ".env")

TIINGO_API_KEY: str | None = os.getenv("TIINGO_API_KEY")
MARKETAUX_API_KEY: str | None = os.getenv("MARKETAUX_API_KEY")

if os.getenv("DATA_DIR") is not None:
    DATA_DIR: Path = Path(os.getenv("DATA_DIR"))
else:
    DATA_DIR: Path = _PROJECT_ROOT / "data"

NEWS_DIR: Path = DATA_DIR / "news"

# Storage mode and S3
_STORAGE_MODE_RAW = os.getenv("STORAGE_MODE", "LOCAL")
if _STORAGE_MODE_RAW not in ("LOCAL", "S3"):
    raise ValueError(f"STORAGE_MODE must be LOCAL or S3, got: {_STORAGE_MODE_RAW!r}")
STORAGE_MODE: str = _STORAGE_MODE_RAW

if STORAGE_MODE == "LOCAL":
    BASE_DATA_PATH: Path = DATA_DIR
else:
    BASE_DATA_PATH = Path(os.getenv("S3_BUCKET_NAME", "s3-bucket-not-set"))

AWS_ACCESS_KEY_ID: str | None = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY: str | None = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_REGION: str = os.getenv("AWS_REGION", "us-east-1")
S3_BUCKET_NAME: str | None = os.getenv("S3_BUCKET_NAME")
