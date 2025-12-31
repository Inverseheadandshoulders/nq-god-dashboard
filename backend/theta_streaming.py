"""
ThetaData WebSocket Streaming Client
=====================================
Real-time streaming of options/stock data via WebSocket connection.

WebSocket endpoint: ws://127.0.0.1:25520/v1/events
"""

import asyncio
import json
import threading
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Set
from dataclasses import dataclass, field
from collections import defaultdict

try:
    import websockets
    WEBSOCKETS_AVAILABLE = True
except ImportError:
    WEBSOCKETS_AVAILABLE = False
    print("[ThetaStream] websockets not installed - streaming disabled")


@dataclass
class StreamConfig:
    """Configuration for streaming"""
    ws_url: str = "ws://127.0.0.1:25520/v1/events"
    reconnect_delay: float = 5.0
    max_reconnect_attempts: int = 10


@dataclass 
class StreamData:
    """Container for streaming data"""
    # Latest prices by symbol
    prices: Dict[str, float] = field(default_factory=dict)
    # Latest quotes by symbol
    quotes: Dict[str, Dict] = field(default_factory=dict)
    # Latest trades by symbol
    trades: Dict[str, List[Dict]] = field(default_factory=lambda: defaultdict(list))
    # Options data by symbol+exp+strike
    options: Dict[str, Dict] = field(default_factory=dict)
    # Callbacks for data updates
    callbacks: List[Callable] = field(default_factory=list)
    # Last update timestamp
    last_update: Optional[datetime] = None


