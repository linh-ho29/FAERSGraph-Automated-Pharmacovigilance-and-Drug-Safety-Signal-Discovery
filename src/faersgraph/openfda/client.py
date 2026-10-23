import logging
from collections.abc import Iterator
from typing import Any

import httpx
from tenacity import Retrying, retry_if_exception_type, stop_after_attempt, wait_exponential
from tenacity.wait import wait_base

from faersgraph.config import Settings
from faersgraph.openfda.models import OpenFDAMeta, OpenFDAResponse, OpenFDAResultsMeta
from faersgraph.openfda.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)


class OpenFDARequestError(Exception):
    """Non-retryable error from the openFDA API (unexpected 4xx, malformed response, etc.)."""


class RateLimitedError(Exception):
    def __init__(self, retry_after: float | None = None):
        self.retry_after = retry_after
        super().__init__(f"openFDA rate limited; retry_after={retry_after}")


class TransientServerError(Exception):
    """A 5xx response -- retryable, unlike other 4xx errors."""


class _WaitForRetryAfterOrFallback(wait_base):
    """Honors a RateLimitedError's Retry-After value when present, else exponential backoff."""

    def __init__(self, fallback: wait_base):
        self._fallback = fallback

    def __call__(self, retry_state: Any) -> float:
        exc = retry_state.outcome.exception() if retry_state.outcome else None
        if isinstance(exc, RateLimitedError) and exc.retry_after is not None:
            return exc.retry_after
        return self._fallback(retry_state)


def _safe_json(response: httpx.Response) -> dict[str, Any] | None:
    try:
        return response.json()
    except ValueError:
        return None


def _empty_response() -> OpenFDAResponse:
    return OpenFDAResponse(meta=OpenFDAMeta(results=OpenFDAResultsMeta(skip=0, limit=0, total=0)))


class OpenFDAClient:
    """Thin wrapper over the openFDA drug/event.json endpoint with rate limiting, retry/backoff,
    and clean pagination termination. Every real HTTP call (including retries) goes through
    `rate_limiter.acquire()` first, so the limiter governs wall-clock request pacing, not just
    logical "requests"."""

    def __init__(
        self,
        settings: Settings,
        rate_limiter: RateLimiter,
        http_client: httpx.Client | None = None,
    ):
        self.settings = settings
        self._settings = settings
        self._rate_limiter = rate_limiter
        self._http = http_client or httpx.Client(timeout=settings.http_timeout_seconds)

    def _build_params(self, search: str, limit: int, skip: int) -> dict[str, Any]:
        params: dict[str, Any] = {"limit": limit, "skip": skip}
        if search:
            params["search"] = search
        if self._settings.openfda_api_key:
            params["api_key"] = self._settings.openfda_api_key
        return params

    def _fetch_page_once(self, search: str, limit: int, skip: int) -> OpenFDAResponse:
        self._rate_limiter.acquire()
        params = self._build_params(search, limit, skip)
        response = self._http.get(self._settings.openfda_base_url, params=params)

        if response.status_code == 429:
            retry_after_header = response.headers.get("Retry-After")
            retry_after = float(retry_after_header) if retry_after_header else None
            raise RateLimitedError(retry_after=retry_after)

        if response.status_code == 404:
            body = _safe_json(response)
            error_code = ((body or {}).get("error") or {}).get("code")
            if error_code == "NOT_FOUND":
                # openFDA's normal way of saying "zero results for this search" -- not an error.
                return _empty_response()
            raise OpenFDARequestError(f"openFDA 404: {response.text}")

        if response.status_code >= 500:
            raise TransientServerError(f"openFDA {response.status_code}: {response.text}")
        if not response.is_success:
            raise OpenFDARequestError(f"openFDA {response.status_code}: {response.text}")

        return OpenFDAResponse.model_validate(response.json())

    def fetch_page(self, search: str, limit: int, skip: int) -> OpenFDAResponse:
        retrying = Retrying(
            retry=retry_if_exception_type((httpx.TransportError, RateLimitedError, TransientServerError)),
            wait=_WaitForRetryAfterOrFallback(wait_exponential(multiplier=1, min=1, max=60)),
            stop=stop_after_attempt(self._settings.http_max_retries),
            reraise=True,
        )
        return retrying(self._fetch_page_once, search, limit, skip)

    def iter_reports(
        self,
        search: str = "",
        page_size: int | None = None,
        max_skip: int | None = None,
    ) -> Iterator[OpenFDAResponse]:
        """Yields one OpenFDAResponse per page, advancing skip until results are exhausted, the
        reported total is reached, or the openFDA pagination skip ceiling is hit."""
        page_size = page_size or self._settings.openfda_page_size
        max_skip = max_skip if max_skip is not None else self._settings.openfda_max_skip
        skip = 0
        while True:
            page = self.fetch_page(search, page_size, skip)
            yield page
            if not page.results:
                break
            total = page.meta.results.total
            skip += page_size
            if skip >= total:
                break
            if skip > max_skip:
                logger.warning(
                    "Stopping pagination at skip=%s (max_skip=%s) for search=%r; "
                    "narrow the search query to retrieve the remaining %s results.",
                    skip,
                    max_skip,
                    search,
                    max(total - skip, 0),
                )
                break
