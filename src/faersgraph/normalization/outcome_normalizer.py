from faersgraph.models.enums import ReactionOutcome, SeriousnessReason


def normalize_outcome_code(code: str | None) -> ReactionOutcome | None:
    if code is None:
        return None
    try:
        return ReactionOutcome(str(code))
    except ValueError:
        return None


def normalize_seriousness(report: dict) -> tuple[bool | None, list[SeriousnessReason]]:
    """FAERS' top-level `serious` field is '1' (serious) or '2' (not serious), sometimes absent.
    Each `seriousness*` flag is '1' when that specific reason applies, else absent."""
    serious_raw = report.get("serious")
    if serious_raw == "1":
        serious: bool | None = True
    elif serious_raw == "2":
        serious = False
    else:
        serious = None

    reasons = [reason for reason in SeriousnessReason if report.get(reason.value) == "1"]
    return serious, reasons
