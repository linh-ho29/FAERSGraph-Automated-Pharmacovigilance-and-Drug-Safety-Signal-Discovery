from functools import lru_cache
from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="FAERSGRAPH_", extra="ignore")

    openfda_base_url: str = "https://api.fda.gov/drug/event.json"
    openfda_api_key: str | None = None
    openfda_rate_limit_per_min: int = 240
    openfda_rate_limit_per_day: int = 1000
    openfda_page_size: int = 100
    openfda_max_skip: int = 25000

    rxnorm_base_url: str = "https://rxnav.nlm.nih.gov/REST"
    rxnorm_timeout_seconds: float = 10.0

    http_timeout_seconds: float = 30.0
    http_max_retries: int = 5

    data_dir: Path = Path("data")
    raw_dir: Path | None = None
    processed_dir: Path | None = None
    db_path: Path | None = None

    log_level: str = "INFO"

    @model_validator(mode="after")
    def _derive_paths(self) -> "Settings":
        if self.raw_dir is None:
            self.raw_dir = self.data_dir / "raw"
        if self.processed_dir is None:
            self.processed_dir = self.data_dir / "processed"
        if self.db_path is None:
            self.db_path = self.data_dir / "db" / "faersgraph.sqlite"
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
