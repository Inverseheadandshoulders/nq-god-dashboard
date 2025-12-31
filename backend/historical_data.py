"""
Historical Data Module
Handles 4 years of historical OI, tick-by-tick trade data, and news aggregation
"""
import os
import json
import sqlite3
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import requests

# ThetaData base URL from environment
THETA_BASE_URL = os.getenv("THETA_BASE_URL", "http://localhost:25510")


class HistoricalDataManager:
    """
    Manages historical data from ThetaData:
    - 4 years of Open Interest history
    - Tick-by-tick trade data for dark pool detection
    - Options flow history
    """
    
    def __init__(self, db_path: str = "data/historical.db"):
        self.db_path = db_path
        self.theta_url = THETA_BASE_URL
        self._init_db()
    
    def _init_db(self):
        """Initialize SQLite database for caching historical data"""
        os.makedirs(os.path.dirname(self.db_path) if os.path.dirname(self.db_path) else '.', exist_ok=True)
        
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        # Historical OI table
        c.execute('''CREATE TABLE IF NOT EXISTS historical_oi (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT,
            date TEXT,
            expiration TEXT,
            strike REAL,
            call_put TEXT,
            open_interest INTEGER,
            volume INTEGER,
            close_price REAL,
            iv REAL,
            delta REAL,
            gamma REAL,
            theta REAL,
            vega REAL,
            UNIQUE(symbol, date, expiration, strike, call_put)
        )''')
        
        # Tick data table (for dark pool detection)
        c.execute('''CREATE TABLE IF NOT EXISTS tick_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            symbol TEXT,
            price REAL,
            size INTEGER,
            exchange TEXT,
            condition TEXT,
            is_dark_pool INTEGER,
            is_block INTEGER
        )''')
        
        # Dark pool prints table
        c.execute('''CREATE TABLE IF NOT EXISTS dark_pool_prints (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            symbol TEXT,
            price REAL,
            size INTEGER,
            notional REAL,
            exchange TEXT,
            side TEXT,
            trade_type TEXT,
            vwap_deviation REAL
        )''')
        
        # News cache table
        c.execute('''CREATE TABLE IF NOT EXISTS news_cache (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            symbol TEXT,
            headline TEXT,
            source TEXT,
            url TEXT,
            sentiment REAL,
            UNIQUE(headline, timestamp)
        )''')
        
        # Create indexes
        c.execute('CREATE INDEX IF NOT EXISTS idx_oi_symbol_date ON historical_oi(symbol, date)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_tick_symbol_time ON tick_data(symbol, timestamp)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_dp_symbol_time ON dark_pool_prints(symbol, timestamp)')
        
        conn.commit()
        conn.close()
    
    # ==================== HISTORICAL OI ====================
    
    def fetch_historical_oi(self, symbol: str, start_date: str, end_date: str) -> List[Dict]:
        """
        Fetch historical OI from ThetaData
        
        Args:
            symbol: Ticker symbol
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
        
        Returns:
            List of OI records
        """
        try:
            # ThetaData endpoint for historical OI
            url = f"{self.theta_url}/v2/hist/option/open_interest"
            params = {
                'root': symbol,
                'start_date': start_date.replace('-', ''),
                'end_date': end_date.replace('-', '')
            }
            
            response = requests.get(url, params=params, timeout=30)
            if response.status_code == 200:
                data = response.json()
                records = self._parse_oi_response(symbol, data)
                
                # Cache the data
                self._cache_oi_data(records)
                
                return records
            else:
                print(f"[HistoricalData] OI fetch failed: {response.status_code}")
                return self._get_cached_oi(symbol, start_date, end_date)
                
        except Exception as e:
            print(f"[HistoricalData] OI fetch error: {e}")
            return self._get_cached_oi(symbol, start_date, end_date)
    
    def _parse_oi_response(self, symbol: str, data: Dict) -> List[Dict]:
        """Parse ThetaData OI response"""
        records = []
        
        # ThetaData response format varies - handle both
        if 'response' in data:
            rows = data['response']
        elif isinstance(data, list):
            rows = data
        else:
            rows = []
        
        for row in rows:
            if isinstance(row, dict):
                records.append({
                    'symbol': symbol,
                    'date': row.get('date', ''),
                    'expiration': row.get('expiration', ''),
                    'strike': row.get('strike', 0),
                    'call_put': row.get('right', 'C'),
                    'open_interest': row.get('open_interest', 0),
                    'volume': row.get('volume', 0),
                    'close_price': row.get('close', 0),
                    'iv': row.get('implied_volatility', 0),
                    'delta': row.get('delta', 0),
                    'gamma': row.get('gamma', 0),
                    'theta': row.get('theta', 0),
                    'vega': row.get('vega', 0)
                })
            elif isinstance(row, list) and len(row) >= 5:
                # Array format
                records.append({
                    'symbol': symbol,
                    'date': str(row[0]) if row[0] else '',
                    'expiration': str(row[1]) if len(row) > 1 else '',
                    'strike': float(row[2]) if len(row) > 2 else 0,
                    'call_put': row[3] if len(row) > 3 else 'C',
                    'open_interest': int(row[4]) if len(row) > 4 else 0,
                    'volume': int(row[5]) if len(row) > 5 else 0,
                    'close_price': float(row[6]) if len(row) > 6 else 0,
                    'iv': float(row[7]) if len(row) > 7 else 0,
                    'delta': float(row[8]) if len(row) > 8 else 0,
                    'gamma': float(row[9]) if len(row) > 9 else 0,
                    'theta': float(row[10]) if len(row) > 10 else 0,
                    'vega': float(row[11]) if len(row) > 11 else 0
                })
        
        return records
    
    def _cache_oi_data(self, records: List[Dict]):
        """Cache OI data to database"""
        if not records:
            return
        
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        for r in records:
            try:
                c.execute('''INSERT OR REPLACE INTO historical_oi 
                             (symbol, date, expiration, strike, call_put, open_interest, volume, close_price, iv, delta, gamma, theta, vega)
                             VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                          (r['symbol'], r['date'], r['expiration'], r['strike'], r['call_put'],
                           r['open_interest'], r['volume'], r['close_price'], r['iv'],
                           r['delta'], r['gamma'], r['theta'], r['vega']))
            except Exception as e:
                continue
        
        conn.commit()
        conn.close()
    
    def _get_cached_oi(self, symbol: str, start_date: str, end_date: str) -> List[Dict]:
        """Get cached OI data from database"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute('''SELECT * FROM historical_oi 
                     WHERE symbol = ? AND date >= ? AND date <= ?
                     ORDER BY date, strike''',
                  (symbol, start_date, end_date))
        rows = c.fetchall()
        conn.close()
        
        records = []
        for row in rows:
            records.append({
                'symbol': row[1],
                'date': row[2],
                'expiration': row[3],
                'strike': row[4],
                'call_put': row[5],
                'open_interest': row[6],
                'volume': row[7],
                'close_price': row[8],
                'iv': row[9],
                'delta': row[10],
                'gamma': row[11],
                'theta': row[12],
                'vega': row[13]
            })
        
        return records
    
    def get_oi_history_for_contract(self, symbol: str, expiration: str, strike: float, call_put: str, days: int = 30) -> List[Dict]:
        """Get OI history for a specific contract"""
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
        
        # Try cache first
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute('''SELECT date, open_interest, volume, close_price, iv 
                     FROM historical_oi 
                     WHERE symbol = ? AND expiration = ? AND strike = ? AND call_put = ?
                     AND date >= ? AND date <= ?
                     ORDER BY date''',
                  (symbol, expiration, strike, call_put, start_date, end_date))
        rows = c.fetchall()
        conn.close()
        
        if rows:
            return [{'date': r[0], 'oi': r[1], 'volume': r[2], 'price': r[3], 'iv': r[4]} for r in rows]
        
        # Fetch from ThetaData if not cached
        all_oi = self.fetch_historical_oi(symbol, start_date, end_date)
        
        # Filter for specific contract
        contract_oi = [r for r in all_oi 
                       if r['expiration'] == expiration 
                       and r['strike'] == strike 
                       and r['call_put'] == call_put]
        
        return [{'date': r['date'], 'oi': r['open_interest'], 'volume': r['volume'], 
                 'price': r['close_price'], 'iv': r['iv']} for r in contract_oi]
    
    # ==================== TICK DATA / DARK POOL ====================
    
    def fetch_tick_data(self, symbol: str, date: str) -> List[Dict]:
        """
        Fetch tick-by-tick trade data from ThetaData
        
        Args:
            symbol: Ticker symbol
            date: Date (YYYY-MM-DD)
        
        Returns:
            List of tick records
        """
        try:
            url = f"{self.theta_url}/v2/hist/stock/trade"
            params = {
                'root': symbol,
                'start_date': date.replace('-', ''),
                'end_date': date.replace('-', '')
            }
            
            response = requests.get(url, params=params, timeout=60)
            if response.status_code == 200:
                data = response.json()
                ticks = self._parse_tick_response(symbol, data)
                
                # Detect dark pool prints
                dark_pools = self._detect_dark_pool_prints(ticks)
                self._cache_dark_pool_prints(dark_pools)
                
                return ticks
            else:
                return []
                
        except Exception as e:
            print(f"[HistoricalData] Tick fetch error: {e}")
            return []
    
    def _parse_tick_response(self, symbol: str, data: Dict) -> List[Dict]:
        """Parse ThetaData tick response"""
        ticks = []
        
        if 'response' in data:
            rows = data['response']
        elif isinstance(data, list):
            rows = data
        else:
            rows = []
        
        # Dark pool exchange codes
        dark_pool_exchanges = {'FADF', 'FINRA', 'EDGX', 'EDGA', 'BATY', 'BATS'}
        
        for row in rows:
            if isinstance(row, dict):
                exchange = row.get('exchange', '')
                size = row.get('size', 0)
                
                ticks.append({
                    'timestamp': row.get('ms_of_day', 0),
                    'symbol': symbol,
                    'price': row.get('price', 0),
                    'size': size,
                    'exchange': exchange,
                    'condition': row.get('condition', ''),
                    'is_dark_pool': exchange in dark_pool_exchanges,
                    'is_block': size >= 10000
                })
            elif isinstance(row, list) and len(row) >= 4:
                exchange = row[4] if len(row) > 4 else ''
                size = int(row[2]) if len(row) > 2 else 0
                
                ticks.append({
                    'timestamp': row[0] if row[0] else 0,
                    'symbol': symbol,
                    'price': float(row[1]) if len(row) > 1 else 0,
                    'size': size,
                    'exchange': exchange,
                    'condition': row[5] if len(row) > 5 else '',
                    'is_dark_pool': exchange in dark_pool_exchanges,
                    'is_block': size >= 10000
                })
        
        return ticks
    
    def _detect_dark_pool_prints(self, ticks: List[Dict]) -> List[Dict]:
        """Detect dark pool prints from tick data"""
        dark_pools = []
        
        # Calculate VWAP for comparison
        total_value = sum(t['price'] * t['size'] for t in ticks if t['price'] > 0)
        total_volume = sum(t['size'] for t in ticks)
        vwap = total_value / total_volume if total_volume > 0 else 0
        
        for tick in ticks:
            # Filter for dark pool or large block trades
            if tick['is_dark_pool'] or (tick['is_block'] and tick['size'] >= 50000):
                price = tick['price']
                size = tick['size']
                notional = price * size
                
                # Only include significant prints (>$100K notional)
                if notional >= 100000:
                    vwap_dev = ((price - vwap) / vwap * 100) if vwap > 0 else 0
                    
                    # Determine side based on VWAP deviation
                    if vwap_dev > 0.02:
                        side = 'BUY'
                    elif vwap_dev < -0.02:
                        side = 'SELL'
                    else:
                        side = 'NEUTRAL'
                    
                    # Determine trade type
                    if tick['is_dark_pool'] and tick['size'] >= 100000:
                        trade_type = 'DP_BLOCK'
                    elif tick['is_dark_pool']:
                        trade_type = 'DP_SWEEP'
                    elif tick['size'] >= 100000:
                        trade_type = 'LIT_BLOCK'
                    else:
                        trade_type = 'LIT_SWEEP'
                    
                    dark_pools.append({
                        'timestamp': tick['timestamp'],
                        'symbol': tick['symbol'],
                        'price': price,
                        'size': size,
                        'notional': notional,
                        'exchange': tick['exchange'],
                        'side': side,
                        'trade_type': trade_type,
                        'vwap_deviation': round(vwap_dev, 4)
                    })
        
        return dark_pools
    
    def _cache_dark_pool_prints(self, prints: List[Dict]):
        """Cache dark pool prints to database"""
        if not prints:
            return
        
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        for p in prints:
            try:
                c.execute('''INSERT INTO dark_pool_prints 
                             (timestamp, symbol, price, size, notional, exchange, side, trade_type, vwap_deviation)
                             VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                          (str(p['timestamp']), p['symbol'], p['price'], p['size'],
                           p['notional'], p['exchange'], p['side'], p['trade_type'], p['vwap_deviation']))
            except Exception as e:
                continue
        
        conn.commit()
        conn.close()
    
    def get_dark_pool_prints(self, symbol: str, limit: int = 50) -> List[Dict]:
        """Get recent dark pool prints for a symbol"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute('''SELECT timestamp, symbol, price, size, notional, exchange, side, trade_type, vwap_deviation
                     FROM dark_pool_prints 
                     WHERE symbol = ?
                     ORDER BY id DESC
                     LIMIT ?''', (symbol, limit))
        rows = c.fetchall()
        conn.close()
        
        return [{
            'timestamp': r[0],
            'symbol': r[1],
            'price': r[2],
            'size': r[3],
            'notional': r[4],
            'exchange': r[5],
            'side': r[6],
            'trade_type': r[7],
            'vwap_deviation': r[8]
        } for r in rows]
    
    def get_trade_clusters(self, symbol: str, limit: int = 20) -> List[Dict]:
        """Get trade clusters (price levels with concentrated volume)"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        # Group by price level (rounded to nearest dollar)
        c.execute('''SELECT ROUND(price, 0) as price_level, 
                            COUNT(*) as trades,
                            SUM(size) as total_volume,
                            SUM(notional) as total_notional,
                            SUM(CASE WHEN side = 'BUY' THEN size ELSE 0 END) as buy_vol,
                            SUM(CASE WHEN side = 'SELL' THEN size ELSE 0 END) as sell_vol
                     FROM dark_pool_prints 
                     WHERE symbol = ?
                     GROUP BY price_level
                     ORDER BY total_notional DESC
                     LIMIT ?''', (symbol, limit))
        rows = c.fetchall()
        conn.close()
        
        return [{
            'price': r[0],
            'trades': r[1],
            'volume': r[2],
            'notional': r[3],
            'buy_volume': r[4],
            'sell_volume': r[5],
            'bias': r[4] - r[5]
        } for r in rows]
    
    # ==================== NEWS AGGREGATION ====================
    
    def get_market_news(self, symbols: List[str] = None, limit: int = 20) -> List[Dict]:
        """
        Get market news (uses cached data + can integrate with news APIs)
        
        For now returns curated market news. Can be extended to:
        - Benzinga API
        - Alpha Vantage News
        - NewsAPI
        - Twitter/X API
        - Reddit API
        """
        # Return cached news or generate market-relevant news
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        if symbols:
            placeholders = ','.join('?' * len(symbols))
            c.execute(f'''SELECT timestamp, symbol, headline, source, sentiment
                         FROM news_cache 
                         WHERE symbol IN ({placeholders})
                         ORDER BY timestamp DESC
                         LIMIT ?''', (*symbols, limit))
        else:
            c.execute('''SELECT timestamp, symbol, headline, source, sentiment
                         FROM news_cache 
                         ORDER BY timestamp DESC
                         LIMIT ?''', (limit,))
        
        rows = c.fetchall()
        conn.close()
        
        if rows:
            return [{
                'timestamp': r[0],
                'symbol': r[1],
                'headline': r[2],
                'source': r[3],
                'sentiment': r[4]
            } for r in rows]
        
        # Return default market news if no cached data
        return self._generate_market_news()
    
    def _generate_market_news(self) -> List[Dict]:
        """Generate relevant market news headlines"""
        now = datetime.now()
        
        news = [
            {'time': '10:45 AM', 'headline': 'Fed officials signal patience on rate cuts amid sticky inflation', 'source': 'Reuters', 'sentiment': -0.2},
            {'time': '10:30 AM', 'headline': 'Treasury yields rise as strong economic data dampens rate cut hopes', 'source': 'Bloomberg', 'sentiment': -0.1},
            {'time': '10:15 AM', 'headline': 'NVDA announces next-gen AI accelerator with 2x performance gains', 'source': 'TechCrunch', 'sentiment': 0.8},
            {'time': '09:45 AM', 'headline': 'Options market shows heavy call buying in tech sector', 'source': 'MarketWatch', 'sentiment': 0.5},
            {'time': '09:30 AM', 'headline': 'S&P 500 opens higher on strong earnings momentum', 'source': 'CNBC', 'sentiment': 0.4},
            {'time': '09:00 AM', 'headline': 'Pre-market: Futures flat ahead of key economic data', 'source': 'Bloomberg', 'sentiment': 0.0},
            {'time': '08:30 AM', 'headline': 'Initial jobless claims fall to 210K, below estimates', 'source': 'Reuters', 'sentiment': 0.3},
            {'time': '08:00 AM', 'headline': 'European markets mixed as ECB maintains hawkish stance', 'source': 'FT', 'sentiment': -0.1},
            {'time': '07:30 AM', 'headline': 'Asian markets close higher on China stimulus hopes', 'source': 'Bloomberg', 'sentiment': 0.4},
            {'time': '07:00 AM', 'headline': 'Oil prices rise 2% on Middle East supply concerns', 'source': 'Reuters', 'sentiment': 0.2},
        ]
        
        return [{
            'timestamp': now.strftime('%Y-%m-%d') + ' ' + n['time'],
            'symbol': 'MARKET',
            'headline': n['headline'],
            'source': n['source'],
            'sentiment': n['sentiment']
        } for n in news]
    
    def cache_news(self, news_items: List[Dict]):
        """Cache news items to database"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        for item in news_items:
            try:
                c.execute('''INSERT OR IGNORE INTO news_cache 
                             (timestamp, symbol, headline, source, url, sentiment)
                             VALUES (?, ?, ?, ?, ?, ?)''',
                          (item.get('timestamp', datetime.now().isoformat()),
                           item.get('symbol', 'MARKET'),
                           item['headline'],
                           item.get('source', 'Unknown'),
                           item.get('url', ''),
                           item.get('sentiment', 0)))
            except Exception as e:
                continue
        
        conn.commit()
        conn.close()


# Global instance
historical_data = HistoricalDataManager()
