import httpx
from pydantic import BaseModel
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_fixed

from faersgraph.config import Settings


class RxNormCandidate(BaseModel):
    rxcui: str
    score: int
    rxaui: str | None = None


class RxNormClient:
    """Free NLM RxNorm (RxNav) REST client -- no API key required. RxNav has no published hard
    rate limit but is a shared NIH resource; a lightweight fixed-wait retry is polite enough
    without needing the persisted daily-quota machinery the openFDA client needs."""

    def __init__(self, settings: Settings, http_client: httpx.Client | None = None):
        self._settings = settings
        self._http = http_client or httpx.Client(timeout=settings.rxnorm_timeout_seconds)

    @retry(
        retry=retry_if_exception_type(httpx.TransportError),
        wait=wait_fixed(0.5),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    def approximate_match(self, term: str, max_entries: int = 5) -> list[RxNormCandidate]:
        url = f"{self._settings.rxnorm_base_url}/approximateTerm.json"
        response = self._http.get(url, params={"term": term, "maxEntries": max_entries})
        response.raise_for_status()
        data = response.json()
        raw_candidates = ((data.get("approximateGroup") or {}).get("candidate")) or []

        candidates: list[RxNormCandidate] = []
        for raw in raw_candidates:
            rxcui = raw.get("rxcui")
            if not rxcui:
                continue
            try:
                score = int(raw.get("score") or 0)
            except (TypeError, ValueError):
                score = 0
            candidates.append(RxNormCandidate(rxcui=rxcui, score=score, rxaui=raw.get("rxaui")))

        candidates.sort(key=lambda c: c.score, reverse=True)
        return candidates

    @retry(
        retry=retry_if_exception_type(httpx.TransportError),
        wait=wait_fixed(0.5),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    def get_ingredient_name(self, rxcui: str) -> str | None:
        url = f"{self._settings.rxnorm_base_url}/rxcui/{rxcui}/property.json"
        response = self._http.get(url, params={"propName": "RxNorm Name"})
        response.raise_for_status()
        data = response.json()
        concepts = ((data.get("propConceptGroup") or {}).get("propConcept")) or []
        if not concepts:
            return None
        return concepts[0].get("propValue")
