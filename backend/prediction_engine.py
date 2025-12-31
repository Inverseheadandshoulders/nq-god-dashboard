"""
Prediction Engine with ML Training Infrastructure
Uses historical data to train models for price prediction
"""
import os
import json
import pickle
import sqlite3
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import numpy as np

# Optional ML imports - gracefully degrade if not available
try:
    from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
    from sklearn.model_selection import train_test_split, cross_val_score
    from sklearn.preprocessing import StandardScaler
    from sklearn.metrics import accuracy_score, precision_score, recall_score
    ML_AVAILABLE = True
except ImportError:
    ML_AVAILABLE = False
    print("[PredictionEngine] sklearn not installed - using rule-based predictions")


class PredictionEngine:
    """
    ML-based prediction engine that combines multiple signals:
    - GEX levels and positioning
    - Options flow (call/put ratios, unusual activity)
    - Dark pool prints
    - Historical seasonality
    - Technical indicators
    """
    
    def __init__(self, db_path: str = "data/predictions.db"):
        self.db_path = db_path
        self.models: Dict[str, any] = {}
        self.scalers: Dict[str, any] = {}
        self.feature_columns = [
            'gex_normalized',      # Net GEX as % of avg
            'call_put_ratio',      # Options flow ratio
            'dark_pool_bias',      # Buy vs Sell dark pool
            'price_vs_call_wall',  # Distance to call wall
            'price_vs_put_wall',   # Distance to put wall
            'rsi_14',              # 14-day RSI
            'macd_signal',         # MACD crossover
            'volume_ratio',        # Volume vs 20-day avg
            'iv_percentile',       # IV rank
            'seasonality_score',   # Historical performance for this period
            'vix_level',           # VIX current level
            'trend_5d',            # 5-day price trend
            'trend_20d',           # 20-day price trend
            'gap_from_ema20',      # % gap from 20 EMA
            'hour_of_day',         # Trading hour
            'day_of_week',         # Day of week
        ]
        
        self._init_db()
        self._load_models()
    
    def _init_db(self):
        """Initialize SQLite database for storing training data and predictions"""
        os.makedirs(os.path.dirname(self.db_path) if os.path.dirname(self.db_path) else '.', exist_ok=True)
        
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        # Training data table
        c.execute('''CREATE TABLE IF NOT EXISTS training_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            symbol TEXT,
            features TEXT,
            target_1h INTEGER,
            target_4h INTEGER,
            target_1d INTEGER,
            actual_move_1h REAL,
            actual_move_4h REAL,
            actual_move_1d REAL
        )''')
        
        # Predictions table
        c.execute('''CREATE TABLE IF NOT EXISTS predictions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            symbol TEXT,
            direction TEXT,
            entry_price REAL,
            target_price REAL,
            stop_price REAL,
            confidence REAL,
            timeframe TEXT,
            factors TEXT,
            outcome TEXT,
            actual_price REAL,
            pnl REAL
        )''')
        
        # Archived scans table
        c.execute('''CREATE TABLE IF NOT EXISTS archived_scans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            scan_data TEXT
        )''')
        
        # Model performance table
        c.execute('''CREATE TABLE IF NOT EXISTS model_performance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            symbol TEXT,
            model_type TEXT,
            accuracy REAL,
            precision_val REAL,
            recall REAL,
            total_predictions INTEGER,
            winning_predictions INTEGER
        )''')
        
        conn.commit()
        conn.close()
    
    def _load_models(self):
        """Load trained models from disk if available"""
        model_dir = "data/models"
        if not os.path.exists(model_dir):
            os.makedirs(model_dir, exist_ok=True)
            return
        
        for symbol in ['SPY', 'QQQ', 'NVDA', 'AAPL', 'TSLA']:
            model_path = f"{model_dir}/{symbol}_model.pkl"
            scaler_path = f"{model_dir}/{symbol}_scaler.pkl"
            
            if os.path.exists(model_path) and os.path.exists(scaler_path):
                try:
                    with open(model_path, 'rb') as f:
                        self.models[symbol] = pickle.load(f)
                    with open(scaler_path, 'rb') as f:
                        self.scalers[symbol] = pickle.load(f)
                    print(f"[PredictionEngine] Loaded model for {symbol}")
                except Exception as e:
                    print(f"[PredictionEngine] Failed to load model for {symbol}: {e}")
    
    def collect_features(self, symbol: str, market_data: Dict) -> Dict:
        """
        Collect all features for prediction from market data
        
        Args:
            symbol: Ticker symbol
            market_data: Dict containing gex, flow, darkpool, ohlc data
        
        Returns:
            Dict of feature values
        """
        features = {}
        
        # GEX features
        gex = market_data.get('gex', {})
        features['gex_normalized'] = gex.get('net_gex', 0) / max(abs(gex.get('avg_gex', 1)), 1)
        features['price_vs_call_wall'] = (gex.get('call_wall', 0) - gex.get('spot', 0)) / max(gex.get('spot', 1), 1) * 100
        features['price_vs_put_wall'] = (gex.get('spot', 0) - gex.get('put_wall', 0)) / max(gex.get('spot', 1), 1) * 100
        
        # Options flow features
        flow = market_data.get('flow', {})
        call_prem = flow.get('call_premium', 0)
        put_prem = flow.get('put_premium', 0)
        features['call_put_ratio'] = call_prem / max(put_prem, 1) if put_prem > 0 else 2.0
        
        # Dark pool features
        dp = market_data.get('darkpool', {})
        buy_vol = dp.get('buy_volume', 0)
        sell_vol = dp.get('sell_volume', 0)
        total_vol = buy_vol + sell_vol
        features['dark_pool_bias'] = (buy_vol - sell_vol) / max(total_vol, 1)
        
        # Technical features from OHLC
        ohlc = market_data.get('ohlc', [])
        if len(ohlc) >= 20:
            closes = [d.get('close', 0) for d in ohlc[-20:]]
            features['rsi_14'] = self._calculate_rsi(closes, 14)
            features['macd_signal'] = self._calculate_macd_signal(closes)
            features['trend_5d'] = (closes[-1] - closes[-5]) / max(closes[-5], 1) * 100
            features['trend_20d'] = (closes[-1] - closes[0]) / max(closes[0], 1) * 100
            ema20 = self._calculate_ema(closes, 20)
            features['gap_from_ema20'] = (closes[-1] - ema20) / max(ema20, 1) * 100
            
            volumes = [d.get('volume', 0) for d in ohlc[-20:]]
            avg_vol = sum(volumes[:-1]) / max(len(volumes) - 1, 1)
            features['volume_ratio'] = volumes[-1] / max(avg_vol, 1)
        else:
            features['rsi_14'] = 50
            features['macd_signal'] = 0
            features['trend_5d'] = 0
            features['trend_20d'] = 0
            features['gap_from_ema20'] = 0
            features['volume_ratio'] = 1
        
        # IV and VIX
        features['iv_percentile'] = market_data.get('iv_percentile', 50)
        features['vix_level'] = market_data.get('vix', 15)
        
        # Seasonality
        features['seasonality_score'] = market_data.get('seasonality_score', 0)
        
        # Time features
        now = datetime.now()
        features['hour_of_day'] = now.hour
        features['day_of_week'] = now.weekday()
        
        return features
    
    def _calculate_rsi(self, prices: List[float], period: int = 14) -> float:
        """Calculate RSI"""
        if len(prices) < period + 1:
            return 50
        
        deltas = [prices[i] - prices[i-1] for i in range(1, len(prices))]
        gains = [d if d > 0 else 0 for d in deltas[-period:]]
        losses = [-d if d < 0 else 0 for d in deltas[-period:]]
        
        avg_gain = sum(gains) / period
        avg_loss = sum(losses) / period
        
        if avg_loss == 0:
            return 100
        
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))
    
    def _calculate_macd_signal(self, prices: List[float]) -> float:
        """Calculate MACD signal (1 for bullish cross, -1 for bearish, 0 for neutral)"""
        if len(prices) < 26:
            return 0
        
        ema12 = self._calculate_ema(prices, 12)
        ema26 = self._calculate_ema(prices, 26)
        macd = ema12 - ema26
        
        # Simple signal based on MACD value
        if macd > 0.5:
            return 1
        elif macd < -0.5:
            return -1
        return 0
    
    def _calculate_ema(self, prices: List[float], period: int) -> float:
        """Calculate EMA"""
        if len(prices) < period:
            return prices[-1] if prices else 0
        
        multiplier = 2 / (period + 1)
        ema = sum(prices[:period]) / period
        
        for price in prices[period:]:
            ema = (price - ema) * multiplier + ema
        
        return ema
    
    def train_model(self, symbol: str, training_data: List[Dict]) -> Dict:
        """
        Train a model for a specific symbol
        
        Args:
            symbol: Ticker symbol
            training_data: List of dicts with 'features' and 'target' keys
        
        Returns:
            Dict with training metrics
        """
        if not ML_AVAILABLE:
            return {'error': 'sklearn not installed', 'status': 'rule_based'}
        
        if len(training_data) < 100:
            return {'error': 'Insufficient training data', 'samples': len(training_data)}
        
        # Prepare data
        X = []
        y = []
        
        for sample in training_data:
            features = sample.get('features', {})
            target = sample.get('target_1h', 0)  # 1 for up, 0 for down
            
            feature_vector = [features.get(col, 0) for col in self.feature_columns]
            X.append(feature_vector)
            y.append(target)
        
        X = np.array(X)
        y = np.array(y)
        
        # Split data
        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
        
        # Scale features
        scaler = StandardScaler()
        X_train_scaled = scaler.fit_transform(X_train)
        X_test_scaled = scaler.transform(X_test)
        
        # Train model (Gradient Boosting typically works well for financial data)
        model = GradientBoostingClassifier(
            n_estimators=100,
            max_depth=5,
            learning_rate=0.1,
            random_state=42
        )
        model.fit(X_train_scaled, y_train)
        
        # Evaluate
        y_pred = model.predict(X_test_scaled)
        accuracy = accuracy_score(y_test, y_pred)
        precision = precision_score(y_test, y_pred, zero_division=0)
        recall = recall_score(y_test, y_pred, zero_division=0)
        
        # Cross-validation
        cv_scores = cross_val_score(model, X_train_scaled, y_train, cv=5)
        
        # Save model
        self.models[symbol] = model
        self.scalers[symbol] = scaler
        
        model_dir = "data/models"
        os.makedirs(model_dir, exist_ok=True)
        
        with open(f"{model_dir}/{symbol}_model.pkl", 'wb') as f:
            pickle.dump(model, f)
        with open(f"{model_dir}/{symbol}_scaler.pkl", 'wb') as f:
            pickle.dump(scaler, f)
        
        # Log performance
        self._log_performance(symbol, 'gradient_boosting', accuracy, precision, recall, len(training_data))
        
        # Feature importance
        importance = dict(zip(self.feature_columns, model.feature_importances_))
        top_features = sorted(importance.items(), key=lambda x: x[1], reverse=True)[:5]
        
        return {
            'status': 'trained',
            'symbol': symbol,
            'samples': len(training_data),
            'accuracy': round(accuracy, 4),
            'precision': round(precision, 4),
            'recall': round(recall, 4),
            'cv_mean': round(cv_scores.mean(), 4),
            'cv_std': round(cv_scores.std(), 4),
            'top_features': top_features
        }
    
    def _log_performance(self, symbol: str, model_type: str, accuracy: float, precision: float, recall: float, total: int):
        """Log model performance to database"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute('''INSERT INTO model_performance 
                     (timestamp, symbol, model_type, accuracy, precision_val, recall, total_predictions, winning_predictions)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                  (datetime.now().isoformat(), symbol, model_type, accuracy, precision, recall, total, int(total * accuracy)))
        conn.commit()
        conn.close()
    
    def predict(self, symbol: str, market_data: Dict) -> Dict:
        """
        Generate prediction for a symbol
        
        Args:
            symbol: Ticker symbol
            market_data: Current market data
        
        Returns:
            Prediction dict with direction, targets, confidence, factors
        """
        features = self.collect_features(symbol, market_data)
        spot = market_data.get('gex', {}).get('spot', 0) or market_data.get('price', 100)
        
        # Use ML model if available
        if ML_AVAILABLE and symbol in self.models:
            return self._ml_predict(symbol, features, spot)
        
        # Fallback to rule-based prediction
        return self._rule_based_predict(symbol, features, spot)
    
    def _ml_predict(self, symbol: str, features: Dict, spot: float) -> Dict:
        """Generate ML-based prediction"""
        model = self.models[symbol]
        scaler = self.scalers[symbol]
        
        feature_vector = np.array([[features.get(col, 0) for col in self.feature_columns]])
        feature_scaled = scaler.transform(feature_vector)
        
        # Get probability
        prob = model.predict_proba(feature_scaled)[0]
        direction = 'BULLISH' if prob[1] > 0.5 else 'BEARISH'
        confidence = max(prob) * 100
        
        # Calculate targets based on ATR or fixed %
        atr_pct = 0.012  # ~1.2% default
        
        if direction == 'BULLISH':
            entry = spot
            target = spot * (1 + atr_pct * 1.8)
            stop = spot * (1 - atr_pct)
        else:
            entry = spot
            target = spot * (1 - atr_pct * 1.8)
            stop = spot * (1 + atr_pct)
        
        # Determine factors
        factors = self._determine_factors(features, direction)
        
        return {
            'symbol': symbol,
            'direction': direction,
            'entry': round(entry, 2),
            'target': round(target, 2),
            'stop': round(stop, 2),
            'confidence': round(confidence, 1),
            'rr': round(abs(target - entry) / max(abs(stop - entry), 0.01), 2),
            'win_rate': round(confidence, 0),
            'ev': round((confidence/100) * abs(target - entry) - ((100-confidence)/100) * abs(stop - entry), 2),
            'factors': factors,
            'model': 'ml',
            'timestamp': datetime.now().isoformat()
        }
    
    def _rule_based_predict(self, symbol: str, features: Dict, spot: float) -> Dict:
        """Generate rule-based prediction when ML model not available"""
        score = 0
        factors = []
        
        # GEX analysis
        if features['price_vs_put_wall'] < 1:
            score += 2
            factors.append({'name': 'Near Put Wall Support', 'type': 'positive'})
        elif features['price_vs_call_wall'] < 1:
            score -= 2
            factors.append({'name': 'Near Call Wall Resistance', 'type': 'negative'})
        
        if features['gex_normalized'] > 0.5:
            score += 1
            factors.append({'name': 'Positive GEX', 'type': 'positive'})
        elif features['gex_normalized'] < -0.5:
            score -= 1
            factors.append({'name': 'Negative GEX', 'type': 'negative'})
        
        # Flow analysis
        if features['call_put_ratio'] > 1.5:
            score += 1.5
            factors.append({'name': 'Call Flow Dominant', 'type': 'positive'})
        elif features['call_put_ratio'] < 0.7:
            score -= 1.5
            factors.append({'name': 'Put Flow Dominant', 'type': 'negative'})
        
        # Dark pool
        if features['dark_pool_bias'] > 0.2:
            score += 1
            factors.append({'name': 'Dark Pool Buying', 'type': 'positive'})
        elif features['dark_pool_bias'] < -0.2:
            score -= 1
            factors.append({'name': 'Dark Pool Selling', 'type': 'negative'})
        
        # RSI
        if features['rsi_14'] < 30:
            score += 1.5
            factors.append({'name': 'RSI Oversold', 'type': 'positive'})
        elif features['rsi_14'] > 70:
            score -= 1.5
            factors.append({'name': 'RSI Overbought', 'type': 'negative'})
        
        # Trend
        if features['trend_5d'] > 1:
            score += 0.5
            factors.append({'name': 'Uptrend 5D', 'type': 'positive'})
        elif features['trend_5d'] < -1:
            score -= 0.5
            factors.append({'name': 'Downtrend 5D', 'type': 'negative'})
        
        # Seasonality
        if features['seasonality_score'] > 0.5:
            score += 1
            factors.append({'name': 'Bullish Seasonality', 'type': 'positive'})
        elif features['seasonality_score'] < -0.5:
            score -= 1
            factors.append({'name': 'Bearish Seasonality', 'type': 'negative'})
        
        # Determine direction and confidence
        direction = 'BULLISH' if score > 0 else 'BEARISH'
        confidence = min(85, 50 + abs(score) * 5)
        
        # Calculate targets
        atr_pct = 0.012
        if direction == 'BULLISH':
            entry = spot
            target = spot * (1 + atr_pct * 1.8)
            stop = spot * (1 - atr_pct)
        else:
            entry = spot
            target = spot * (1 - atr_pct * 1.8)
            stop = spot * (1 + atr_pct)
        
        return {
            'symbol': symbol,
            'direction': direction,
            'entry': round(entry, 2),
            'target': round(target, 2),
            'stop': round(stop, 2),
            'confidence': round(confidence, 1),
            'rr': round(abs(target - entry) / max(abs(stop - entry), 0.01), 2),
            'win_rate': round(confidence, 0),
            'ev': round((confidence/100) * abs(target - entry) - ((100-confidence)/100) * abs(stop - entry), 2),
            'factors': factors[:4],
            'model': 'rule_based',
            'timestamp': datetime.now().isoformat()
        }
    
    def _determine_factors(self, features: Dict, direction: str) -> List[Dict]:
        """Determine contributing factors for the prediction"""
        factors = []
        
        if direction == 'BULLISH':
            if features['call_put_ratio'] > 1.2:
                factors.append({'name': 'Call Flow', 'type': 'positive'})
            if features['dark_pool_bias'] > 0.1:
                factors.append({'name': 'DP Accumulation', 'type': 'positive'})
            if features['gex_normalized'] > 0:
                factors.append({'name': 'GEX Supportive', 'type': 'positive'})
            if features['rsi_14'] < 40:
                factors.append({'name': 'RSI Setup', 'type': 'positive'})
        else:
            if features['call_put_ratio'] < 0.8:
                factors.append({'name': 'Put Flow', 'type': 'positive'})
            if features['dark_pool_bias'] < -0.1:
                factors.append({'name': 'DP Distribution', 'type': 'positive'})
            if features['gex_normalized'] < 0:
                factors.append({'name': 'GEX Resistance', 'type': 'positive'})
            if features['rsi_14'] > 60:
                factors.append({'name': 'RSI Setup', 'type': 'positive'})
        
        if features['seasonality_score'] != 0:
            factors.append({'name': 'Seasonality', 'type': 'neutral'})
        
        return factors[:4]
    
    def save_prediction(self, prediction: Dict) -> int:
        """Save a prediction to the database"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute('''INSERT INTO predictions 
                     (timestamp, symbol, direction, entry_price, target_price, stop_price, confidence, timeframe, factors)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                  (prediction.get('timestamp', datetime.now().isoformat()),
                   prediction['symbol'],
                   prediction['direction'],
                   prediction['entry'],
                   prediction['target'],
                   prediction['stop'],
                   prediction['confidence'],
                   prediction.get('timeframe', '1h'),
                   json.dumps(prediction.get('factors', []))))
        conn.commit()
        pred_id = c.lastrowid
        conn.close()
        return pred_id
    
    def archive_scan(self, scan_data: Dict) -> int:
        """Archive a market scan"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute('''INSERT INTO archived_scans (timestamp, scan_data) VALUES (?, ?)''',
                  (datetime.now().isoformat(), json.dumps(scan_data)))
        conn.commit()
        scan_id = c.lastrowid
        conn.close()
        return scan_id
    
    def get_archived_scans(self, limit: int = 50) -> List[Dict]:
        """Get archived scans"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute('''SELECT id, timestamp, scan_data FROM archived_scans ORDER BY timestamp DESC LIMIT ?''', (limit,))
        rows = c.fetchall()
        conn.close()
        
        scans = []
        for row in rows:
            scan = json.loads(row[2])
            scan['id'] = row[0]
            scan['timestamp'] = row[1]
            scans.append(scan)
        
        return scans
    
    def get_model_stats(self) -> Dict:
        """Get model performance statistics"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        # Get latest performance for each symbol
        c.execute('''SELECT symbol, accuracy, precision_val, recall, total_predictions, timestamp
                     FROM model_performance 
                     WHERE id IN (SELECT MAX(id) FROM model_performance GROUP BY symbol)''')
        rows = c.fetchall()
        conn.close()
        
        stats = {}
        for row in rows:
            stats[row[0]] = {
                'accuracy': row[1],
                'precision': row[2],
                'recall': row[3],
                'total_predictions': row[4],
                'last_trained': row[5]
            }
        
        return stats


# Global instance
prediction_engine = PredictionEngine()
