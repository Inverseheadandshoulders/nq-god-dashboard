from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests


@dataclass(frozen=True)
class AlertRuleSettings:
    """Tune these later. Defaults are conservative."""

    # Alert when total net GEX changes by more than this fraction.
    net_gex_change_pct_threshold: float = 0.35
    # Alert when Gamma Flip moves more than this fraction of spot price.
    gamma_flip_shift_pct_threshold: float = 0.004
    # Alert when Call/Put Wall move by more than this many points.
    wall_shift_points_threshold: float = 10.0


def _pct_change(prev: float, cur: float) -> float:
    if prev == 0:
        return 0.0
    return (cur - prev) / abs(prev)


def compute_alerts(
    prev_snapshot: Optional[Dict[str, Any]],
    cur_snapshot: Dict[str, Any],
    settings: AlertRuleSettings,
) -> List[Dict[str, Any]]:
    """Return a list of alert objects based on the diff between prev and current."""
    if not prev_snapshot:
        return []

    prev_sum = prev_snapshot.get("summary", {})
    cur_sum = cur_snapshot.get("summary", {})

    alerts: List[Dict[str, Any]] = []

    # 1) Total net GEX sign flip
    prev_net = float(prev_sum.get("net_gex", 0.0) or 0.0)
    cur_net = float(cur_sum.get("net_gex", 0.0) or 0.0)
    if (prev_net <= 0 < cur_net) or (prev_net >= 0 > cur_net):
        alerts.append(
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "type": "NET_GEX_FLIP",
                "title": "Net GEX flipped sign",
                "detail": f"{prev_net:,.0f} → {cur_net:,.0f}",
                "symbol": cur_snapshot.get("meta", {}).get("symbol"),
                "bucket": cur_snapshot.get("meta", {}).get("bucket"),
            }
        )

    # 2) Large net change
    pct = abs(_pct_change(prev_net, cur_net))
    if pct >= settings.net_gex_change_pct_threshold:
        alerts.append(
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "type": "NET_GEX_SPIKE",
                "title": "Large Net GEX change",
                "detail": f"Δ {pct*100:.0f}% ({prev_net:,.0f} → {cur_net:,.0f})",
                "symbol": cur_snapshot.get("meta", {}).get("symbol"),
                "bucket": cur_snapshot.get("meta", {}).get("bucket"),
            }
        )

    # 3) Gamma flip moved
    prev_flip = prev_sum.get("gamma_flip")
    cur_flip = cur_sum.get("gamma_flip")
    spot = float(cur_snapshot.get("meta", {}).get("spot", 0.0) or 0.0)
    if prev_flip is not None and cur_flip is not None and spot > 0:
        prev_flip_f = float(prev_flip)
        cur_flip_f = float(cur_flip)
        if abs(cur_flip_f - prev_flip_f) >= settings.gamma_flip_shift_pct_threshold * spot:
            alerts.append(
                {
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "type": "GAMMA_FLIP_SHIFT",
                    "title": "Gamma Flip moved",
                    "detail": f"{prev_flip_f:.2f} → {cur_flip_f:.2f} (spot {spot:.2f})",
                    "symbol": cur_snapshot.get("meta", {}).get("symbol"),
                    "bucket": cur_snapshot.get("meta", {}).get("bucket"),
                }
            )

    # 4) Walls moved
    for key, label in [("call_wall", "Call Wall"), ("put_wall", "Put Wall")]:
        prev_wall = prev_sum.get(key)
        cur_wall = cur_sum.get(key)
        if prev_wall is None or cur_wall is None:
            continue
        prev_wall_f = float(prev_wall)
        cur_wall_f = float(cur_wall)
        if abs(cur_wall_f - prev_wall_f) >= settings.wall_shift_points_threshold:
            alerts.append(
                {
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "type": "WALL_SHIFT",
                    "title": f"{label} moved",
                    "detail": f"{prev_wall_f:.2f} → {cur_wall_f:.2f}",
                    "symbol": cur_snapshot.get("meta", {}).get("symbol"),
                    "bucket": cur_snapshot.get("meta", {}).get("bucket"),
                }
            )

    return alerts


def maybe_send_discord(webhook_url: Optional[str], alerts: List[Dict[str, Any]]) -> None:
    """Send each alert to Discord webhook if configured."""
    if not webhook_url or not alerts:
        return

    for a in alerts:
        try:
            title = a.get("title", "Alert")
            symbol = a.get("symbol", "")
            bucket = a.get("bucket", "")
            detail = a.get("detail", "")

            payload = {
                "content": None,
                "embeds": [
                    {
                        "title": f"{symbol} · {title}",
                        "description": f"**Bucket:** {bucket}\n**Detail:** {detail}",
                        "timestamp": a.get("ts"),
                    }
                ],
            }
            requests.post(webhook_url, json=payload, timeout=10)
        except Exception:
            # don't crash ingest for alert failures
            pass
