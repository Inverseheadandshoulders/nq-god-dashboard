#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║                    ADAPTIVE LEARNING ENGINE                                   ║
║                                                                              ║
║  This is NOT a toy. This learns from EVERY trade:                            ║
║  • WHY did it fail? (timing, stop placement, catalyst misread, regime)       ║
║  • WHAT market conditions were present?                                      ║
║  • HOW can the pattern be refined?                                           ║
║  • WHEN does this pattern work best? (time, day, VIX level)                  ║
║                                                                              ║
║  The system gets smarter with every outcome.                                 ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import os
import json
import sqlite3
import hashlib
import statistics
import threading
from datetime import datetime, timedelta
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Tuple
from collections import defaultdict
import math

# ============================================================================
# TRADE RECORD - CAPTURES EVERYTHING
# ============================================================================

@dataclass
class TradeRecord:
    """Complete record of a trade for learning"""
    id: str
    pattern_name: str
    symbol: str
    direction: str  # LONG/SHORT
    
    # Entry details
    entry_price: float
    entry_time: str
    catalyst: str
    catalyst_source: str
    catalyst_category: str
    
    # Targets
    target_price: float
    stop_price: float
    
    # Market context at entry
    vix_at_entry: float
    vix_regime: str  # COMPLACENT/NORMAL/ELEVATED/HIGH_FEAR
    spy_trend: str   # UP/DOWN/SIDEWAYS
    sector_momentum: float
    time_of_day: str  # PRE_MARKET/OPEN/MIDDAY/CLOSE/AFTER_HOURS
    day_of_week: int
    days_to_expiry: int
    
    # Options specifics
    strike: float = None
    expiration: str = None
    option_type: str = None  # CALL/PUT
    iv_at_entry: float = None
    delta_at_entry: float = None
    
    # Conviction and scoring
    conviction: str = "MEDIUM"
    pattern_score: float = 1.0
    pattern_win_rate_at_entry: float = 0.5
    
    # Outcome (filled after resolution)
    outcome: str = "PENDING"  # WIN/LOSS/SCRATCH/EXPIRED
    exit_price: float = None
    exit_time: str = None
    actual_return: float = None
    max_favorable: float = None  # Best price reached
    max_adverse: float = None    # Worst price reached
    time_to_resolution: int = None  # Minutes
    
    # Post-trade analysis (filled by learning engine)
    failure_reason: str = None
    lesson_learned: str = None
    suggested_improvements: List[str] = field(default_factory=list)


# ============================================================================
# PATTERN EVOLUTION - HOW PATTERNS CHANGE OVER TIME  
# ============================================================================

@dataclass
class PatternEvolution:
    """Tracks how a pattern evolves and improves"""
    name: str
    version: int = 1
    
    # Core pattern
    keywords: List[str] = field(default_factory=list)
    direction: str = "LONG"
    symbols: List[str] = field(default_factory=list)
    
    # Learned parameters (start with defaults, evolve over time)
    base_weight: float = 1.0
    
    # Time-based adjustments (learned)
    best_time_of_day: str = None  # When does this pattern work best?
    worst_time_of_day: str = None
    time_multipliers: Dict[str, float] = field(default_factory=dict)
    
    # VIX regime adjustments (learned)
    best_vix_regime: str = None
    vix_multipliers: Dict[str, float] = field(default_factory=dict)
    
    # Day of week adjustments (learned)
    day_multipliers: Dict[int, float] = field(default_factory=dict)
    
    # Stop/target adjustments (learned from actual outcomes)
    optimal_stop_pct: float = 0.02  # Starts at 2%, adjusts based on outcomes
    optimal_target_pct: float = 0.03  # Starts at 3%, adjusts based on outcomes
    
    # Hold period (learned)
    optimal_hold_hours: int = 24
    
    # Performance tracking
    total_trades: int = 0
    wins: int = 0
    losses: int = 0
    scratches: int = 0
    total_return: float = 0.0
    
    # Detailed tracking for learning
    returns_by_vix: Dict[str, List[float]] = field(default_factory=dict)
    returns_by_time: Dict[str, List[float]] = field(default_factory=dict)
    returns_by_day: Dict[int, List[float]] = field(default_factory=dict)
    stop_hit_prices: List[float] = field(default_factory=list)  # How far before stop hit
    target_hit_prices: List[float] = field(default_factory=list)
    
    # Learning history
    adjustments_made: List[dict] = field(default_factory=list)
    last_updated: str = None

    @property
    def win_rate(self) -> float:
        if self.total_trades == 0:
            return 0.5
        return self.wins / self.total_trades
    
    @property
    def avg_return(self) -> float:
        if self.total_trades == 0:
            return 0.0
        return self.total_return / self.total_trades
    
    @property
    def effective_weight(self) -> float:
        """Calculate weight based on performance"""
        base = self.base_weight
        
        # Adjust based on win rate (more trades = more confidence in adjustment)
        if self.total_trades >= 10:
            if self.win_rate > 0.65:
                base *= 1.3
            elif self.win_rate > 0.55:
                base *= 1.1
            elif self.win_rate < 0.40:
                base *= 0.7
            elif self.win_rate < 0.50:
                base *= 0.85
        
        return base


