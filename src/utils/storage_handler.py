"""
Parquet I/O utility for saving and loading DataFrames.

Uses fastparquet engine. Optional S3 sync when STORAGE_MODE=S3 via CloudStorageProvider.
"""
import logging
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)


class CloudStorageProvider:
    """S3 upload/download using credentials from src.core.config. Logs simulated if no credentials."""

    def __init__(self):
        from src.core.config import (
            AWS_ACCESS_KEY_ID,
            AWS_SECRET_ACCESS_KEY,
            AWS_REGION,
            S3_BUCKET_NAME,
        )
        self.bucket = S3_BUCKET_NAME
        self.region = AWS_REGION
        self.access_key = AWS_ACCESS_KEY_ID
        self.secret_key = AWS_SECRET_ACCESS_KEY

    def _has_credentials(self) -> bool:
        return bool(self.access_key and self.secret_key and self.bucket)

    def upload(self, local_path: Path, s3_key: str) -> None:
        if self._has_credentials():
            import boto3
            client = boto3.client(
                "s3",
                region_name=self.region,
                aws_access_key_id=self.access_key,
                aws_secret_access_key=self.secret_key,
            )
            client.upload_file(str(local_path), self.bucket, s3_key)
        else:
            logger.info("S3 upload simulated: %s", s3_key)

    def download(self, s3_key: str, local_path: Path) -> None:
        if self._has_credentials():
            import boto3
            client = boto3.client(
                "s3",
                region_name=self.region,
                aws_access_key_id=self.access_key,
                aws_secret_access_key=self.secret_key,
            )
            local_path.parent.mkdir(parents=True, exist_ok=True)
            client.download_file(self.bucket, s3_key, str(local_path))
        else:
            logger.info("S3 download simulated: %s", s3_key)


class StorageGateway:
    """Facade for parquet save/load with optional S3 sync."""

    @staticmethod
    def save_to_parquet(df: pd.DataFrame, path: str | Path) -> None:
        save_to_parquet(df, path)

    @staticmethod
    def read_from_parquet(path: str | Path) -> pd.DataFrame:
        return read_from_parquet(path)


def _s3_key_for_path(path: Path) -> str:
    from src.core.config import DATA_DIR
    try:
        return path.resolve().relative_to(DATA_DIR.resolve()).as_posix()
    except ValueError:
        return path.name


def save_to_parquet(df: pd.DataFrame, path: str | Path) -> None:
    """Save DataFrame to parquet; create parent directories if needed. Logs row count and path at DEBUG."""
    from src.core.config import STORAGE_MODE
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, engine="fastparquet", index=True)
    logger.debug("Saved %d rows to %s", len(df), path)
    if STORAGE_MODE == "S3":
        CloudStorageProvider().upload(path, _s3_key_for_path(path))


def read_from_parquet(path: str | Path) -> pd.DataFrame:
    """Load DataFrame from parquet. Raises FileNotFoundError if path does not exist. Logs row count and path at DEBUG."""
    from src.core.config import STORAGE_MODE
    path = Path(path)
    if STORAGE_MODE == "S3":
        CloudStorageProvider().download(_s3_key_for_path(path), path)
    if not path.exists():
        raise FileNotFoundError(f"Parquet file not found: {path}")
    df = pd.read_parquet(path, engine="fastparquet")
    logger.debug("Loaded %d rows from %s", len(df), path)
    return df
