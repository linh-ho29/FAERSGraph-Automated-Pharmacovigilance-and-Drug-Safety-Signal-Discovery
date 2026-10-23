from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel

from faersgraph.classification.types import DrugClass

from .enums import DrugCharacterization, ReactionOutcome, SeriousnessReason, TermSourceStatus


class NormalizedDrug(BaseModel):
    raw_medicinalproduct: str | None = None
    raw_generic_name: str | None = None
    raw_substance_name: str | None = None
    rxcui: str | None = None
    rxnorm_normalized_name: str | None = None
    normalization_status: TermSourceStatus
    drug_class: DrugClass
    drug_class_confidence: Literal["high", "medium", "low"]
    drug_class_matched_rule: str
    drugcharacterization: DrugCharacterization | None = None
    indication_raw: str | None = None
    indication_normalized: str | None = None


class NormalizedReaction(BaseModel):
    meddrapt_raw: str
    meddrapt_normalized: str
    term_source_status: TermSourceStatus
    outcome: ReactionOutcome | None = None


class NormalizedReport(BaseModel):
    safetyreportid: str
    safetyreportversion: str
    receivedate: date | None = None
    receiptdate: date | None = None
    serious: bool | None = None
    seriousness_reasons: list[SeriousnessReason] = []
    drugs: list[NormalizedDrug] = []
    reactions: list[NormalizedReaction] = []
    batch_id: str
    normalized_at: datetime
