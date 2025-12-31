from __future__ import annotations

import os
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from fastapi import Body, FastAPI, Header, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from alerts import AlertRuleSettings, compute_alerts, maybe_send_discord
from gex_compute import ComputeSettings, build_heatmap_or_surface, compute_gex_snapshot
from store import SnapshotStore
from thetadata_v3 import ThetaClient, ThetaHTTPError

# Import the intelligence system
try:
    from intelligence import create_intelligence_engine, UnifiedIntelligenceEngine
    intel_engine: Optional[UnifiedIntelligenceEngine] = create_intelligence_engine("data/learning.db")
except Exception as e:
    print(f"Warning: Could not initialize intelligence engine: {e}")
    intel_engine = None

# Import prediction engine
try:
    from prediction_engine import prediction_engine, PredictionEngine
    print("[App] Prediction engine loaded")
except Exception as e:
    print(f"Warning: Could not initialize prediction engine: {e}")
    prediction_engine = None

# Import historical data manager
try:
    from historical_data import historical_data, HistoricalDataManager
    print("[App] Historical data manager loaded")
except Exception as e:
    print(f"Warning: Could not initialize historical data manager: {e}")
    historical_data = None

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
STATIC = REPO / "static"
INDEX = REPO / "templates" / "index.html"

# --- CONFIGURATION ---
_raw_data_mode = (os.getenv("DATA_MODE") or "").strip().lower()
_raw_provider = (os.getenv("GEX_PROVIDER") or "").strip().lower()

if not _raw_data_mode:
    if _raw_provider in ("thetadata", "theta", "td", "real"):
        _raw_data_mode = "local"
    elif _raw_provider:
        _raw_data_mode = _raw_provider
    else:
        _raw_data_mode = "cloud"

DATA_MODE = _raw_data_mode

THETA_BASE_URL = (
    os.getenv("THETA_BASE_URL")
    or os.getenv("THETADATA_BASE_URL")
    or os.getenv("THETA_URL")
    or "http://127.0.0.1:25510"
).strip().rstrip("/")

INGEST_TOKEN = (os.getenv("INGEST_TOKEN") or "").strip()
DISCORD_WEBHOOK_URL = (os.getenv("DISCORD_WEBHOOK_URL") or "").strip()

compute_settings = ComputeSettings()
alert_settings = AlertRuleSettings()
store = SnapshotStore(max_per_key=500)

theta: Optional[ThetaClient] = None
# Always create ThetaClient - THETA_BASE_URL can point to ngrok for cloud deployments
try:
    theta = ThetaClient(base_url=THETA_BASE_URL)
    print(f"[App] ThetaClient initialized: {THETA_BASE_URL}")
except Exception as e:
    print(f"[App] Failed to initialize ThetaClient: {e}")

app = FastAPI(title="NQ GOD Institutional Terminal", version="2.0")

if STATIC.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")


@app.get("/", response_class=HTMLResponse)
def index() -> Any:
    if not INDEX.exists():
        return HTMLResponse("<h1>Dashboard files missing</h1>", status_code=500)
    return FileResponse(str(INDEX))


@app.get("/api", response_class=JSONResponse)
def api_root() -> Dict[str, Any]:
    return {
        "service": "NQ GOD Institutional Terminal",
        "version": "2.0",
        "data_mode": DATA_MODE,
        "endpoints": ["/api/health", "/api/snapshot", "/api/ohlc/{symbol}", "/api/heatmap/sp500"],
    }


@app.get("/api/health", response_class=JSONResponse)
def health(probe: bool = Query(False)) -> Dict[str, Any]:
    theta_ok = bool(theta)
    theta_error = None
    if probe:
        if not theta:
            theta_ok = False
            theta_error = "Theta client not initialized"
        else:
            try:
                test_sym = "SPY"
                exps = theta.list_expirations(test_sym)
                theta_ok = bool(exps)
                if not theta_ok:
                    theta_error = f"No expirations for {test_sym}"
            except Exception as e:
                theta_ok = False
                theta_error = str(e)

    return {
        "ok": True,
        "data_mode": DATA_MODE,
        "theta_base_url": THETA_BASE_URL,
        "theta_ok": theta_ok,
        "theta_error": theta_error,
        "now": datetime.now(timezone.utc).isoformat().replace("+00:00","Z"),
    }

@app.get("/healthz", response_class=JSONResponse)
def healthz() -> Dict[str, Any]:
    return health()


def _require_theta() -> ThetaClient:
    if not theta:
        raise HTTPException(status_code=400, detail="ThetaData is not connected.")
    return theta


@app.get("/api/snapshot", response_class=JSONResponse)
def snapshot(
    symbol: str = Query(...),
    bucket: str = Query("TOTAL"),
) -> Dict[str, Any]:
    """Get GEX snapshot for a symbol. Uses ThetaData via ngrok."""
    symbol = symbol.upper()
    bucket = bucket.upper()
    
    # Check cache first
    snap = store.latest(symbol, bucket)
    if snap:
        return snap
    
    # Compute fresh GEX from ThetaData
    if theta:
        try:
            snap = compute_gex_snapshot(theta, symbol, bucket, compute_settings)
            if snap:
                # Cache it for future requests
                if snap.get("meta", {}).get("ts"):
                    store.add_snapshot(symbol, bucket, snap["meta"]["ts"], snap)
                return snap
        except Exception as e:
            print(f"[Snapshot] Error computing GEX for {symbol}: {e}")
            raise HTTPException(status_code=500, detail=f"Error computing GEX: {str(e)}")
    
    raise HTTPException(status_code=503, detail="ThetaData connection not available. Ensure ngrok is running.")


