from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class OpenFDAMetaSnapshot(BaseModel):
    disclaimer: str
    license: str
    last_updated: str
    results_total: int


class ProvenanceEnvelope(BaseModel):
    """Captures everything needed to reproduce and audit a single openFDA fetch."""

    batch_id: str
    query_search: str
    query_limit: int
    query_skip: int
    retrieved_at: datetime
    openfda_meta: OpenFDAMetaSnapshot
    source_url: str


class RawSafetyReport(BaseModel):
    """Minimally-typed view used only to extract lineage keys and classification inputs.

    Deliberately permissive (`extra="allow"`): the verbatim dict persisted to raw storage is the
    source of truth, this model just gives typed access to the handful of fields the pipeline
    needs to navigate (lineage keys, patient/drug/reaction walking).
    """

    model_config = ConfigDict(extra="allow")

    safetyreportid: str
    safetyreportversion: str
    receivedate: str | None = None
    receiptdate: str | None = None
    serious: str | None = None
    patient: dict[str, Any] = {}