# ============================================================================
# LEARNING DATABASE
# ============================================================================

class LearningDatabase:
    """Persistent storage for all learning data"""
    
    def __init__(self, db_path: str = "data/learning.db"):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path) if os.path.dirname(db_path) else 'data', exist_ok=True)
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.lock = threading.Lock()
        self._init_tables()
    
    def _init_tables(self):
        cursor = self.conn.cursor()
        
        # Complete trade history
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                id TEXT PRIMARY KEY,
                pattern_name TEXT,
                symbol TEXT,
                direction TEXT,
                entry_price REAL,
                entry_time TEXT,
                catalyst TEXT,
                catalyst_source TEXT,
                catalyst_category TEXT,
                target_price REAL,
                stop_price REAL,
                vix_at_entry REAL,
                vix_regime TEXT,
                spy_trend TEXT,
                sector_momentum REAL,
                time_of_day TEXT,
                day_of_week INTEGER,
                days_to_expiry INTEGER,
                strike REAL,
                expiration TEXT,
                option_type TEXT,
                iv_at_entry REAL,
                delta_at_entry REAL,
                conviction TEXT,
                pattern_score REAL,
                pattern_win_rate_at_entry REAL,
                outcome TEXT DEFAULT 'PENDING',
                exit_price REAL,
                exit_time TEXT,
                actual_return REAL,
                max_favorable REAL,
                max_adverse REAL,
                time_to_resolution INTEGER,
                failure_reason TEXT,
                lesson_learned TEXT,
                suggested_improvements TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Pattern evolution history
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS patterns (
                name TEXT PRIMARY KEY,
                version INTEGER DEFAULT 1,
                keywords TEXT,
                direction TEXT,
                symbols TEXT,
                base_weight REAL DEFAULT 1.0,
                best_time_of_day TEXT,
                worst_time_of_day TEXT,
                time_multipliers TEXT,
                best_vix_regime TEXT,
                vix_multipliers TEXT,
                day_multipliers TEXT,
                optimal_stop_pct REAL DEFAULT 0.02,
                optimal_target_pct REAL DEFAULT 0.03,
                optimal_hold_hours INTEGER DEFAULT 24,
                total_trades INTEGER DEFAULT 0,
                wins INTEGER DEFAULT 0,
                losses INTEGER DEFAULT 0,
                scratches INTEGER DEFAULT 0,
                total_return REAL DEFAULT 0.0,
                returns_by_vix TEXT,
                returns_by_time TEXT,
                returns_by_day TEXT,
                stop_hit_prices TEXT,
                target_hit_prices TEXT,
                adjustments_made TEXT,
                last_updated TEXT
            )
        """)
        
        # Learning log - what did we learn and when
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS learning_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                pattern_name TEXT,
                learning_type TEXT,
                old_value TEXT,
                new_value TEXT,
                reason TEXT,
                trades_analyzed INTEGER,
                confidence REAL
            )
        """)
        
        # Daily performance summary
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS daily_summary (
                date TEXT PRIMARY KEY,
                total_signals INTEGER DEFAULT 0,
                wins INTEGER DEFAULT 0,
                losses INTEGER DEFAULT 0,
                scratches INTEGER DEFAULT 0,
                total_return REAL DEFAULT 0.0,
                best_pattern TEXT,
                worst_pattern TEXT,
                avg_vix REAL,
                lessons TEXT
            )
        """)
        
        # Market regime tracking
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS market_regimes (
                timestamp TEXT PRIMARY KEY,
                vix REAL,
                vix_regime TEXT,
                spy_price REAL,
                spy_trend TEXT,
                market_breadth REAL,
                sector_rotation TEXT
            )
        """)
        
        self.conn.commit()
    
    def save_trade(self, trade: TradeRecord):
        """Save a complete trade record"""
        with self.lock:
            cursor = self.conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO trades (
                    id, pattern_name, symbol, direction, entry_price, entry_time,
                    catalyst, catalyst_source, catalyst_category, target_price, stop_price,
                    vix_at_entry, vix_regime, spy_trend, sector_momentum, time_of_day,
                    day_of_week, days_to_expiry, strike, expiration, option_type,
                    iv_at_entry, delta_at_entry, conviction, pattern_score,
                    pattern_win_rate_at_entry, outcome, exit_price, exit_time,
                    actual_return, max_favorable, max_adverse, time_to_resolution,
                    failure_reason, lesson_learned, suggested_improvements
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                trade.id, trade.pattern_name, trade.symbol, trade.direction,
                trade.entry_price, trade.entry_time, trade.catalyst, trade.catalyst_source,
                trade.catalyst_category, trade.target_price, trade.stop_price,
                trade.vix_at_entry, trade.vix_regime, trade.spy_trend, trade.sector_momentum,
                trade.time_of_day, trade.day_of_week, trade.days_to_expiry,
                trade.strike, trade.expiration, trade.option_type,
                trade.iv_at_entry, trade.delta_at_entry, trade.conviction, trade.pattern_score,
                trade.pattern_win_rate_at_entry, trade.outcome, trade.exit_price,
                trade.exit_time, trade.actual_return, trade.max_favorable, trade.max_adverse,
                trade.time_to_resolution, trade.failure_reason, trade.lesson_learned,
                json.dumps(trade.suggested_improvements) if trade.suggested_improvements else None
            ))
            self.conn.commit()
    
    def get_trades_for_pattern(self, pattern_name: str, limit: int = 100) -> List[dict]:
        """Get all trades for a pattern"""
        with self.lock:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT * FROM trades WHERE pattern_name = ? 
                ORDER BY entry_time DESC LIMIT ?
            """, (pattern_name, limit))
            columns = [d[0] for d in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]
    
    def get_pattern(self, name: str) -> Optional[PatternEvolution]:
        """Load a pattern's evolution data"""
        with self.lock:
            cursor = self.conn.cursor()
            cursor.execute("SELECT * FROM patterns WHERE name = ?", (name,))
            row = cursor.fetchone()
            if not row:
                return None
            
            columns = [d[0] for d in cursor.description]
            data = dict(zip(columns, row))
            
            # Parse JSON fields
            pattern = PatternEvolution(name=data['name'])
            pattern.version = data['version']
            pattern.keywords = json.loads(data['keywords']) if data['keywords'] else []
            pattern.direction = data['direction']
            pattern.symbols = json.loads(data['symbols']) if data['symbols'] else []
            pattern.base_weight = data['base_weight']
            pattern.best_time_of_day = data['best_time_of_day']
            pattern.worst_time_of_day = data['worst_time_of_day']
            pattern.time_multipliers = json.loads(data['time_multipliers']) if data['time_multipliers'] else {}
            pattern.best_vix_regime = data['best_vix_regime']
            pattern.vix_multipliers = json.loads(data['vix_multipliers']) if data['vix_multipliers'] else {}
            pattern.day_multipliers = json.loads(data['day_multipliers']) if data['day_multipliers'] else {}
            pattern.optimal_stop_pct = data['optimal_stop_pct']
            pattern.optimal_target_pct = data['optimal_target_pct']
            pattern.optimal_hold_hours = data['optimal_hold_hours']
            pattern.total_trades = data['total_trades']
            pattern.wins = data['wins']
            pattern.losses = data['losses']
            pattern.scratches = data['scratches']
            pattern.total_return = data['total_return']
            pattern.returns_by_vix = json.loads(data['returns_by_vix']) if data['returns_by_vix'] else {}
            pattern.returns_by_time = json.loads(data['returns_by_time']) if data['returns_by_time'] else {}
            pattern.returns_by_day = json.loads(data['returns_by_day']) if data['returns_by_day'] else {}
            pattern.adjustments_made = json.loads(data['adjustments_made']) if data['adjustments_made'] else []
            pattern.last_updated = data['last_updated']
            
            return pattern
    
    def save_pattern(self, pattern: PatternEvolution):
        """Save pattern evolution data"""
        with self.lock:
            cursor = self.conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO patterns (
                    name, version, keywords, direction, symbols, base_weight,
                    best_time_of_day, worst_time_of_day, time_multipliers,
                    best_vix_regime, vix_multipliers, day_multipliers,
                    optimal_stop_pct, optimal_target_pct, optimal_hold_hours,
                    total_trades, wins, losses, scratches, total_return,
                    returns_by_vix, returns_by_time, returns_by_day,
                    stop_hit_prices, target_hit_prices, adjustments_made, last_updated
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                pattern.name, pattern.version, json.dumps(pattern.keywords),
                pattern.direction, json.dumps(pattern.symbols), pattern.base_weight,
                pattern.best_time_of_day, pattern.worst_time_of_day,
                json.dumps(pattern.time_multipliers), pattern.best_vix_regime,
                json.dumps(pattern.vix_multipliers), json.dumps({str(k): v for k, v in pattern.day_multipliers.items()}),
                pattern.optimal_stop_pct, pattern.optimal_target_pct, pattern.optimal_hold_hours,
                pattern.total_trades, pattern.wins, pattern.losses, pattern.scratches,
                pattern.total_return, json.dumps(pattern.returns_by_vix),
                json.dumps(pattern.returns_by_time), json.dumps({str(k): v for k, v in pattern.returns_by_day.items()}),
                json.dumps(pattern.stop_hit_prices[-100:]),  # Keep last 100
                json.dumps(pattern.target_hit_prices[-100:]),
                json.dumps(pattern.adjustments_made[-50:]),  # Keep last 50 adjustments
                datetime.now().isoformat()
            ))
            self.conn.commit()
    
    def log_learning(self, pattern_name: str, learning_type: str, old_value: str, 
                     new_value: str, reason: str, trades_analyzed: int, confidence: float):
        """Log a learning event"""
        with self.lock:
            cursor = self.conn.cursor()
            cursor.execute("""
                INSERT INTO learning_log (timestamp, pattern_name, learning_type, 
                                          old_value, new_value, reason, trades_analyzed, confidence)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (datetime.now().isoformat(), pattern_name, learning_type,
                  old_value, new_value, reason, trades_analyzed, confidence))
            self.conn.commit()
    
    def get_all_patterns(self) -> List[PatternEvolution]:
        """Get all patterns"""
        with self.lock:
            cursor = self.conn.cursor()
            cursor.execute("SELECT name FROM patterns")
            names = [row[0] for row in cursor.fetchall()]
        
        return [self.get_pattern(name) for name in names if self.get_pattern(name)]
    
    def get_learning_history(self, pattern_name: str = None, limit: int = 50) -> List[dict]:
        """Get learning history"""
        with self.lock:
            cursor = self.conn.cursor()
            if pattern_name:
                cursor.execute("""
                    SELECT * FROM learning_log WHERE pattern_name = ?
                    ORDER BY timestamp DESC LIMIT ?
                """, (pattern_name, limit))
            else:
                cursor.execute("""
                    SELECT * FROM learning_log ORDER BY timestamp DESC LIMIT ?
                """, (limit,))
            columns = [d[0] for d in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]


# ============================================================================
# THE LEARNING ENGINE - THE BRAIN
# ============================================================================

class AdaptiveLearningEngine:
    """
    The brain that learns from every trade.
    
    After each trade resolves, it:
    1. Analyzes WHY the trade succeeded or failed
    2. Identifies patterns in failures (time, VIX, stop placement, etc.)
    3. Adjusts pattern parameters to improve future performance
    4. Generates human-readable reports on what it learned
    """
    
    def __init__(self, db: LearningDatabase):
        self.db = db
        self.min_trades_for_learning = 5  # Need at least 5 trades to start adjusting
        self.confidence_threshold = 0.7   # Only adjust if confidence > 70%
    
    def analyze_trade_outcome(self, trade: TradeRecord) -> dict:
        """
        Deep analysis of a single trade outcome.
        Returns detailed breakdown of what happened and why.
        """
        analysis = {
            'trade_id': trade.id,
            'pattern': trade.pattern_name,
            'outcome': trade.outcome,
            'return': trade.actual_return,
            'failure_reasons': [],
            'success_factors': [],
            'lessons': [],
            'improvements': []
        }
        
        if trade.outcome == 'WIN':
            analysis['success_factors'] = self._analyze_success(trade)
        elif trade.outcome == 'LOSS':
            analysis['failure_reasons'] = self._analyze_failure(trade)
            analysis['lessons'] = self._extract_lessons(trade)
            analysis['improvements'] = self._suggest_improvements(trade)
        
        return analysis
    
    def _analyze_failure(self, trade: TradeRecord) -> List[str]:
        """Identify why a trade failed"""
        reasons = []
        
        # 1. Stop hit analysis
        if trade.max_adverse and trade.stop_price:
            stop_distance = abs(trade.entry_price - trade.stop_price) / trade.entry_price
            adverse_distance = abs(trade.entry_price - trade.max_adverse) / trade.entry_price
            
            if trade.max_favorable and trade.max_favorable != trade.entry_price:
                # Trade went our way first, then reversed
                favorable_distance = abs(trade.max_favorable - trade.entry_price) / trade.entry_price
                if favorable_distance > 0.01:  # Went 1%+ in our favor
                    reasons.append(f"REVERSAL: Trade went {favorable_distance:.1%} favorable before reversing")
            
            if adverse_distance > stop_distance * 0.9:
                reasons.append("STOP_TOO_TIGHT: Price barely exceeded stop before reversing")
        
        # 2. Timing analysis
        if trade.time_of_day == 'OPEN' and trade.time_to_resolution and trade.time_to_resolution < 30:
            reasons.append("OPEN_VOLATILITY: Stopped out in opening volatility")
        
        if trade.time_of_day == 'CLOSE':
            reasons.append("END_OF_DAY: Late entry reduced reaction time")
        
        # 3. VIX regime mismatch
        if trade.vix_regime == 'HIGH_FEAR' and trade.direction == 'LONG':
            reasons.append("VIX_MISMATCH: Long position in high fear environment")
        elif trade.vix_regime == 'COMPLACENT' and trade.direction == 'SHORT':
            reasons.append("VIX_MISMATCH: Short position in complacent market")
        
        # 4. Catalyst strength
        if trade.pattern_score < 1.5:
            reasons.append("WEAK_CATALYST: Pattern score below threshold for high conviction")
        
        # 5. Options-specific
        if trade.option_type and trade.days_to_expiry:
            if trade.days_to_expiry < 3:
                reasons.append("THETA_DECAY: Too close to expiration")
            if trade.iv_at_entry and trade.iv_at_entry > 50:
                reasons.append("IV_CRUSH_RISK: High IV at entry increased risk")
        
        if not reasons:
            reasons.append("MARKET_CONDITIONS: Adverse market move against position")
        
        return reasons
    
    def _analyze_success(self, trade: TradeRecord) -> List[str]:
        """Identify why a trade succeeded"""
        factors = []
        
        if trade.time_to_resolution and trade.time_to_resolution < 60:
            factors.append("QUICK_MOVE: Target hit rapidly")
        
        if trade.vix_regime == 'NORMAL' and trade.direction == 'LONG':
            factors.append("FAVORABLE_REGIME: Normal VIX environment for longs")
        
        if trade.pattern_score >= 2.0:
            factors.append("HIGH_CONVICTION: Strong pattern score")
        
        if trade.pattern_win_rate_at_entry >= 0.6:
            factors.append("PROVEN_PATTERN: High historical win rate")
        
        if trade.max_favorable:
            target_distance = abs(trade.target_price - trade.entry_price)
            actual_move = abs(trade.max_favorable - trade.entry_price)
            if actual_move > target_distance * 1.2:
                factors.append("EXCEEDED_TARGET: Move exceeded expectations")
        
        return factors
    
    def _extract_lessons(self, trade: TradeRecord) -> List[str]:
        """Extract actionable lessons from a losing trade"""
        lessons = []
        
        failure_reasons = self._analyze_failure(trade)
        
        for reason in failure_reasons:
            if 'STOP_TOO_TIGHT' in reason:
                lessons.append(f"Consider widening stop for {trade.pattern_name} pattern")
            elif 'OPEN_VOLATILITY' in reason:
                lessons.append(f"Avoid {trade.pattern_name} entries in first 30 mins")
            elif 'VIX_MISMATCH' in reason:
                lessons.append(f"Check VIX regime before {trade.direction} entries")
            elif 'THETA_DECAY' in reason:
                lessons.append("Use longer-dated options for this pattern")
            elif 'REVERSAL' in reason:
                lessons.append("Consider taking partial profits earlier")
        
        return lessons
    
    def _suggest_improvements(self, trade: TradeRecord) -> List[str]:
        """Suggest specific parameter changes"""
        improvements = []
        
        failure_reasons = self._analyze_failure(trade)
        
        for reason in failure_reasons:
            if 'STOP_TOO_TIGHT' in reason:
                current_stop = abs(trade.entry_price - trade.stop_price) / trade.entry_price
                suggested_stop = current_stop * 1.25
                improvements.append(f"STOP: Increase from {current_stop:.1%} to {suggested_stop:.1%}")
            
            elif 'OPEN_VOLATILITY' in reason:
                improvements.append("TIME: Add filter to avoid first 30 minutes")
            
            elif 'VIX_MISMATCH' in reason:
                improvements.append(f"REGIME: Add VIX filter for {trade.direction} trades")
            
            elif 'WEAK_CATALYST' in reason:
                improvements.append("SCORE: Increase minimum pattern score threshold")
        
        return improvements
    
    def learn_from_pattern_history(self, pattern: PatternEvolution) -> dict:
        """
        Analyze all trades for a pattern and update its parameters.
        This is the core learning function.
        """
        trades = self.db.get_trades_for_pattern(pattern.name)
        
        if len(trades) < self.min_trades_for_learning:
            return {'status': 'insufficient_data', 'trades': len(trades)}
        
        learning_report = {
            'pattern': pattern.name,
            'trades_analyzed': len(trades),
            'adjustments': [],
            'new_parameters': {}
        }
        
        # Separate wins and losses
        wins = [t for t in trades if t['outcome'] == 'WIN']
        losses = [t for t in trades if t['outcome'] == 'LOSS']
        
        # 1. LEARN OPTIMAL VIX REGIME
        vix_performance = self._analyze_by_vix(trades)
        if vix_performance['best_regime'] and vix_performance['confidence'] > self.confidence_threshold:
            old_best = pattern.best_vix_regime
            pattern.best_vix_regime = vix_performance['best_regime']
            pattern.vix_multipliers = vix_performance['multipliers']
            
            if old_best != pattern.best_vix_regime:
                learning_report['adjustments'].append({
                    'type': 'VIX_REGIME',
                    'old': old_best,
                    'new': pattern.best_vix_regime,
                    'reason': f"Win rate {vix_performance['best_win_rate']:.1%} in {pattern.best_vix_regime}"
                })
                self.db.log_learning(pattern.name, 'VIX_REGIME', str(old_best),
                                    pattern.best_vix_regime, vix_performance['reason'],
                                    len(trades), vix_performance['confidence'])
        
        # 2. LEARN OPTIMAL TIME OF DAY
        time_performance = self._analyze_by_time(trades)
        if time_performance['best_time'] and time_performance['confidence'] > self.confidence_threshold:
            old_best = pattern.best_time_of_day
            pattern.best_time_of_day = time_performance['best_time']
            pattern.worst_time_of_day = time_performance['worst_time']
            pattern.time_multipliers = time_performance['multipliers']
            
            if old_best != pattern.best_time_of_day:
                learning_report['adjustments'].append({
                    'type': 'TIME_OF_DAY',
                    'old': old_best,
                    'new': pattern.best_time_of_day,
                    'reason': time_performance['reason']
                })
                self.db.log_learning(pattern.name, 'TIME_OF_DAY', str(old_best),
                                    pattern.best_time_of_day, time_performance['reason'],
                                    len(trades), time_performance['confidence'])
        
        # 3. LEARN OPTIMAL STOP DISTANCE
        stop_analysis = self._analyze_stops(trades)
        if stop_analysis['optimal_stop'] and stop_analysis['confidence'] > self.confidence_threshold:
            old_stop = pattern.optimal_stop_pct
            if abs(stop_analysis['optimal_stop'] - old_stop) > 0.005:  # Only if >0.5% difference
                pattern.optimal_stop_pct = stop_analysis['optimal_stop']
                
                learning_report['adjustments'].append({
                    'type': 'STOP_DISTANCE',
                    'old': f"{old_stop:.1%}",
                    'new': f"{pattern.optimal_stop_pct:.1%}",
                    'reason': stop_analysis['reason']
                })
                self.db.log_learning(pattern.name, 'STOP_DISTANCE', f"{old_stop:.1%}",
                                    f"{pattern.optimal_stop_pct:.1%}", stop_analysis['reason'],
                                    len(trades), stop_analysis['confidence'])
        
        # 4. LEARN OPTIMAL TARGET
        target_analysis = self._analyze_targets(trades)
        if target_analysis['optimal_target'] and target_analysis['confidence'] > self.confidence_threshold:
            old_target = pattern.optimal_target_pct
            if abs(target_analysis['optimal_target'] - old_target) > 0.005:
                pattern.optimal_target_pct = target_analysis['optimal_target']
                
                learning_report['adjustments'].append({
                    'type': 'TARGET_DISTANCE',
                    'old': f"{old_target:.1%}",
                    'new': f"{pattern.optimal_target_pct:.1%}",
                    'reason': target_analysis['reason']
                })
                self.db.log_learning(pattern.name, 'TARGET_DISTANCE', f"{old_target:.1%}",
                                    f"{pattern.optimal_target_pct:.1%}", target_analysis['reason'],
                                    len(trades), target_analysis['confidence'])
        
        # 5. LEARN DAY OF WEEK PATTERNS
        day_performance = self._analyze_by_day(trades)
        if day_performance['multipliers']:
            pattern.day_multipliers = day_performance['multipliers']
        
        # 6. UPDATE BASE WEIGHT BASED ON OVERALL PERFORMANCE
        if len(trades) >= 20:
            win_rate = len(wins) / len(trades)
            avg_return = sum(t['actual_return'] or 0 for t in trades) / len(trades)
            
            old_weight = pattern.base_weight
            
            # Aggressive weight adjustment
            if win_rate >= 0.70 and avg_return > 0.02:
                pattern.base_weight = min(3.0, old_weight * 1.2)
            elif win_rate >= 0.60 and avg_return > 0.01:
                pattern.base_weight = min(2.5, old_weight * 1.1)
            elif win_rate < 0.40:
                pattern.base_weight = max(0.3, old_weight * 0.7)
            elif win_rate < 0.50:
                pattern.base_weight = max(0.5, old_weight * 0.85)
            
            if abs(pattern.base_weight - old_weight) > 0.1:
                learning_report['adjustments'].append({
                    'type': 'BASE_WEIGHT',
                    'old': f"{old_weight:.2f}",
                    'new': f"{pattern.base_weight:.2f}",
                    'reason': f"Win rate {win_rate:.1%}, Avg return {avg_return:.2%}"
                })
        
        # Update pattern stats
        pattern.total_trades = len(trades)
        pattern.wins = len(wins)
        pattern.losses = len(losses)
        pattern.total_return = sum(t['actual_return'] or 0 for t in trades)
        pattern.version += 1
        pattern.last_updated = datetime.now().isoformat()
        
        # Record this adjustment
        pattern.adjustments_made.append({
            'timestamp': datetime.now().isoformat(),
            'trades_analyzed': len(trades),
            'adjustments': learning_report['adjustments']
        })
        
        # Save updated pattern
        self.db.save_pattern(pattern)
        
        learning_report['new_parameters'] = {
            'base_weight': pattern.base_weight,
            'optimal_stop_pct': pattern.optimal_stop_pct,
            'optimal_target_pct': pattern.optimal_target_pct,
            'best_vix_regime': pattern.best_vix_regime,
            'best_time_of_day': pattern.best_time_of_day,
            'win_rate': pattern.win_rate,
            'version': pattern.version
        }
        
        return learning_report
    
    def _analyze_by_vix(self, trades: List[dict]) -> dict:
        """Analyze performance by VIX regime"""
        by_regime = defaultdict(list)
        
        for t in trades:
            if t['vix_regime'] and t['outcome'] in ['WIN', 'LOSS']:
                by_regime[t['vix_regime']].append(t['outcome'] == 'WIN')
        
        if not by_regime:
            return {'best_regime': None, 'confidence': 0}
        
        # Calculate win rate per regime
        regime_stats = {}
        for regime, outcomes in by_regime.items():
            if len(outcomes) >= 3:
                regime_stats[regime] = {
                    'win_rate': sum(outcomes) / len(outcomes),
                    'trades': len(outcomes)
                }
        
        if not regime_stats:
            return {'best_regime': None, 'confidence': 0}
        
        # Find best regime
        best_regime = max(regime_stats.keys(), key=lambda r: regime_stats[r]['win_rate'])
        worst_regime = min(regime_stats.keys(), key=lambda r: regime_stats[r]['win_rate'])
        
        # Calculate confidence based on sample size
        total_trades = sum(s['trades'] for s in regime_stats.values())
        confidence = min(1.0, total_trades / 20)
        
        # Calculate multipliers
        avg_win_rate = sum(s['win_rate'] for s in regime_stats.values()) / len(regime_stats)
        multipliers = {
            regime: stats['win_rate'] / avg_win_rate if avg_win_rate > 0 else 1.0
            for regime, stats in regime_stats.items()
        }
        
        return {
            'best_regime': best_regime,
            'worst_regime': worst_regime,
            'best_win_rate': regime_stats[best_regime]['win_rate'],
            'multipliers': multipliers,
            'confidence': confidence,
            'reason': f"{regime_stats[best_regime]['win_rate']:.1%} win rate in {best_regime} ({regime_stats[best_regime]['trades']} trades)"
        }
    
    def _analyze_by_time(self, trades: List[dict]) -> dict:
        """Analyze performance by time of day"""
        by_time = defaultdict(list)
        
        for t in trades:
            if t['time_of_day'] and t['outcome'] in ['WIN', 'LOSS']:
                by_time[t['time_of_day']].append(t['outcome'] == 'WIN')
        
        if not by_time:
            return {'best_time': None, 'confidence': 0}
        
        time_stats = {}
        for time, outcomes in by_time.items():
            if len(outcomes) >= 2:
                time_stats[time] = {
                    'win_rate': sum(outcomes) / len(outcomes),
                    'trades': len(outcomes)
                }
        
        if not time_stats:
            return {'best_time': None, 'confidence': 0}
        
        best_time = max(time_stats.keys(), key=lambda t: time_stats[t]['win_rate'])
        worst_time = min(time_stats.keys(), key=lambda t: time_stats[t]['win_rate'])
        
        total_trades = sum(s['trades'] for s in time_stats.values())
        confidence = min(1.0, total_trades / 15)
        
        avg_win_rate = sum(s['win_rate'] for s in time_stats.values()) / len(time_stats)
        multipliers = {
            time: stats['win_rate'] / avg_win_rate if avg_win_rate > 0 else 1.0
            for time, stats in time_stats.items()
        }
        
        return {
            'best_time': best_time,
            'worst_time': worst_time,
            'multipliers': multipliers,
            'confidence': confidence,
            'reason': f"{time_stats[best_time]['win_rate']:.1%} win rate at {best_time}"
        }
    
    def _analyze_by_day(self, trades: List[dict]) -> dict:
        """Analyze performance by day of week"""
        by_day = defaultdict(list)
        
        for t in trades:
            if t['day_of_week'] is not None and t['outcome'] in ['WIN', 'LOSS']:
                by_day[t['day_of_week']].append(t['outcome'] == 'WIN')
        
        if not by_day:
            return {'multipliers': {}}
        
        day_stats = {}
        for day, outcomes in by_day.items():
            if len(outcomes) >= 2:
                day_stats[day] = sum(outcomes) / len(outcomes)
        
        if not day_stats:
            return {'multipliers': {}}
        
        avg_rate = sum(day_stats.values()) / len(day_stats)
        multipliers = {
            day: rate / avg_rate if avg_rate > 0 else 1.0
            for day, rate in day_stats.items()
        }
        
        return {'multipliers': multipliers}
    
    def _analyze_stops(self, trades: List[dict]) -> dict:
        """Analyze stop placement effectiveness"""
        losses = [t for t in trades if t['outcome'] == 'LOSS' and t['max_adverse'] and t['entry_price']]
        
        if len(losses) < 3:
            return {'optimal_stop': None, 'confidence': 0}
        
        # Calculate how far price went against us before stopping out
        stop_distances = []
        for t in losses:
            actual_stop = abs(t['entry_price'] - t['stop_price']) / t['entry_price']
            adverse_move = abs(t['entry_price'] - t['max_adverse']) / t['entry_price']
            stop_distances.append({
                'planned_stop': actual_stop,
                'adverse_move': adverse_move,
                'exceeded_by': adverse_move - actual_stop
            })
        
        # If stops are consistently being hit and then price reverses,
        # the stop is too tight
        tight_stops = [s for s in stop_distances if s['exceeded_by'] < 0.005]  # Within 0.5% of stop
        
        if len(tight_stops) > len(stop_distances) * 0.5:
            # More than half the losses barely exceeded the stop
            avg_stop = statistics.mean(s['planned_stop'] for s in stop_distances)
            suggested_stop = avg_stop * 1.3  # Widen by 30%
            
            return {
                'optimal_stop': min(0.05, suggested_stop),  # Cap at 5%
                'confidence': min(1.0, len(losses) / 10),
                'reason': f"{len(tight_stops)}/{len(losses)} losses barely exceeded stop - widening recommended"
            }
        
        # If adverse moves are consistently much larger than stops,
        # might need even wider stops or pattern is too risky
        avg_adverse = statistics.mean(s['adverse_move'] for s in stop_distances)
        avg_stop = statistics.mean(s['planned_stop'] for s in stop_distances)
        
        if avg_adverse > avg_stop * 2:
            return {
                'optimal_stop': None,
                'confidence': 0.5,
                'reason': f"Large adverse moves ({avg_adverse:.1%} avg) - consider reducing position size"
            }
        
        return {'optimal_stop': None, 'confidence': 0}
    
    def _analyze_targets(self, trades: List[dict]) -> dict:
        """Analyze target effectiveness"""
        wins = [t for t in trades if t['outcome'] == 'WIN' and t['max_favorable'] and t['entry_price']]
        
        if len(wins) < 3:
            return {'optimal_target': None, 'confidence': 0}
        
        # How much further could we have gone?
        target_analysis = []
        for t in wins:
            target_distance = abs(t['target_price'] - t['entry_price']) / t['entry_price']
            max_move = abs(t['max_favorable'] - t['entry_price']) / t['entry_price']
            target_analysis.append({
                'target': target_distance,
                'max_move': max_move,
                'left_on_table': max_move - target_distance
            })
        
        # If we're consistently leaving money on the table, widen targets
        avg_left = statistics.mean(t['left_on_table'] for t in target_analysis)
        avg_target = statistics.mean(t['target'] for t in target_analysis)
        
        if avg_left > 0.01:  # Leaving >1% on average
            suggested_target = avg_target + (avg_left * 0.5)  # Capture half of what we're leaving
            return {
                'optimal_target': min(0.08, suggested_target),  # Cap at 8%
                'confidence': min(1.0, len(wins) / 10),
                'reason': f"Leaving avg {avg_left:.1%} on table - widening target"
            }
        
        return {'optimal_target': None, 'confidence': 0}
    
    def generate_learning_report(self, pattern_name: str = None) -> str:
        """Generate human-readable report of what the system has learned"""
        report = []
        report.append("=" * 70)
        report.append("           ADAPTIVE LEARNING REPORT")
        report.append("=" * 70)
        report.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report.append("")
        
        patterns = self.db.get_all_patterns()
        if pattern_name:
            patterns = [p for p in patterns if p.name == pattern_name]
        
        for pattern in patterns:
            report.append(f"\n{'─' * 50}")
            report.append(f"PATTERN: {pattern.name.upper()}")
            report.append(f"{'─' * 50}")
            report.append(f"Version: {pattern.version}")
            report.append(f"Total Trades: {pattern.total_trades}")
            report.append(f"Win Rate: {pattern.win_rate:.1%}")
            report.append(f"Avg Return: {pattern.avg_return:.2%}")
            report.append(f"Effective Weight: {pattern.effective_weight:.2f}")
            
            report.append("\n📈 LEARNED OPTIMIZATIONS:")
            if pattern.best_vix_regime:
                report.append(f"   • Best VIX Regime: {pattern.best_vix_regime}")
            if pattern.best_time_of_day:
                report.append(f"   • Best Time: {pattern.best_time_of_day}")
            if pattern.worst_time_of_day:
                report.append(f"   • Avoid: {pattern.worst_time_of_day}")
            report.append(f"   • Optimal Stop: {pattern.optimal_stop_pct:.1%}")
            report.append(f"   • Optimal Target: {pattern.optimal_target_pct:.1%}")
            
            if pattern.adjustments_made:
                report.append("\n📝 RECENT ADJUSTMENTS:")
                for adj in pattern.adjustments_made[-3:]:
                    report.append(f"   [{adj['timestamp'][:10]}] Analyzed {adj['trades_analyzed']} trades")
                    for change in adj.get('adjustments', []):
                        report.append(f"      • {change['type']}: {change['old']} → {change['new']}")
                        report.append(f"        Reason: {change['reason']}")
        
        # Overall learning stats
        report.append("\n" + "=" * 70)
        report.append("OVERALL LEARNING STATISTICS")
        report.append("=" * 70)
        
        learning_history = self.db.get_learning_history(limit=20)
        report.append(f"Total Learning Events: {len(learning_history)}")
        
        if learning_history:
            report.append("\nRecent Learning:")
            for event in learning_history[:5]:
                report.append(f"   [{event['timestamp'][:10]}] {event['pattern_name']}: {event['learning_type']}")
                report.append(f"      {event['old_value']} → {event['new_value']}")
        
        return "\n".join(report)


# ============================================================================
# INTEGRATION WITH MAIN SYSTEM
# ============================================================================

def create_learning_engine(db_path: str = "data/learning.db") -> AdaptiveLearningEngine:
    """Factory function to create learning engine"""
    db = LearningDatabase(db_path)
    return AdaptiveLearningEngine(db)


if __name__ == "__main__":
    # Demo
    engine = create_learning_engine()
    print(engine.generate_learning_report())
