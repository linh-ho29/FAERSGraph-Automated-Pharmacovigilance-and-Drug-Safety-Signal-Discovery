from typing import Any

from pydantic import BaseModel


class OpenFDAResultsMeta(BaseModel):
    skip: int = 0
    limit: int = 0
    total: int = 0


class OpenFDAMeta(BaseModel):
    disclaimer: str = ""
    license: str = ""
    last_updated: str = ""
    results: OpenFDAResultsMeta = OpenFDAResultsMeta()


class OpenFDAResponse(BaseModel):
    """Loose response wrapper. `results` is kept as `list[dict]` (not strictly typed) so the raw
    storage layer can persist exactly what openFDA returned, without pydantic silently dropping
    unknown/variable fields. Strict typing happens downstream only where needed (RawSafetyReport,
    classification)."""

    meta: OpenFDAMeta
    results: list[dict[str, Any]] = []
