"""PandaAI data-skills client (Data Agent tool layer).

Every fetched datum is normalized into an :class:`EvidenceItem` with a
server-generated ``evidenceId`` so lens outputs can reference data through the
same ``references.evidenceIds`` discipline the engine already enforces —
without touching any database ledger.

Official access path (per pandaaiquant.com/data-service/api-docs) is the
synchronous ``panda_data`` Python SDK with ``init_token`` credential auth —
that lives in :class:`SdkPandaClient` (SDK calls run in a worker thread).
:class:`HttpPandaClient` remains as a REST fallback should the track expose
one, and :class:`FixturePandaClient` keeps tests and offline runs network- and
key-free (fixtures never impersonate live data: ``origin`` says so).
"""

from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Protocol, runtime_checkable

import httpx

from app.a2a.config import A2ASettings


@dataclass(frozen=True, slots=True)
class EvidenceItem:
    """One normalized market-data observation usable as lens evidence."""

    evidence_id: str
    kind: str  # e.g. quote | financial | factor | index | calendar
    subject: str  # instrument / index / entity the datum describes
    summary: str  # compact human-readable rendering for prompts
    payload: dict[str, Any]  # raw normalized fields (kept small)
    source: str  # e.g. "pandaai:quote/daily"
    origin: str  # "live" or "fixture"


@dataclass(frozen=True, slots=True)
class DataRequest:
    """What the Planner asked the Data Agent to fetch."""

    kind: str
    subject: str
    params: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class PandaDataClient(Protocol):
    """Stable seam between the pipeline and any PandaAI transport."""

    name: str

    async def fetch(self, request: DataRequest) -> list[EvidenceItem]: ...


def _summarize(payload: dict[str, Any], limit: int = 400) -> str:
    parts = [f"{key}={value}" for key, value in payload.items()]
    text = ", ".join(parts)
    return text if len(text) <= limit else text[: limit - 1] + "…"


class SdkPandaClient:
    """Official ``panda_data`` SDK binding (init_token + per-kind getters).

    The SDK is synchronous and returns pandas DataFrames; every call runs in
    ``asyncio.to_thread`` so the event loop (and A2A status streaming) never
    blocks. ``init_token`` happens once per process behind a lock. Rows are
    truncated to the most recent ``_MAX_ROWS`` so prompts stay bounded.
    """

    name = "pandaai-sdk"

    _MAX_ROWS = 12
    _token_lock = threading.Lock()
    _token_ready = False

    def __init__(self, settings: A2ASettings) -> None:
        if not settings.panda_username or not settings.panda_password:
            raise ValueError("PANDAAI_USERNAME / PANDAAI_PASSWORD are not configured")
        self._username = settings.panda_username
        self._password = settings.panda_password
        self._counter = 0

    def _ensure_token(self) -> None:
        """Thread-side: authenticate once; credential failures must surface."""

        import panda_data

        with SdkPandaClient._token_lock:
            if SdkPandaClient._token_ready:
                return
            try:
                panda_data.init_token(
                    username=self._username, password=self._password
                )
            except Exception as exc:
                raise PermissionError(
                    f"panda_data init_token failed: {type(exc).__name__}"
                ) from exc
            SdkPandaClient._token_ready = True

    @staticmethod
    def _default_window(days: int = 120) -> tuple[str, str]:
        end = datetime.now()
        start = end - timedelta(days=days)
        return start.strftime("%Y%m%d"), end.strftime("%Y%m%d")

    @staticmethod
    def _default_quarters() -> tuple[str, str]:
        now = datetime.now()
        end_q = f"{now.year}q{(now.month - 1) // 3 + 1}"
        start_year = now.year - 1
        start_q = f"{start_year}q{(now.month - 1) // 3 + 1}"
        return start_q, end_q

    def _call_sdk(self, request: DataRequest) -> Any:
        """Thread-side: dispatch one request to the matching SDK getter."""

        import panda_data

        self._ensure_token()
        params = dict(request.params)
        start_date, end_date = self._default_window()
        start_date = str(params.pop("start_date", start_date))
        end_date = str(params.pop("end_date", end_date))

        if request.kind == "quote":
            return panda_data.get_stock_daily(
                symbol=[request.subject], start_date=start_date, end_date=end_date
            )
        if request.kind == "index":
            return panda_data.get_index_daily(
                symbol=[request.subject], start_date=start_date, end_date=end_date
            )
        if request.kind == "factor":
            factors = params.pop(
                "factors", ["close", "volume", "market_cap", "turnover"]
            )
            return panda_data.get_factor(
                symbol=request.subject,
                start_date=start_date,
                end_date=end_date,
                factors=list(factors),
                type=str(params.pop("type", "stock")),
            )
        if request.kind == "financial":
            start_quarter, end_quarter = self._default_quarters()
            return panda_data.get_fina_reports(
                symbol=request.subject,
                start_quarter=str(params.pop("start_quarter", start_quarter)),
                end_quarter=str(params.pop("end_quarter", end_quarter)),
            )
        if request.kind == "calendar":
            return panda_data.get_trade_cal(
                start_date=start_date,
                end_date=end_date,
                exchange=str(params.pop("exchange", "SH")),
                is_trading_day=1,
            )
        return None

    def _rows(self, frame: Any) -> list[dict[str, Any]]:
        if frame is None:
            return []
        try:
            if hasattr(frame, "empty") and frame.empty:
                return []
            if hasattr(frame, "sort_values") and "date" in getattr(frame, "columns", []):
                frame = frame.sort_values("date")
            tail = frame.tail(self._MAX_ROWS) if hasattr(frame, "tail") else frame
            records = tail.to_dict("records") if hasattr(tail, "to_dict") else []
        except Exception:  # noqa: BLE001 - malformed frame degrades to no evidence
            return []
        cleaned: list[dict[str, Any]] = []
        for row in records:
            cleaned.append(
                {
                    str(key): (None if value != value else value)  # NaN -> None
                    for key, value in row.items()
                }
            )
        return cleaned

    async def fetch(self, request: DataRequest) -> list[EvidenceItem]:
        try:
            frame = await asyncio.to_thread(self._call_sdk, request)
        except PermissionError:
            raise
        except Exception:  # noqa: BLE001 - one bad request must not kill the run
            return []
        items: list[EvidenceItem] = []
        for row in self._rows(frame):
            self._counter += 1
            items.append(
                EvidenceItem(
                    evidence_id=f"ev-panda-{request.kind}-{self._counter:04d}",
                    kind=request.kind,
                    subject=request.subject,
                    summary=_summarize(row),
                    payload=row,
                    source=f"pandaai-sdk:{request.kind}",
                    origin="live",
                )
            )
        return items