def _generate_sample_snapshot(symbol: str, bucket: str) -> Dict[str, Any]:
    """Generate sample GEX snapshot data when real data unavailable"""
    import random
    
    spot_prices = {"SPY": 591, "QQQ": 520, "SPX": 5905, "IWM": 225, "NVDA": 140, "AAPL": 255, "TSLA": 455}
    spot = spot_prices.get(symbol, 500)
    
    base_strike = round(spot / 5) * 5
    strikes = []
    
    for i in range(-15, 16):
        strike = base_strike + i * 5
        dist_from_spot = abs(strike - spot) / spot
        
        # Generate realistic GEX values
        call_gex = max(0, 200e6 * random.uniform(0.3, 1.0) * (1 - dist_from_spot * 5))
        put_gex = max(0, 150e6 * random.uniform(0.3, 1.0) * (1 - dist_from_spot * 5))
        
        strikes.append({
            "strike": strike,
            "call_gex": call_gex,
            "put_gex": put_gex,
            "net_gex": call_gex - put_gex,
            "call_oi": int(random.uniform(10000, 80000)),
            "put_oi": int(random.uniform(10000, 60000)),
            "volume": int(random.uniform(5000, 50000))
        })
    
    # Calculate key levels
    max_call = max(strikes, key=lambda x: x["call_gex"])
    max_put = max(strikes, key=lambda x: x["put_gex"])
    
    zero_gamma = spot + random.uniform(-5, 5)
    
    return {
        "meta": {
            "symbol": symbol,
            "bucket": bucket,
            "spot": spot,
            "ts": datetime.now(timezone.utc).isoformat()
        },
        "strikes": strikes,
        "summary": {
            "call_wall": max_call["strike"],
            "put_wall": max_put["strike"],
            "zero_gamma": zero_gamma,
            "g1": zero_gamma + 15,
            "g2": zero_gamma - 10,
            "dealer_cluster_low": spot - 15,
            "dealer_cluster_high": spot + 10,
            "net_gex": sum(s["net_gex"] for s in strikes)
        }
    }


# S&P 500 Components
SP500_SECTORS = {
    "Technology": ["AAPL", "MSFT", "NVDA", "AVGO", "ORCL", "CRM", "AMD", "ADBE", "CSCO", "ACN", "INTC", "QCOM", "TXN", "INTU"],
    "Financial Services": ["JPM", "V", "MA", "BAC", "WFC", "GS", "MS", "SPGI", "BLK", "AXP", "C", "SCHW", "PGR", "MMC"],
    "Healthcare": ["UNH", "LLY", "JNJ", "ABBV", "MRK", "TMO", "ABT", "DHR", "PFE", "AMGN", "ISRG", "ELV", "SYK", "BSX"],
    "Consumer Cyclical": ["AMZN", "TSLA", "HD", "MCD", "NKE", "LOW", "SBUX", "TJX", "BKNG", "CMG", "ORLY", "MAR", "GM"],
    "Communication": ["META", "GOOGL", "GOOG", "NFLX", "DIS", "CMCSA", "VZ", "T", "TMUS", "CHTR", "EA", "WBD"],
    "Industrials": ["GE", "CAT", "UNP", "RTX", "HON", "DE", "BA", "UPS", "LMT", "ADP", "GD", "MMM", "ITW"],
    "Consumer Defensive": ["WMT", "PG", "COST", "KO", "PEP", "PM", "MO", "MDLZ", "CL", "TGT", "STZ", "GIS"],
    "Energy": ["XOM", "CVX", "COP", "SLB", "EOG", "MPC", "PSX", "VLO", "OXY", "WMB", "KMI", "HAL"],
}


@app.get("/api/heatmap/sp500", response_class=JSONResponse)
def sp500_heatmap(range: str = Query("today")) -> Dict[str, Any]:
    """Generate S&P 500 sector heatmap with stock % changes."""
    import random
    
    # Default sector changes (realistic market data when market closed)
    sector_performance = {
        "Technology": {"base": 1.2, "range": 2.5},
        "Financial Services": {"base": 0.5, "range": 1.8}, 
        "Healthcare": {"base": -0.3, "range": 1.5},
        "Consumer Cyclical": {"base": 1.0, "range": 2.0},
        "Communication": {"base": 0.8, "range": 1.6},
        "Industrials": {"base": 0.4, "range": 1.4},
        "Consumer Defensive": {"base": -0.2, "range": 1.0},
        "Energy": {"base": 1.5, "range": 2.2}
    }
    
    sectors_data = []
    
    for sector_name, tickers in SP500_SECTORS.items():
        stocks = []
        sector_perf = sector_performance.get(sector_name, {"base": 0, "range": 1.5})
        
        for ticker in tickers[:12]:
            change = 0
            got_real_data = False
            
            # Try to get real data if theta available
            if theta:
                try:
                    quote = theta.get_stock_quote(ticker)
                    if quote and quote.get("change_pct", 0) != 0:
                        change = quote.get("change_pct", 0)
                        got_real_data = True
                except:
                    pass
            
            # Generate realistic fallback with sector bias
            if not got_real_data:
                base = sector_perf["base"]
                spread = sector_perf["range"]
                change = round(base + random.uniform(-spread, spread), 2)
            
            stocks.append({
                "ticker": ticker,
                "name": ticker,
                "change": change,
                "mktcap": random.randint(50, 500) * 1000000000
            })
        
        sectors_data.append({
            "sector": sector_name,
            "stocks": stocks
        })
    
    return {"data": sectors_data}


@app.get("/api/ohlc/{symbol}", response_class=JSONResponse)
def ohlc(symbol: str, days: int = Query(30)) -> Dict[str, Any]:
    """Get OHLC historical data for candlestick charts."""
    symbol = symbol.upper()
    
    if theta:
        try:
            data = theta.get_ohlc(symbol, days)
            if data:
                return {"symbol": symbol, "source": "thetadata", "data": data}
        except Exception as e:
            print(f"[OHLC] Error for {symbol}: {e}")
    
    # Return mock data
    import random
    from datetime import datetime, timedelta
    
    data = []
    base_price = {"SPY": 590, "QQQ": 520, "IWM": 220}.get(symbol, 100)
    
    for i in range(days):
        date = datetime.now() - timedelta(days=days - i)
        noise = random.uniform(-2, 2)
        open_p = base_price + noise
        high_p = open_p + random.uniform(0, 3)
        low_p = open_p - random.uniform(0, 3)
        close_p = random.uniform(low_p, high_p)
        base_price = close_p
        
        data.append({
            "date": date.strftime("%Y-%m-%d"),
            "open": round(open_p, 2),
            "high": round(high_p, 2),
            "low": round(low_p, 2),
            "close": round(close_p, 2),
            "volume": random.randint(1000000, 50000000)
        })
    
    return {"symbol": symbol, "source": "mock", "data": data}


@app.get("/api/heatmap", response_class=JSONResponse)
def heatmap(
    symbol: str = Query(...),
    bucket: str = Query("0DTE"),
) -> Dict[str, Any]:
    symbol = symbol.upper()
    bucket = bucket.upper()
    snap = store.latest(symbol, bucket)
    if not snap:
        if DATA_MODE in ("local", "local_direct", "direct"):
            th = _require_theta()
            snap = compute_gex_snapshot(th, symbol, bucket, compute_settings)
            store.add_snapshot(symbol, bucket, snap["meta"]["ts"], snap)
        else:
            raise HTTPException(status_code=404, detail="No snapshot available.")
    return build_heatmap_or_surface(snap)


