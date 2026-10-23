from enum import Enum


class ReactionOutcome(str, Enum):
    RECOVERED_RESOLVED = "1"
    RECOVERING_RESOLVING = "2"
    NOT_RECOVERED_NOT_RESOLVED = "3"
    RECOVERED_WITH_SEQUELAE = "4"
    FATAL = "5"
    UNKNOWN = "6"


class SeriousnessReason(str, Enum):
    DEATH = "seriousnessdeath"
    HOSPITALIZATION = "seriousnesshospitalization"
    LIFE_THREATENING = "seriousnesslifethreatening"
    DISABLING = "seriousnessdisabling"
    CONGENITAL_ANOMALY = "seriousnesscongenitalanomali"
    OTHER = "seriousnessother"


class DrugCharacterization(str, Enum):
    SUSPECT = "1"
    CONCOMITANT = "2"
    INTERACTING = "3"


class TermSourceStatus(str, Enum):
    MEDDRA_HIERARCHY_UNAVAILABLE = "meddra_hierarchy_unavailable"
    MEDDRA_HIERARCHY_LOCAL = "meddra_hierarchy_local"
    RXNORM_MATCHED = "rxnorm_matched"
    RXNORM_UNMATCHED = "rxnorm_unmatched"