class ThetaStreamClient:
    """WebSocket streaming client for ThetaData"""
    
    def __init__(self, config: Optional[StreamConfig] = None):
        self.config = config or StreamConfig()
        self.data = StreamData()
        self._ws = None
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._subscriptions: Set[str] = set()
        self._reconnect_count = 0
        
    @property
    def is_connected(self) -> bool:
        return self._ws is not None and self._running
    
    def add_callback(self, callback: Callable[[str, Dict], None]):
        """Add callback for streaming updates. Callback receives (event_type, data)"""
        self.data.callbacks.append(callback)
        
    def remove_callback(self, callback: Callable):
        """Remove a callback"""
        if callback in self.data.callbacks:
            self.data.callbacks.remove(callback)
    
    def _notify_callbacks(self, event_type: str, data: Dict):
        """Notify all callbacks of new data"""
        for callback in self.data.callbacks:
            try:
                callback(event_type, data)
            except Exception as e:
                print(f"[ThetaStream] Callback error: {e}")
    
    async def _connect(self):
        """Establish WebSocket connection"""
        if not WEBSOCKETS_AVAILABLE:
            print("[ThetaStream] websockets not installed")
            return False
            
        try:
            print(f"[ThetaStream] Connecting to {self.config.ws_url}...")
            self._ws = await websockets.connect(self.config.ws_url)
            print("[ThetaStream] Connected!")
            self._reconnect_count = 0
            return True
        except Exception as e:
            print(f"[ThetaStream] Connection failed: {e}")
            self._ws = None
            return False
    
    async def subscribe_stock_trades(self, symbols: List[str]):
        """Subscribe to stock trade stream for given symbols"""
        if not self._ws:
            return False
            
        for symbol in symbols:
            req = {
                "msg_type": "STREAM",
                "sec_type": "STOCK",
                "req_type": "TRADE",
                "root": symbol.upper(),
                "add": True,
                "id": len(self._subscriptions)
            }
            await self._ws.send(json.dumps(req))
            self._subscriptions.add(f"STOCK:TRADE:{symbol}")
            print(f"[ThetaStream] Subscribed to {symbol} trades")
        return True
    
    async def subscribe_stock_quotes(self, symbols: List[str]):
        """Subscribe to stock quote stream for given symbols"""
        if not self._ws:
            return False
            
        for symbol in symbols:
            req = {
                "msg_type": "STREAM",
                "sec_type": "STOCK",
                "req_type": "QUOTE",
                "root": symbol.upper(),
                "add": True,
                "id": len(self._subscriptions)
            }
            await self._ws.send(json.dumps(req))
            self._subscriptions.add(f"STOCK:QUOTE:{symbol}")
            print(f"[ThetaStream] Subscribed to {symbol} quotes")
        return True
    
    async def subscribe_all_options_trades(self):
        """Subscribe to ALL options trades (bulk stream)"""
        if not self._ws:
            return False
            
        req = {
            "msg_type": "STREAM_BULK",
            "sec_type": "OPTION",
            "req_type": "TRADE",
            "add": True,
            "id": len(self._subscriptions)
        }
        await self._ws.send(json.dumps(req))
        self._subscriptions.add("OPTION:TRADE:BULK")
        print("[ThetaStream] Subscribed to ALL options trades")
        return True
    
    async def subscribe_all_options_quotes(self):
        """Subscribe to ALL options quotes (bulk stream)"""
        if not self._ws:
            return False
            
        req = {
            "msg_type": "STREAM_BULK",
            "sec_type": "OPTION",
            "req_type": "QUOTE",
            "add": True,
            "id": len(self._subscriptions)
        }
        await self._ws.send(json.dumps(req))
        self._subscriptions.add("OPTION:QUOTE:BULK")
        print("[ThetaStream] Subscribed to ALL options quotes")
        return True
    
    def _process_message(self, msg: Dict):
        """Process incoming WebSocket message"""
        header = msg.get("header", {})
        msg_type = header.get("type", "")
        
        self.data.last_update = datetime.now()
        
        if msg_type == "TRADE":
            self._handle_trade(msg)
        elif msg_type == "QUOTE":
            self._handle_quote(msg)
        elif msg_type == "STATUS":
            print(f"[ThetaStream] Status: {msg}")
        elif msg_type == "ERROR":
            print(f"[ThetaStream] Error: {msg}")
    
    def _handle_trade(self, msg: Dict):
        """Handle trade message"""
        trade = msg.get("trade", {})
        contract = msg.get("contract", {})
        
        symbol = contract.get("root", "UNKNOWN")
        price = trade.get("price", 0)
        size = trade.get("size", 0)
        
        # Update latest price
        if price > 0:
            self.data.prices[symbol] = price
            
        # Store trade
        trade_data = {
            "symbol": symbol,
            "price": price,
            "size": size,
            "ms_of_day": trade.get("ms_of_day", 0),
            "condition": trade.get("condition"),
            "timestamp": datetime.now().isoformat()
        }
        
        # For options, include strike/exp/right
        if contract.get("strike"):
            trade_data["strike"] = contract.get("strike", 0) / 1000
            trade_data["exp"] = contract.get("expiration")
            trade_data["right"] = contract.get("right")
        
        # Keep last 100 trades per symbol
        self.data.trades[symbol].append(trade_data)
        if len(self.data.trades[symbol]) > 100:
            self.data.trades[symbol] = self.data.trades[symbol][-100:]
        
        # Notify callbacks
        self._notify_callbacks("trade", trade_data)
    
    def _handle_quote(self, msg: Dict):
        """Handle quote message"""
        quote = msg.get("quote", {})
        contract = msg.get("contract", {})
        
        symbol = contract.get("root", "UNKNOWN")
        bid = quote.get("bid", 0)
        ask = quote.get("ask", 0)
        
        quote_data = {
            "symbol": symbol,
            "bid": bid,
            "ask": ask,
            "bid_size": quote.get("bid_size", 0),
            "ask_size": quote.get("ask_size", 0),
            "mid": (bid + ask) / 2 if bid > 0 and ask > 0 else 0,
            "timestamp": datetime.now().isoformat()
        }
        
        # For options
        if contract.get("strike"):
            quote_data["strike"] = contract.get("strike", 0) / 1000
            quote_data["exp"] = contract.get("expiration")
            quote_data["right"] = contract.get("right")
        
        self.data.quotes[symbol] = quote_data
        
        # Update price from mid
        if quote_data["mid"] > 0:
            self.data.prices[symbol] = quote_data["mid"]
        
        self._notify_callbacks("quote", quote_data)
    
    async def _run_loop(self):
        """Main streaming loop"""
        while self._running:
            if not await self._connect():
                if self._reconnect_count >= self.config.max_reconnect_attempts:
                    print("[ThetaStream] Max reconnect attempts reached")
                    break
                self._reconnect_count += 1
                await asyncio.sleep(self.config.reconnect_delay)
                continue
            
            try:
                async for message in self._ws:
                    if not self._running:
                        break
                    try:
                        msg = json.loads(message)
                        self._process_message(msg)
                    except json.JSONDecodeError:
                        print(f"[ThetaStream] Invalid JSON: {message[:100]}")
                    except Exception as e:
                        print(f"[ThetaStream] Process error: {e}")
            except websockets.exceptions.ConnectionClosed:
                print("[ThetaStream] Connection closed, reconnecting...")
            except Exception as e:
                print(f"[ThetaStream] Error: {e}")
            
            self._ws = None
            if self._running:
                await asyncio.sleep(self.config.reconnect_delay)
    
    def start(self, symbols: Optional[List[str]] = None):
        """Start streaming in background thread"""
        if self._running:
            return
            
        self._running = True
        
        async def _start():
            if not await self._connect():
                return
            
            # Subscribe to defaults
            default_symbols = symbols or ["SPY", "QQQ", "IWM", "VIX"]
            await self.subscribe_stock_trades(default_symbols)
            await self.subscribe_stock_quotes(default_symbols)
            await self.subscribe_all_options_trades()
            
            await self._run_loop()
        
        def _thread_target():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(_start())
        
        self._thread = threading.Thread(target=_thread_target, daemon=True)
        self._thread.start()
        print("[ThetaStream] Started streaming thread")
    
    def stop(self):
        """Stop streaming"""
        self._running = False
        if self._ws:
            asyncio.get_event_loop().run_until_complete(self._ws.close())
        print("[ThetaStream] Stopped")
    
    def get_price(self, symbol: str) -> Optional[float]:
        """Get latest price for symbol"""
        return self.data.prices.get(symbol.upper())
    
    def get_quote(self, symbol: str) -> Optional[Dict]:
        """Get latest quote for symbol"""
        return self.data.quotes.get(symbol.upper())
    
    def get_recent_trades(self, symbol: str, limit: int = 20) -> List[Dict]:
        """Get recent trades for symbol"""
        trades = self.data.trades.get(symbol.upper(), [])
        return trades[-limit:] if trades else []
    
    def get_all_prices(self) -> Dict[str, float]:
        """Get all latest prices"""
        return dict(self.data.prices)


# Global streaming client instance
stream_client: Optional[ThetaStreamClient] = None


def get_stream_client() -> Optional[ThetaStreamClient]:
    """Get or create global stream client"""
    global stream_client
    if stream_client is None and WEBSOCKETS_AVAILABLE:
        stream_client = ThetaStreamClient()
    return stream_client


def start_streaming(symbols: Optional[List[str]] = None):
    """Start global streaming"""
    client = get_stream_client()
    if client:
        client.start(symbols)
    return client


def stop_streaming():
    """Stop global streaming"""
    global stream_client
    if stream_client:
        stream_client.stop()
        stream_client = None
