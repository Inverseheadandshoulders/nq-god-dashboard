"""
NQ GOD v5 - GEX Computation Engine
==================================
Compatible with app.py's compute_gex_snapshot(theta_client, symbol, bucket, settings) signature.

Calculates:
- Net GEX (Call GEX - Put GEX)  
- Gross GEX (Call GEX + Put GEX)
- Zero Gamma (interpolated crossing point)
- Call/Put walls (max GEX at strike)
- Cluster zones (high gamma concentration)
"""

import math
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass


@dataclass
class ComputeSettings:
    """Settings for GEX computation"""
    min_oi: int = 100
    min_volume: int = 10
    strike_range_pct: float = 0.20  # 20% above/below spot
    include_weeklies: bool = True
    include_monthlies: bool = True
    gamma_multiplier: float = 100.0


def compute_gex_snapshot(
    theta_client,
    symbol: str,
    bucket: str = "TOTAL",
    settings: ComputeSettings = None
) -> Dict[str, Any]:
    """
    Compute full GEX snapshot from ThetaData.
    
    Args:
        theta_client: ThetaClient instance
        symbol: Ticker symbol (e.g., 'SPY')
        bucket: Filter by expiration ('0DTE', 'WEEKLY', 'MONTHLY', 'TOTAL')
        settings: ComputeSettings instance
    
    Returns:
        Complete GEX analysis
    """
    if settings is None:
        settings = ComputeSettings()
    
    ts = datetime.now().isoformat()
    
    # Get spot price
    try:
        spot = theta_client.get_spot(symbol)
        if not spot or spot <= 0:
            return _empty_snapshot(0, bucket, ts)
    except Exception as e:
        print(f"[GEX] Failed to get spot for {symbol}: {e}")
        return _empty_snapshot(0, bucket, ts)
    
    # Get expirations
    try:
        expirations = theta_client.list_expirations(symbol)
        if not expirations:
            return _empty_snapshot(spot, bucket, ts)
    except Exception as e:
        print(f"[GEX] Failed to get expirations for {symbol}: {e}")
        return _empty_snapshot(spot, bucket, ts)
    
    # Filter expirations by bucket
    filtered_exps = _filter_expirations(expirations, bucket)
    if not filtered_exps:
        return _empty_snapshot(spot, bucket, ts)
    
    # Fetch contracts from ThetaData
    all_contracts = []
    for exp in filtered_exps[:5]:  # Limit for performance
        try:
            greeks = theta_client.get_all_greeks(symbol, exp)
            if greeks:
                for g in greeks:
                    g['exp'] = exp
                    # Normalize OI field name
                    if 'open_interest' in g and 'oi' not in g:
                        g['oi'] = g['open_interest']
                all_contracts.extend(greeks)
        except Exception as e:
            print(f"[GEX] Failed to get greeks for {symbol} exp {exp}: {e}")
            continue
    
    if not all_contracts:
        print(f"[GEX] No contracts found for {symbol}")
        return _empty_snapshot(spot, bucket, ts)
    
    print(f"[GEX] {symbol}: {len(all_contracts)} contracts from {len(filtered_exps)} expirations")
    
    # Build strike-level data
    by_strike = _aggregate_by_strike(all_contracts, spot, settings)
    
    if not by_strike:
        return _empty_snapshot(spot, bucket, ts)
    
    # Sort strikes
    strikes = sorted(by_strike.keys())
    
    # Extract arrays
    call_gex = [by_strike[k]["call_gex"] for k in strikes]
    put_gex = [by_strike[k]["put_gex"] for k in strikes]
    net_gex = [by_strike[k]["net_gex"] for k in strikes]
    call_oi = [by_strike[k]["call_oi"] for k in strikes]
    put_oi = [by_strike[k]["put_oi"] for k in strikes]
    
    # Compute summary metrics
    total_call_gex = sum(call_gex)
    total_put_gex = sum(put_gex)
    total_net_gex = total_call_gex - total_put_gex
    total_gross_gex = total_call_gex + total_put_gex
    
    # Find key levels
    gamma_flip = _compute_gamma_flip(strikes, net_gex, spot)
    call_wall = _find_max_gex_strike(strikes, call_gex)
    put_wall = _find_max_gex_strike(strikes, put_gex)
    max_gamma = _find_max_abs_gex_strike(strikes, net_gex)
    
    # Determine regime
    regime = "POSITIVE_GAMMA" if total_net_gex > 0 else "NEGATIVE_GAMMA"
    
    # Put/Call ratio
    total_call_oi = sum(call_oi)
    total_put_oi = sum(put_oi)
    pc_ratio = total_put_oi / total_call_oi if total_call_oi > 0 else 1.0
    
    # Find clusters
    clusters = _find_cluster_zones(strikes, call_gex, put_gex, spot)
    
    # Build levels
    levels = [
        {"label": "Gamma Flip", "value": gamma_flip, "type": "flip"},
        {"label": "Call Wall", "value": call_wall, "type": "call"},
        {"label": "Put Wall", "value": put_wall, "type": "put"},
        {"label": "Max Gamma", "value": max_gamma, "type": "max"}
    ]
    
    return {
        "meta": {
            "ts": ts,
            "spot": spot,
            "bucket": bucket,
            "contract_count": len(all_contracts)
        },
        "profile": {
            "strikes": strikes,
            "net_gex": net_gex,
            "call_gex": call_gex,
            "put_gex": put_gex,
            "call_oi": call_oi,
            "put_oi": put_oi
        },
        "summary": {
            "net_gex": total_net_gex,
            "gross_gex": total_gross_gex,
            "call_gex_total": total_call_gex,
            "put_gex_total": total_put_gex,
            "gamma_flip": gamma_flip,
            "call_wall": call_wall,
            "put_wall": put_wall,
            "max_gamma": max_gamma,
            "regime": regime,
            "pc_ratio": pc_ratio,
            "clusters": clusters
        },
        "levels": levels,
        "clusters": clusters
    }


