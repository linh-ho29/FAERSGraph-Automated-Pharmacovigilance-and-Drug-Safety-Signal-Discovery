from dataclasses import dataclass
from enum import Enum
from typing import Literal

Confidence = Literal["high", "medium", "low"]


class DrugClass(str, Enum):
    PEPTIDE = "peptide"
    PROTEIN = "protein"
    SIRNA = "sirna"
    SMALL_MOLECULE = "small_molecule"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ClassificationResult:
    drug_class: DrugClass
    confidence: Confidence
    matched_rule: str