class HttpPandaClient:
    """Async REST client for the PandaAI market/factor data API.

    Endpoint paths are intentionally centralized in ``_ENDPOINTS`` so aligning
    with the official docs is a one-table edit. Failures degrade to an empty
    evidence list (the pipeline reports data gaps instead of crashing), except
    for authentication problems which raise so misconfiguration is visible.
    """

    name = "pandaai-http"

    # kind -> relative path; adjust to the official PandaAI data API docs.
    _ENDPOINTS: dict[str, str] = {
        "quote": "/api/v1/market/quote",
        "financial": "/api/v1/fundamental/financial",
        "factor": "/api/v1/factor/values",
        "index": "/api/v1/index/quote",
        "calendar": "/api/v1/calendar/trading-days",
    }

    def __init__(self, settings: A2ASettings) -> None:
        if not settings.panda_base_url:
            raise ValueError("PANDAAI_DATA_BASE_URL is not configured")
        self._base_url = settings.panda_base_url
        self._api_key = settings.panda_api_key
        self._timeout = settings.panda_timeout_seconds
        self._counter = 0

    def _next_evidence_id(self, kind: str) -> str:
        self._counter += 1
        return f"ev-panda-{kind}-{self._counter:04d}"

    async def fetch(self, request: DataRequest) -> list[EvidenceItem]:
        path = self._ENDPOINTS.get(request.kind)
        if path is None:
            return []
        headers = {"Authorization": f"Bearer {self._api_key}"} if self._api_key else {}
        params: dict[str, Any] = {"symbol": request.subject, **request.params}
        async with httpx.AsyncClient(
            base_url=self._base_url, timeout=self._timeout, headers=headers
        ) as client:
            try:
                response = await client.get(path, params=params)
            except httpx.HTTPError:
                return []
        if response.status_code in (401, 403):
            raise PermissionError(
                f"PandaAI data API rejected credentials (HTTP {response.status_code})"
            )
        if response.status_code != 200:
            return []
        try:
            body = response.json()
        except ValueError:
            return []
        return self._normalize(request, body)

    def _normalize(self, request: DataRequest, body: Any) -> list[EvidenceItem]:
        """Flatten common ``{data: [...]}`` / list / object bodies into evidence."""

        rows: list[dict[str, Any]]
        if isinstance(body, dict):
            data = body.get("data", body)
            if isinstance(data, list):
                rows = [row for row in data if isinstance(row, dict)]
            elif isinstance(data, dict):
                rows = [data]
            else:
                rows = []
        elif isinstance(body, list):
            rows = [row for row in body if isinstance(row, dict)]
        else:
            rows = []

        items: list[EvidenceItem] = []
        for row in rows[:50]:  # keep prompt sizes bounded
            items.append(
                EvidenceItem(
                    evidence_id=self._next_evidence_id(request.kind),
                    kind=request.kind,
                    subject=request.subject,
                    summary=_summarize(row),
                    payload=row,
                    source=f"pandaai:{request.kind}",
                    origin="live",
                )
            )
        return items


@dataclass(slots=True)
class FixturePandaClient:
    """Deterministic offline client; canned rows keyed by ``(kind, subject)``."""

    name: str = "pandaai-fixture"
    responses: dict[tuple[str, str], list[dict[str, Any]]] = field(default_factory=dict)
    _counter: int = 0

    def register(self, kind: str, subject: str, rows: list[dict[str, Any]]) -> None:
        self.responses[(kind, subject)] = rows

    async def fetch(self, request: DataRequest) -> list[EvidenceItem]:
        rows = self.responses.get((request.kind, request.subject), [])
        items: list[EvidenceItem] = []
        for row in rows:
            self._counter += 1
            items.append(
                EvidenceItem(
                    evidence_id=f"ev-fixture-{request.kind}-{self._counter:04d}",
                    kind=request.kind,
                    subject=request.subject,
                    summary=_summarize(row),
                    payload=dict(row),
                    source=f"fixture:{request.kind}",
                    origin="fixture",
                )
            )
        return items