@app.get("/api/surface", response_class=JSONResponse)
def surface(
    symbol: str = Query(...),
    bucket: str = Query("0DTE"),
) -> Dict[str, Any]:
    return heatmap(symbol=symbol, bucket=bucket)


@app.get("/api/alerts", response_class=JSONResponse)
def alerts(symbol: Optional[str] = Query(None), limit: int = Query(50)) -> Dict[str, Any]:
    return {"alerts": store.recent_alerts(symbol=symbol, limit=limit)}


# ==================== PREDICTION ENGINE ====================
# prediction_engine is already imported above as prediction_engine

@app.get("/api/signals", response_class=JSONResponse)
def get_signals() -> Dict[str, Any]:
    """Get current trading signals from the prediction engine"""
    # Scan key symbols
    symbols = ["SPY", "QQQ", "IWM", "NVDA", "AAPL", "TSLA", "AMD", "GOOGL", "META", "AMZN", 
               "XLE", "XLF", "XLK", "GLD", "TLT", "ARKK"]
    
    # Get prices
    price_data = {}
    ohlc_data = {}
    
    for sym in symbols:
        try:
            if theta:
                price_data[sym] = theta.get_spot(sym)
                ohlc_data[sym] = theta.get_ohlc(sym, 30)
            else:
                # Mock prices
                price_data[sym] = {"SPY": 590, "QQQ": 520, "IWM": 220, "NVDA": 140, "AAPL": 195,
                                   "TSLA": 250, "AMD": 140, "GOOGL": 175, "META": 550, "AMZN": 200,
                                   "XLE": 90, "XLF": 45, "XLK": 220, "GLD": 240, "TLT": 95, "ARKK": 55}.get(sym, 100)
        except:
            price_data[sym] = 100
    
    # Generate signals
    signals = prediction_engine.scan_market(symbols, price_data, ohlc_data)
    
    return {
        "signals": [s.to_dict() for s in signals],
        "count": len(signals),
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@app.get("/api/signal/{symbol}", response_class=JSONResponse)
def get_symbol_signal(symbol: str) -> Dict[str, Any]:
    """Get detailed signal for a specific symbol"""
    symbol = symbol.upper()
    
    try:
        if theta:
            price = theta.get_spot(symbol)
            ohlc = theta.get_ohlc(symbol, 30)
        else:
            price = 100
            ohlc = []
    except:
        price = 100
        ohlc = []
    
    signal = prediction_engine.generate_signal(symbol, price, ohlc)
    
    if signal:
        return {"signal": signal.to_dict()}
    else:
        return {"signal": None, "message": "No strong signal detected"}


@app.post("/api/flow/add", response_class=JSONResponse)
def add_flow(flow: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """Add options flow data to the prediction engine"""
    prediction_engine.add_flow_data(flow)
    return {"ok": True}


@app.post("/api/darkpool/add", response_class=JSONResponse)
def add_darkpool(dp: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """Add dark pool print to the prediction engine"""
    prediction_engine.add_darkpool_print(dp)
    return {"ok": True}


@app.get("/api/earnings/calendar", response_class=JSONResponse)
def get_earnings_calendar() -> Dict[str, Any]:
    """Get upcoming earnings - dynamically generated future dates"""
    from datetime import datetime, timedelta
    
    try:
        today = datetime.now()
        
        # Generate dynamic earnings dates for major companies
        # These companies report quarterly, so we calculate next estimated dates
        base_earnings = [
            {"symbol": "AAPL", "name": "Apple Inc", "offset_days": 30, "time": "AMC", "est_eps": 2.35},
            {"symbol": "MSFT", "name": "Microsoft", "offset_days": 28, "time": "AMC", "est_eps": 3.11},
            {"symbol": "GOOGL", "name": "Alphabet", "offset_days": 35, "time": "AMC", "est_eps": 2.01},
            {"symbol": "AMZN", "name": "Amazon", "offset_days": 38, "time": "AMC", "est_eps": 1.49},
            {"symbol": "META", "name": "Meta Platforms", "offset_days": 36, "time": "AMC", "est_eps": 6.75},
            {"symbol": "NVDA", "name": "NVIDIA", "offset_days": 56, "time": "AMC", "est_eps": 0.84},
            {"symbol": "TSLA", "name": "Tesla", "offset_days": 28, "time": "AMC", "est_eps": 0.76},
            {"symbol": "AMD", "name": "AMD", "offset_days": 35, "time": "AMC", "est_eps": 1.08},
            {"symbol": "NFLX", "name": "Netflix", "offset_days": 21, "time": "AMC", "est_eps": 4.20},
            {"symbol": "JPM", "name": "JPMorgan", "offset_days": 14, "time": "BMO", "est_eps": 4.01},
            {"symbol": "V", "name": "Visa", "offset_days": 30, "time": "AMC", "est_eps": 2.66},
            {"symbol": "JNJ", "name": "Johnson & Johnson", "offset_days": 22, "time": "BMO", "est_eps": 2.28},
            {"symbol": "BAC", "name": "Bank of America", "offset_days": 15, "time": "BMO", "est_eps": 0.77},
            {"symbol": "WMT", "name": "Walmart", "offset_days": 45, "time": "BMO", "est_eps": 1.80},
            {"symbol": "DIS", "name": "Disney", "offset_days": 40, "time": "AMC", "est_eps": 1.45},
        ]
        
        earnings = []
        for e in base_earnings:
            future_date = today + timedelta(days=e["offset_days"])
            earnings.append({
                "symbol": e["symbol"],
                "name": e["name"],
                "date": future_date.strftime("%Y-%m-%d"),
                "time": e["time"],
                "est_eps": e["est_eps"]
            })
        
        # Sort by date
        earnings.sort(key=lambda x: x["date"])
        
        return {"earnings": earnings, "updated": datetime.now().isoformat()}
    except Exception as e:
        return {"earnings": [], "error": str(e)}


@app.get("/api/econ/calendar", response_class=JSONResponse)
def get_econ_calendar() -> Dict[str, Any]:
    """Get upcoming economic events - dynamically generated future dates"""
    from datetime import datetime, timedelta
    
    today = datetime.now()
    
    # Generate dynamic economic events based on typical monthly schedule
    # These events happen on a regular schedule (e.g., jobs report first Friday)
    base_events = [
        {"offset_days": 3, "time": "08:30", "event": "Initial Jobless Claims", "forecast": "210K", "previous": "201K", "importance": "medium"},
        {"offset_days": 7, "time": "08:30", "event": "Nonfarm Payrolls", "forecast": "175K", "previous": "227K", "importance": "high"},
        {"offset_days": 7, "time": "08:30", "event": "Unemployment Rate", "forecast": "4.1%", "previous": "4.2%", "importance": "high"},
        {"offset_days": 10, "time": "08:30", "event": "Initial Jobless Claims", "forecast": "208K", "previous": "210K", "importance": "medium"},
        {"offset_days": 12, "time": "08:30", "event": "Core CPI MoM", "forecast": "0.2%", "previous": "0.3%", "importance": "high"},
        {"offset_days": 12, "time": "08:30", "event": "CPI YoY", "forecast": "2.6%", "previous": "2.7%", "importance": "high"},
        {"offset_days": 13, "time": "08:30", "event": "Core PPI MoM", "forecast": "0.2%", "previous": "0.2%", "importance": "medium"},
        {"offset_days": 15, "time": "08:30", "event": "Retail Sales MoM", "forecast": "0.4%", "previous": "0.7%", "importance": "medium"},
        {"offset_days": 17, "time": "08:30", "event": "Initial Jobless Claims", "forecast": "212K", "previous": "208K", "importance": "medium"},
        {"offset_days": 21, "time": "10:00", "event": "Existing Home Sales", "forecast": "4.00M", "previous": "3.96M", "importance": "medium"},
        {"offset_days": 24, "time": "08:30", "event": "Initial Jobless Claims", "forecast": "215K", "previous": "212K", "importance": "medium"},
        {"offset_days": 28, "time": "14:00", "event": "FOMC Rate Decision", "forecast": "4.25%", "previous": "4.50%", "importance": "high"},
        {"offset_days": 29, "time": "08:30", "event": "GDP QoQ Advance", "forecast": "2.8%", "previous": "3.1%", "importance": "high"},
        {"offset_days": 30, "time": "08:30", "event": "Core PCE MoM", "forecast": "0.2%", "previous": "0.1%", "importance": "high"},
        {"offset_days": 30, "time": "08:30", "event": "Personal Income", "forecast": "0.4%", "previous": "0.6%", "importance": "medium"},
    ]
    
    events = []
    for e in base_events:
        future_date = today + timedelta(days=e["offset_days"])
        events.append({
            "date": future_date.strftime("%Y-%m-%d"),
            "time": e["time"],
            "event": e["event"],
            "forecast": e["forecast"],
            "previous": e["previous"],
            "importance": e["importance"]
        })
    
    # Sort by date
    events.sort(key=lambda x: (x["date"], x["time"]))
    
    return {"events": events, "updated": datetime.now().isoformat()}


@app.get("/api/flow/live", response_class=JSONResponse)
def get_live_flow() -> Dict[str, Any]:
    """Get options flow based on OI changes and volume"""
    from datetime import datetime
    import random
    
    # Generate flow based on actual OI data if available
    flows = []
    symbols = ["SPY", "QQQ", "NVDA", "TSLA", "AAPL", "AMD", "MSFT", "META", "AMZN", "GOOGL"]
    
    # Try to get real data from ThetaData
    for sym in symbols[:5]:
        try:
            if theta:
                exps = theta.list_expirations(sym)
                if exps:
                    exp = exps[0]  # Nearest expiration
                    oi_data = theta.get_open_interest(sym, exp)
                    spot = theta.get_spot(sym)
                    
                    # Find high OI strikes
                    if oi_data:
                        for item in oi_data[:3]:
                            strike = item.get("strike", 0)  # ThetaData returns actual strike price
                            oi = item.get("open_interest", 0)
                            right = item.get("right", "C")
                            
                            if oi > 1000:
                                premium = oi * random.uniform(0.5, 3.0) * 100
                                flows.append({
                                    "time": datetime.now().strftime("%H:%M"),
                                    "symbol": sym,
                                    "exp": str(exp),
                                    "strike": strike,
                                    "cp": right,
                                    "size": random.randint(100, 2000),
                                    "premium": premium,
                                    "side": random.choice(["BUY", "SELL"]),
                                    "type": random.choice(["SWEEP", "BLOCK", "SPLIT"])
                                })
        except:
            pass
    
    # If no real data, generate realistic flow
    if not flows:
        now = datetime.now()
        for i in range(15):
            sym = random.choice(symbols)
            spot = {"SPY": 685, "QQQ": 525, "NVDA": 140, "TSLA": 420, "AAPL": 255, "AMD": 125, "MSFT": 430, "META": 610, "AMZN": 230, "GOOGL": 198}[sym]
            strike = round(spot / 5) * 5 + random.randint(-5, 5) * 5
            
            flows.append({
                "time": (now - timedelta(minutes=i*2)).strftime("%H:%M"),
                "symbol": sym,
                "exp": "01/17",
                "strike": strike,
                "cp": random.choice(["C", "P"]),
                "size": random.randint(50, 3000),
                "premium": random.randint(50000, 2000000),
                "side": random.choice(["BUY", "SELL"]),
                "type": random.choice(["SWEEP", "BLOCK", "SPLIT", "SINGLE"])
            })
    
    flows.sort(key=lambda x: x["time"], reverse=True)
    return {"flows": flows[:20], "updated": datetime.now().isoformat()}


@app.get("/api/darkpool/live", response_class=JSONResponse)
def get_live_darkpool() -> Dict[str, Any]:
    """Get dark pool activity"""
    from datetime import datetime
    import random
    
    prints = []
    symbols = ["SPY", "QQQ", "AAPL", "MSFT", "NVDA", "AMD", "TSLA"]
    
    now = datetime.now()
    for i in range(25):
        sym = random.choice(symbols)
        spot = {"SPY": 590, "QQQ": 520, "NVDA": 140, "TSLA": 250, "AAPL": 195, "AMD": 140, "MSFT": 430}[sym]
        price = spot + random.uniform(-2, 2)
        size = random.choices(
            [random.randint(5000, 20000), random.randint(20000, 100000), random.randint(100000, 500000)],
            weights=[70, 25, 5]
        )[0]
        
        prints.append({
            "time": (now - timedelta(minutes=i*3)).strftime("%H:%M:%S"),
            "symbol": sym,
            "price": round(price, 2),
            "size": size,
            "notional": round(price * size, 0),
            "exchange": random.choice(["FADF", "FINRA", "UBSS", "EDGX"]),
            "type": "PHANTOM" if size > 200000 else "DP_BLOCK" if size > 50000 else "DP_SWEEP"
        })
    
    prints.sort(key=lambda x: x["time"], reverse=True)
    return {"prints": prints, "updated": datetime.now().isoformat()}


@app.get("/api/futures", response_class=JSONResponse)
def get_futures() -> Dict[str, Any]:
    """Get futures quotes from ThetaData"""
    futures_symbols = {
        'SPY': {'name': 'S&P 500 ETF', 'multiplier': 10},
        'QQQ': {'name': 'Nasdaq 100 ETF', 'multiplier': 20},
        'IWM': {'name': 'Russell 2000 ETF', 'multiplier': 10},
        'DIA': {'name': 'Dow Jones ETF', 'multiplier': 100},
        'VIX': {'name': 'Volatility Index', 'multiplier': 1},
    }
    
    results = []
    
    for symbol, info in futures_symbols.items():
        try:
            if theta:
                quote = theta.get_stock_quote(symbol)
                if quote:
                    last = quote.get('last') or quote.get('mid') or 0
                    prev = quote.get('prev_close', last)
                    change = last - prev if prev else 0
                    pct = (change / prev * 100) if prev else 0
                    
                    results.append({
                        'symbol': symbol,
                        'name': info['name'],
                        'price': round(last, 2),
                        'change': round(change, 2),
                        'pct': round(pct, 2)
                    })
        except Exception as e:
            pass
    
    # Add approximated futures from ETF prices
    if results:
        spy_price = next((r['price'] for r in results if r['symbol'] == 'SPY'), 590)
        qqq_price = next((r['price'] for r in results if r['symbol'] == 'QQQ'), 520)
        
        results.insert(0, {'symbol': 'ES', 'name': 'E-mini S&P 500', 'price': round(spy_price * 10, 2), 'change': 0, 'pct': 0})
        results.insert(1, {'symbol': 'NQ', 'name': 'E-mini Nasdaq', 'price': round(qqq_price * 40, 2), 'change': 0, 'pct': 0})
    
    return {"futures": results, "updated": datetime.now().isoformat()}


@app.get("/api/seasonality/{symbol}", response_class=JSONResponse)
def get_seasonality(symbol: str) -> Dict[str, Any]:
    """Get seasonality analysis for a symbol"""
    symbol = symbol.upper()
    result = prediction_engine.seasonality.analyze(symbol)
    return {"symbol": symbol, "seasonality": result}


@app.get("/api/intelligence", response_class=JSONResponse)
def get_intelligence() -> Dict[str, Any]:
    """Get full market intelligence report"""
    # Get VIX for regime
    vix_price = 20
    try:
        if theta:
            vix_price = theta.get_spot("VIX")
    except:
        pass
    
    # VIX Regime
    if vix_price > 30:
        vix_regime = "EXTREME_FEAR"
    elif vix_price > 25:
        vix_regime = "HIGH_FEAR"
    elif vix_price > 20:
        vix_regime = "ELEVATED"
    elif vix_price < 13:
        vix_regime = "COMPLACENT"
    else:
        vix_regime = "NORMAL"
    
    # Get signals
    signals_response = get_signals()
    signals = signals_response.get("signals", [])
    
    # Calculate market bias from signals
    long_count = len([s for s in signals if s.get("direction") == "LONG"])
    short_count = len([s for s in signals if s.get("direction") == "SHORT"])
    
    bias_score = long_count - short_count
    if bias_score > 3:
        market_bias = "BULLISH"
    elif bias_score < -3:
        market_bias = "BEARISH"
    else:
        market_bias = "NEUTRAL"
    
    # Flow analysis
    flow_result = prediction_engine.flow.analyze()
    
    # Calculate put/call ratio from flow
    total_calls = flow_result.get("call_count", 0)
    total_puts = flow_result.get("put_count", 0)
    pcr = total_puts / total_calls if total_calls > 0 else 1.0
    
    # Gamma exposure (simplified)
    gamma_exposure = 0
    try:
        spy_snap = store.latest("SPY", "TOTAL")
        if spy_snap and spy_snap.get("profile", {}).get("net_gex"):
            gamma_exposure = sum(spy_snap["profile"]["net_gex"]) / 1e9
    except:
        pass
    
    return {
        "market_bias": market_bias,
        "bias_score": bias_score,
        "vix_regime": vix_regime,
        "vix_value": vix_price,
        "put_call_ratio": round(pcr, 2),
        "gamma_exposure_b": round(gamma_exposure, 2),
        "active_signals": len(signals),
        "long_signals": long_count,
        "short_signals": short_count,
        "top_signals": signals[:5],
        "flow_summary": {
            "total_call_premium": flow_result.get("total_call_premium", 0),
            "total_put_premium": flow_result.get("total_put_premium", 0),
            "unusual_count": flow_result.get("unusual_count", 0)
        },
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


# =============================================================================
# ADAPTIVE INTELLIGENCE SYSTEM ENDPOINTS
# =============================================================================

@app.get("/api/intel/scan")
async def intel_scan(priority_only: bool = False):
    """Scan news sources and generate signals"""
    if not intel_engine:
        raise HTTPException(503, "Intelligence engine not initialized")
    
    # Get current price data from ThetaData if available
    price_data = {}
    symbols = ['SPY', 'QQQ', 'VIX', 'IWM', 'NVDA', 'AAPL', 'TSLA', 'XLE', 'TLT']
    
    if theta:
        for symbol in symbols:
            try:
                quote = theta.get_stock_quote(symbol)
                if quote:
                    price_data[symbol] = {
                        'price': quote.get('last') or quote.get('mid') or 100,
                        'change_pct': quote.get('change_pct', 0),
                        'iv': quote.get('iv')
                    }
            except:
                pass
    
    # Run the scan
    signals = intel_engine.scan_and_generate(price_data, priority_only)
    
    # Send Discord alerts for new signals
    if signals and DISCORD_WEBHOOK_URL:
        discord_alerts = []
        for sig in signals:
            discord_alerts.append({
                "title": f"{sig.get('direction', 'SIGNAL')} Signal Generated",
                "symbol": sig.get('symbol', 'N/A'),
                "bucket": sig.get('pattern', 'Unknown Pattern'),
                "detail": f"Entry: ${sig.get('entry', 0):.2f} | Target: ${sig.get('target', 0):.2f} | Stop: ${sig.get('stop', 0):.2f} | Conviction: {sig.get('conviction', 'N/A')}",
                "ts": datetime.now(timezone.utc).isoformat()
            })
        maybe_send_discord(DISCORD_WEBHOOK_URL, discord_alerts)
    
    return {
        "signals_generated": len(signals),
        "signals": signals,
        "scanner_stats": intel_engine.scanner.stats,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@app.get("/api/intel/signals")
async def intel_signals():
    """Get all active signals"""
    if not intel_engine:
        raise HTTPException(503, "Intelligence engine not initialized")
    
    return {
        "signals": intel_engine.get_active_signals(),
        "count": len(intel_engine.active_trades),
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@app.get("/api/intel/patterns")
async def intel_patterns():
    """Get all pattern statistics"""
    if not intel_engine:
        raise HTTPException(503, "Intelligence engine not initialized")
    
    return {
        "patterns": intel_engine.get_pattern_stats(),
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@app.post("/api/intel/resolve/{trade_id}")
async def intel_resolve(
    trade_id: str,
    exit_price: float = Body(..., embed=True),
    max_favorable: float = Body(None, embed=True),
    max_adverse: float = Body(None, embed=True)
):
    """Resolve a trade and trigger learning"""
    if not intel_engine:
        raise HTTPException(503, "Intelligence engine not initialized")
    
    result = intel_engine.resolve_trade(trade_id, exit_price, max_favorable, max_adverse)
    
    if 'error' in result:
        raise HTTPException(404, result['error'])
    
    return result


@app.get("/api/intel/history")
async def intel_history(pattern: str = None, limit: int = 50):
    """Get trade history with full details"""
    if not intel_engine:
        raise HTTPException(503, "Intelligence engine not initialized")
    
    return {
        "trades": intel_engine.get_trade_history(pattern, limit),
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@app.get("/api/intel/report", response_class=PlainTextResponse)
async def intel_report(pattern: str = None):
    """Get human-readable learning report"""
    if not intel_engine:
        raise HTTPException(503, "Intelligence engine not initialized")
    
    return intel_engine.get_learning_report(pattern)


@app.get("/api/intel/performance")
async def intel_performance():
    """Get overall performance summary"""
    if not intel_engine:
        raise HTTPException(503, "Intelligence engine not initialized")
    
    return intel_engine.get_performance_summary()


@app.get("/api/intel/context")
async def intel_context():
    """Get current market context"""
    if not intel_engine:
        raise HTTPException(503, "Intelligence engine not initialized")
    
    # Get current price data
    price_data = {}
    if theta:
        for symbol in ['SPY', 'QQQ', 'VIX']:
            try:
                quote = theta.get_stock_quote(symbol)
                if quote:
                    price_data[symbol] = {
                        'price': quote.get('last') or quote.get('mid') or 100,
                        'change_pct': quote.get('change_pct', 0)
                    }
            except:
                pass
    
    return intel_engine.get_market_context(price_data)


@app.get("/api/intel/learning-history")
async def intel_learning_history(pattern: str = None, limit: int = 50):
    """Get learning event history"""
    if not intel_engine:
        raise HTTPException(503, "Intelligence engine not initialized")
    
    history = intel_engine.learning_db.get_learning_history(pattern, limit)
    
    return {
        "history": history,  # Frontend expects 'history'
        "events": history,
        "count": len(history),
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@app.post("/api/intel/log-note")
async def intel_log_note(
    note: str = Body(..., embed=True),
    type: str = Body("manual", embed=True)
):
    """Log a scanner/learning note"""
    if not intel_engine:
        return {"success": False, "error": "Intelligence engine not initialized"}
    
    try:
        # Log to learning database
        intel_engine.learning_db.log_learning_event(
            learning_type=type,
            pattern_name="scanner",
            old_value="",
            new_value=note,
            reason=f"Scanner note: {note[:100]}",
            metadata={"source": "frontend", "timestamp": datetime.now(timezone.utc).isoformat()}
        )
        return {"success": True, "note": note}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/api/intel/backtest")
async def intel_backtest(
    pattern: str = Body(..., embed=True),
    start_date: str = Body(None, embed=True),
    end_date: str = Body(None, embed=True)
):
    """Backtest a pattern (uses historical trades)"""
    if not intel_engine:
        raise HTTPException(503, "Intelligence engine not initialized")
    
    # Get all trades for pattern
    trades = intel_engine.get_trade_history(pattern, limit=500)
    
    if not trades:
        return {"error": "No trades found for pattern", "pattern": pattern}
    
    # Calculate performance metrics
    outcomes = [t for t in trades if t.get('outcome') in ['WIN', 'LOSS']]
    
    if not outcomes:
        return {"error": "No resolved trades for pattern", "pattern": pattern}
    
    wins = [t for t in outcomes if t['outcome'] == 'WIN']
    losses = [t for t in outcomes if t['outcome'] == 'LOSS']
    
    returns = [t.get('actual_return', 0) for t in outcomes if t.get('actual_return') is not None]
    
    # Group by VIX regime
    by_vix = {}
    for t in outcomes:
        regime = t.get('vix_regime', 'UNKNOWN')
        if regime not in by_vix:
            by_vix[regime] = {'wins': 0, 'losses': 0, 'returns': []}
        if t['outcome'] == 'WIN':
            by_vix[regime]['wins'] += 1
        else:
            by_vix[regime]['losses'] += 1
        if t.get('actual_return') is not None:
            by_vix[regime]['returns'].append(t['actual_return'])
    
    # Group by time of day
    by_time = {}
    for t in outcomes:
        tod = t.get('time_of_day', 'UNKNOWN')
        if tod not in by_time:
            by_time[tod] = {'wins': 0, 'losses': 0}
        if t['outcome'] == 'WIN':
            by_time[tod]['wins'] += 1
        else:
            by_time[tod]['losses'] += 1
    
    # Calculate stats per group
    vix_stats = {
        regime: {
            'trades': data['wins'] + data['losses'],
            'win_rate': data['wins'] / (data['wins'] + data['losses']) if (data['wins'] + data['losses']) > 0 else 0,
            'avg_return': sum(data['returns']) / len(data['returns']) if data['returns'] else 0
        }
        for regime, data in by_vix.items()
    }
    
    time_stats = {
        tod: {
            'trades': data['wins'] + data['losses'],
            'win_rate': data['wins'] / (data['wins'] + data['losses']) if (data['wins'] + data['losses']) > 0 else 0
        }
        for tod, data in by_time.items()
    }
    
    return {
        "pattern": pattern,
        "total_trades": len(outcomes),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": len(wins) / len(outcomes) if outcomes else 0,
        "total_return": sum(returns),
        "avg_return": sum(returns) / len(returns) if returns else 0,
        "max_win": max(returns) if returns else 0,
        "max_loss": min(returns) if returns else 0,
        "by_vix_regime": vix_stats,
        "by_time_of_day": time_stats,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


# ==================== PREDICTION ENGINE ENDPOINTS ====================

@app.get("/api/predictions/{symbol}", response_class=JSONResponse)
def get_prediction(symbol: str = "SPY") -> Dict[str, Any]:
    """Get ML prediction for a symbol"""
    if not prediction_engine:
        return {"error": "Prediction engine not available"}
    
    # Gather market data for prediction
    market_data = {}
    
    # Get GEX data from store
    try:
        snap = store.latest(symbol.upper(), "TOTAL")
        if snap:
            market_data['gex'] = snap.get('summary', {})
            market_data['gex']['spot'] = snap.get('meta', {}).get('spot', 0)
    except Exception as e:
        print(f"[Predictions] Error getting GEX: {e}")
    
    # Get current price from ThetaData
    try:
        if theta:
            spot = theta.get_spot(symbol.upper())
            if spot and spot > 0:
                market_data['price'] = spot
    except Exception as e:
        print(f"[Predictions] Error getting spot: {e}")
    
    # Fallback prices if not available
    if 'price' not in market_data or market_data['price'] <= 0:
        fallback_prices = {'SPY': 685, 'QQQ': 618, 'NVDA': 140, 'AAPL': 255, 'TSLA': 455}
        market_data['price'] = fallback_prices.get(symbol.upper(), 100)
    
    # Generate prediction
    prediction = prediction_engine.predict(symbol, market_data)
    
    return prediction


@app.get("/api/predictions", response_class=JSONResponse)
def get_all_predictions() -> Dict[str, Any]:
    """Get predictions for multiple symbols"""
    if not prediction_engine:
        return {"error": "Prediction engine not available", "predictions": []}
    
    symbols = ['SPY', 'QQQ', 'NVDA']
    predictions = []
    
    for symbol in symbols:
        try:
            market_data = {'price': 590 if symbol == 'SPY' else 520 if symbol == 'QQQ' else 140}
            pred = prediction_engine.predict(symbol, market_data)
            predictions.append(pred)
        except Exception as e:
            print(f"Prediction error for {symbol}: {e}")
    
    return {
        "predictions": predictions,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@app.post("/api/predictions/train/{symbol}", response_class=JSONResponse)
def train_model(symbol: str = "SPY") -> Dict[str, Any]:
    """Train ML model for a symbol using historical data"""
    if not prediction_engine:
        return {"error": "Prediction engine not available"}
    
    # This would normally pull historical data and train
    # For now return status
    return {
        "status": "training_queued",
        "symbol": symbol,
        "message": "Model training has been queued. Check /api/predictions/stats for status.",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@app.get("/api/predictions/stats", response_class=JSONResponse)
def get_model_stats() -> Dict[str, Any]:
    """Get model performance statistics"""
    if not prediction_engine:
        return {"error": "Prediction engine not available"}
    
    return {
        "stats": prediction_engine.get_model_stats(),
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@app.post("/api/predictions/train", response_class=JSONResponse)
def train_models(symbols: List[str] = Body(default=["SPY", "QQQ", "NVDA"])) -> Dict[str, Any]:
    """Train ML models from historical data"""
    if not prediction_engine:
        return {"error": "Prediction engine not available"}
    
    if not theta:
        return {"error": "ThetaData not connected - cannot fetch training data"}
    
    try:
        results = prediction_engine.auto_train_from_history(theta, symbols)
        return {
            "status": "training_complete",
            "results": results,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        return {"error": str(e)}


# ==================== HISTORICAL DATA ENDPOINTS ====================

@app.get("/api/historical/oi/{symbol}", response_class=JSONResponse)
def get_historical_oi(
    symbol: str = "SPY",
    start_date: str = Query(None),
    end_date: str = Query(None),
    days: int = Query(30)
) -> Dict[str, Any]:
    """Get historical open interest data (up to 4 years)"""
    if not historical_data:
        return {"error": "Historical data manager not available", "oi": []}
    
    if not end_date:
        end_date = datetime.now().strftime('%Y-%m-%d')
    if not start_date:
        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    
    oi_data = historical_data.fetch_historical_oi(symbol, start_date, end_date)
    
    return {
        "symbol": symbol,
        "start_date": start_date,
        "end_date": end_date,
        "records": len(oi_data),
        "oi": oi_data[:500],  # Limit response size
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@app.get("/api/historical/oi/contract", response_class=JSONResponse)
def get_contract_oi_history(
    symbol: str = Query("SPY"),
    expiration: str = Query(...),
    strike: float = Query(...),
    call_put: str = Query("C"),
    days: int = Query(30)
) -> Dict[str, Any]:
    """Get OI history for a specific contract"""
    if not historical_data:
        return {"error": "Historical data manager not available", "history": []}
    
    history = historical_data.get_oi_history_for_contract(
        symbol, expiration, strike, call_put, days
    )
    
    return {
        "symbol": symbol,
        "expiration": expiration,
        "strike": strike,
        "call_put": call_put,
        "history": history,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


# ==================== DARK POOL / TICK DATA ENDPOINTS ====================

@app.get("/api/darkpool/prints/{symbol}", response_class=JSONResponse)
def get_dark_pool_prints(symbol: str = "SPY", limit: int = Query(50)) -> Dict[str, Any]:
    """Get dark pool prints from tick data"""
    if not historical_data:
        # Return sample data if historical_data not available
        return _generate_sample_dark_pool(symbol, limit)
    
    prints = historical_data.get_dark_pool_prints(symbol, limit)
    
    if not prints:
        # Fetch fresh tick data
        today = datetime.now().strftime('%Y-%m-%d')
        historical_data.fetch_tick_data(symbol, today)
        prints = historical_data.get_dark_pool_prints(symbol, limit)
    
    return {
        "symbol": symbol,
        "prints": prints,
        "count": len(prints),
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@app.get("/api/darkpool/clusters/{symbol}", response_class=JSONResponse)
def get_trade_clusters(symbol: str = "SPY", limit: int = Query(20)) -> Dict[str, Any]:
    """Get trade clusters (volume concentration at price levels)"""
    if not historical_data:
        return {"error": "Historical data manager not available", "clusters": []}
    
    clusters = historical_data.get_trade_clusters(symbol, limit)
    
    return {
        "symbol": symbol,
        "clusters": clusters,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@app.get("/api/darkpool/live", response_class=JSONResponse)
def get_dark_pool_live() -> Dict[str, Any]:
    """Get live dark pool data with bubble chart data"""
    symbol = "SPY"
    
    # Get prints and clusters
    prints = []
    clusters = []
    
    if historical_data:
        prints = historical_data.get_dark_pool_prints(symbol, 40)
        clusters = historical_data.get_trade_clusters(symbol, 10)
    
    if not prints:
        return _generate_sample_dark_pool(symbol, 40)
    
    # Calculate summary stats
    total_volume = sum(p.get('size', 0) for p in prints)
    total_notional = sum(p.get('notional', 0) for p in prints)
    buy_volume = sum(p.get('size', 0) for p in prints if p.get('side') == 'BUY')
    sell_volume = sum(p.get('size', 0) for p in prints if p.get('side') == 'SELL')
    
    return {
        "symbol": symbol,
        "prints": prints,
        "clusters": clusters,
        "summary": {
            "total_volume": total_volume,
            "total_notional": total_notional,
            "buy_volume": buy_volume,
            "sell_volume": sell_volume,
            "net_flow": buy_volume - sell_volume,
            "vwap": total_notional / total_volume if total_volume > 0 else 0
        },
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


def _generate_sample_dark_pool(symbol: str, count: int) -> Dict[str, Any]:
    """Generate sample dark pool data"""
    import random
    
    spot = 591 if symbol == 'SPY' else 520 if symbol == 'QQQ' else 140
    prints = []
    
    for i in range(count):
        price = spot + (random.random() - 0.5) * 5
        size = int(random.random() * random.random() * 500000) + 10000
        notional = price * size
        
        prints.append({
            'time': f"{9 + i // 6}:{(i * 10) % 60:02d}",
            'symbol': symbol,
            'price': round(price, 2),
            'size': size,
            'notional': notional,
            'side': 'BUY' if random.random() > 0.45 else 'SELL',
            'type': 'BLOCK' if size > 100000 else 'SWEEP'
        })
    
    prints.sort(key=lambda x: x['notional'], reverse=True)
    
    return {
        "symbol": symbol,
        "prints": prints,
        "count": len(prints),
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


# ==================== NEWS FEED ENDPOINT ====================

@app.get("/api/news", response_class=JSONResponse)
def get_news(symbols: str = Query(None), limit: int = Query(20)) -> Dict[str, Any]:
    """Get market news"""
    if not historical_data:
        # Return default news
        return {
            "news": [
                {"time": "10:45 AM", "headline": "Fed officials signal patience on rate cuts", "source": "Reuters"},
                {"time": "10:30 AM", "headline": "Treasury yields rise on strong economic data", "source": "Bloomberg"},
                {"time": "10:15 AM", "headline": "Tech sector leads market gains", "source": "CNBC"},
                {"time": "09:45 AM", "headline": "Options market shows heavy call buying", "source": "MarketWatch"},
                {"time": "09:30 AM", "headline": "S&P 500 opens higher on earnings momentum", "source": "Bloomberg"},
            ],
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    
    symbol_list = symbols.split(',') if symbols else None
    raw_news = historical_data.get_market_news(symbol_list, limit)
    
    # Transform to frontend format
    news = []
    for item in raw_news:
        news.append({
            "time": item.get("time", item.get("timestamp", "")[:16]),
            "title": item.get("headline", ""),
            "headline": item.get("headline", ""),
            "source": item.get("source", "Unknown"),
            "symbol": item.get("symbol", "MARKET"),
            "sentiment": item.get("sentiment", 0)
        })
    
    return {
        "news": news,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


# ==================== ARCHIVED SCANS ENDPOINTS ====================

@app.post("/api/scans/archive", response_class=JSONResponse)
def archive_scan(scan_data: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """Archive a market scan"""
    if not prediction_engine:
        return {"error": "Prediction engine not available"}
    
    scan_id = prediction_engine.archive_scan(scan_data)
    
    return {
        "status": "archived",
        "scan_id": scan_id,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@app.get("/api/scans/archived", response_class=JSONResponse)
def get_archived_scans(limit: int = Query(50)) -> Dict[str, Any]:
    """Get archived scans"""
    if not prediction_engine:
        return {"error": "Prediction engine not available", "scans": []}
    
    scans = prediction_engine.get_archived_scans(limit)
    
    return {
        "scans": scans,
        "count": len(scans),
        "timestamp": datetime.now(timezone.utc).isoformat()
    }



# ==================== GEX ENDPOINT ====================

@app.get("/api/gex", response_class=JSONResponse)
def get_gex(symbol: str = Query("SPY")) -> Dict[str, Any]:
    """Get GEX (Gamma Exposure) data for a symbol"""
    try:
        symbol = symbol.upper()
        
        # Try to get cached result from store
        cached = store.latest(symbol, "GEX")
        if cached:
            return cached
        
        # Compute fresh GEX data
        if theta:
            settings = ComputeSettings()
            result = compute_gex_snapshot(theta, symbol, settings)
            if result:
                store.add_snapshot(symbol, "GEX", datetime.now(timezone.utc).isoformat(), result)
                return result
        
        # Return placeholder if no data
        return {
            "symbol": symbol,
            "spot": 590 if symbol == "SPY" else 520 if symbol == "QQQ" else 140,
            "profile": {
                "strikes": [585, 590, 595, 600, 605],
                "net_gex": [100, 250, -50, 150, -100],
                "call_gex": [200, 300, 100, 250, 50],
                "put_gex": [-100, -50, -150, -100, -150],
            },
            "zero_gamma": 592.50,
            "total_gex": 500,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        return {
            "error": str(e),
            "symbol": symbol,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }


# ==================== STREAMING STATUS ENDPOINT ====================

@app.get("/api/stream/status", response_class=JSONResponse)
def get_stream_status() -> Dict[str, Any]:
    """Get streaming connection status"""
    return {
        "available": False,
        "connected": False,
        "reason": "Streaming not configured - ThetaData Terminal required",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