def build_heatmap_or_surface(
    theta_client,
    symbol: str,
    mode: str = "heatmap",
    settings: ComputeSettings = None
) -> Dict[str, Any]:
    """Build heatmap or vol surface data."""
    if settings is None:
        settings = ComputeSettings()
    
    try:
        spot = theta_client.get_spot(symbol)
        expirations = theta_client.list_expirations(symbol)
    except Exception as e:
        return {"error": str(e), "data": []}
    
    if not spot or not expirations:
        return {"error": "No data", "data": []}
    
    data = []
    for exp in expirations[:8]:
        try:
            greeks = theta_client.get_all_greeks(symbol, exp)
            for g in greeks:
                strike = g.get("strike", 0)
                if abs(strike - spot) / spot > settings.strike_range_pct:
                    continue
                data.append({
                    "exp": exp,
                    "strike": strike,
                    "right": g.get("right"),
                    "iv": g.get("iv", 0),
                    "gamma": g.get("gamma", 0),
                    "delta": g.get("delta", 0),
                    "oi": g.get("oi") or g.get("open_interest", 0)
                })
        except:
            continue
    
    return {"spot": spot, "data": data}


def _filter_expirations(expirations: List[int], bucket: str) -> List[int]:
    """Filter expirations by bucket."""
    if bucket == "TOTAL":
        return expirations
    
    today = int(datetime.now().strftime("%Y%m%d"))
    result = []
    
    for exp in expirations:
        try:
            exp_date = datetime.strptime(str(exp), "%Y%m%d").date()
            today_date = datetime.strptime(str(today), "%Y%m%d").date()
            dte = (exp_date - today_date).days
            
            if bucket == "0DTE" and dte == 0:
                result.append(exp)
            elif bucket == "WEEKLY" and dte <= 7:
                result.append(exp)
            elif bucket == "MONTHLY" and dte <= 30:
                result.append(exp)
        except:
            continue
    
    return result if result else expirations[:3]


def _aggregate_by_strike(contracts: List[Dict], spot: float, settings: ComputeSettings) -> Dict[float, Dict]:
    """Aggregate GEX by strike price."""
    by_strike = {}
    
    # Debug: Sample first contract to see field names
    if contracts:
        sample = contracts[0]
        print(f"[GEX DEBUG] Sample contract fields: {list(sample.keys())[:10]}")
        print(f"[GEX DEBUG] Sample values - strike: {sample.get('strike')}, gamma: {sample.get('gamma')}, oi: {sample.get('oi') or sample.get('open_interest')}, right: {sample.get('right')}")
    
    filtered_count = {"no_strike": 0, "out_of_range": 0, "low_oi": 0, "added": 0}
    
    for c in contracts:
        strike = c.get("strike", 0)
        if not strike or strike <= 0:
            filtered_count["no_strike"] += 1
            continue
        
        # Filter by range - be more permissive (30% range)
        if abs(strike - spot) / spot > 0.30:
            filtered_count["out_of_range"] += 1
            continue
        
        right = str(c.get("right", "")).upper()
        oi = c.get("oi") or c.get("open_interest", 0) or 0
        gamma = c.get("gamma", 0) or 0
        
        # Lower OI filter for after-hours (use 1 instead of 100)
        if oi < 1:
            filtered_count["low_oi"] += 1
            continue
        
        filtered_count["added"] += 1
        
        # GEX = Gamma × OI × spot × multiplier
        # If gamma is 0 (after-hours), estimate from delta/IV if available
        if gamma == 0:
            # Simple approximation: use OI as proxy for importance
            gex = oi * spot * 0.001  # Scaled proxy
        else:
            gex = gamma * oi * spot * settings.gamma_multiplier
        
        if strike not in by_strike:
            by_strike[strike] = {
                "call_gex": 0, "put_gex": 0, "net_gex": 0,
                "call_oi": 0, "put_oi": 0
            }
        
        if right == "C":
            by_strike[strike]["call_gex"] += gex
            by_strike[strike]["call_oi"] += oi
            by_strike[strike]["net_gex"] += gex
        elif right == "P":
            by_strike[strike]["put_gex"] += gex
            by_strike[strike]["put_oi"] += oi
            by_strike[strike]["net_gex"] -= gex
    
    print(f"[GEX DEBUG] Filter stats: {filtered_count}, resulting strikes: {len(by_strike)}")
    return by_strike


