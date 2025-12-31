from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Any, Deque, Dict, List, Optional, Tuple


@dataclass
class StoredSnapshot:
    symbol: str
    bucket: str
    ts: str  # ISO timestamp
    payload: Dict[str, Any]


class SnapshotStore:
    """In-memory snapshot storage.

    For a production service you'd move this to Redis / Postgres / S3,
    but this is perfect for local testing and initial deployment.
    """

    def __init__(self, max_per_key: int = 500) -> None:
        self.max_per_key = max_per_key
        self._store: Dict[Tuple[str, str], Deque[StoredSnapshot]] = defaultdict(lambda: deque(maxlen=max_per_key))
        self._alerts: Deque[Dict[str, Any]] = deque(maxlen=2000)

    def add_snapshot(self, symbol: str, bucket: str, ts: str, payload: Dict[str, Any]) -> None:
        key = (symbol.upper(), bucket.upper())
        self._store[key].append(StoredSnapshot(symbol=symbol.upper(), bucket=bucket.upper(), ts=ts, payload=payload))

    def latest(self, symbol: str, bucket: str) -> Optional[Dict[str, Any]]:
        key = (symbol.upper(), bucket.upper())
        if not self._store[key]:
            return None
        return self._store[key][-1].payload

    def get_by_ts(self, symbol: str, bucket: str, ts: str) -> Optional[Dict[str, Any]]:
        key = (symbol.upper(), bucket.upper())
        for item in reversed(self._store[key]):
            if item.ts == ts:
                return item.payload
        return None

    def history_points(self, symbol: str, bucket: str, limit: int = 200) -> List[Dict[str, Any]]:
        key = (symbol.upper(), bucket.upper())
        items = list(self._store[key])[-limit:]
        out: List[Dict[str, Any]] = []
        for it in items:
            meta = it.payload.get("meta", {})
            summ = it.payload.get("summary", {})
            out.append(
                {
                    "ts": meta.get("ts", it.ts),
                    "spot": meta.get("spot"),
                    "net_gex": summ.get("net_gex"),
                    "gross_gex": summ.get("gross_gex"),
                }
            )
        return out

    # ---- alerts ----

    def add_alerts(self, alerts: List[Dict[str, Any]]) -> None:
        for a in alerts:
            self._alerts.appendleft(a)

    def recent_alerts(self, symbol: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        out = []
        for a in list(self._alerts):
            if symbol and (a.get("symbol") or "").upper() != symbol.upper():
                continue
            out.append(a)
            if len(out) >= limit:
                break
        return out