def _compute_gamma_flip(strikes: List[float], net_gex: List[float], spot: float) -> float:
    """Find zero gamma crossing point."""
    if len(strikes) < 2:
        return spot
    
    for i in range(1, len(net_gex)):
        prev_gex = net_gex[i - 1]
        curr_gex = net_gex[i]
        
        if (prev_gex > 0 and curr_gex <= 0) or (prev_gex <= 0 and curr_gex > 0):
            prev_strike = strikes[i - 1]
            curr_strike = strikes[i]
            
            denom = curr_gex - prev_gex
            if abs(denom) < 1e-10:
                return (prev_strike + curr_strike) / 2
            
            ratio = abs(prev_gex) / abs(denom)
            return round(prev_strike + ratio * (curr_strike - prev_strike), 2)
    
    return spot


def _find_max_gex_strike(strikes: List[float], gex_values: List[float]) -> Optional[float]:
    """Find strike with maximum GEX."""
    if not strikes or not gex_values:
        return None
    
    max_idx = 0
    max_val = gex_values[0]
    
    for i, val in enumerate(gex_values):
        if val > max_val:
            max_val = val
            max_idx = i
    
    return strikes[max_idx] if max_val > 0 else None


def _find_max_abs_gex_strike(strikes: List[float], net_gex: List[float]) -> Optional[float]:
    """Find strike with maximum absolute net GEX."""
    if not strikes or not net_gex:
        return None
    
    max_idx = 0
    max_val = abs(net_gex[0])
    
    for i, val in enumerate(net_gex):
        if abs(val) > max_val:
            max_val = abs(val)
            max_idx = i
    
    return strikes[max_idx]


def _find_cluster_zones(strikes: List[float], call_gex: List[float], put_gex: List[float], spot: float) -> List[Dict]:
    """Find zones of concentrated gamma."""
    if len(strikes) < 3:
        return []
    
    total_gex = [c + p for c, p in zip(call_gex, put_gex)]
    
    sorted_gex = sorted(total_gex, reverse=True)
    threshold_idx = max(1, int(len(sorted_gex) * 0.15))
    threshold = sorted_gex[threshold_idx]
    
    if threshold <= 0:
        return []
    
    clusters = []
    in_cluster = False
    cluster_strikes = []
    cluster_gex = []
    cluster_start = 0
    
    for i, (strike, gex) in enumerate(zip(strikes, total_gex)):
        if gex >= threshold:
            if not in_cluster:
                in_cluster = True
                cluster_start = i
                cluster_strikes = []
                cluster_gex = []
            cluster_strikes.append(strike)
            cluster_gex.append(gex)
        else:
            if in_cluster and cluster_strikes:
                peak_idx = cluster_gex.index(max(cluster_gex))
                clusters.append({
                    "start": cluster_strikes[0],
                    "end": cluster_strikes[-1],
                    "peak_strike": cluster_strikes[peak_idx],
                    "total_gex": sum(cluster_gex),
                    "type": "CALL" if call_gex[cluster_start + peak_idx] > put_gex[cluster_start + peak_idx] else "PUT"
                })
                in_cluster = False
    
    if in_cluster and cluster_strikes:
        peak_idx = cluster_gex.index(max(cluster_gex))
        clusters.append({
            "start": cluster_strikes[0],
            "end": cluster_strikes[-1],
            "peak_strike": cluster_strikes[peak_idx],
            "total_gex": sum(cluster_gex),
            "type": "CALL" if call_gex[cluster_start + peak_idx] > put_gex[cluster_start + peak_idx] else "PUT"
        })
    
    clusters.sort(key=lambda x: x["total_gex"], reverse=True)
    return clusters[:5]


def _empty_snapshot(spot: float, bucket: str, ts: str) -> Dict[str, Any]:
    """Return empty snapshot structure."""
    return {
        "meta": {"ts": ts, "spot": spot, "bucket": bucket, "contract_count": 0},
        "profile": {
            "strikes": [], "net_gex": [], "call_gex": [], "put_gex": [],
            "call_oi": [], "put_oi": []
        },
        "summary": {
            "net_gex": 0, "gross_gex": 0, "gamma_flip": spot,
            "call_wall": None, "put_wall": None, "max_gamma": spot,
            "regime": "UNKNOWN", "pc_ratio": 1.0, "clusters": []
        },
        "levels": [],
        "clusters": []
    }
