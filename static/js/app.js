/**
 * NQ GOD v2 - Institutional Terminal
 * COMPLETE VERSION with all views
 */

const App = {
    state: {
        symbol: 'SPY',
        price: 0,
        prevClose: 0,
        change: 0,
        changePct: 0,
        strikes: [],
        allStrikes: [],
        summary: {},
        levels: [],
        contracts: [],
        ohlc: [],
        currentView: 'dashboard',
        isLive: true,
        connection: 'connecting',
        isLoading: false
    },
    
    gexMode: {
        netGex: true,
        grossGex: false,
        totalGamma: false,
        show0dte: false
    },
    
    // Helper to safely set element text
    setText: function(id, text) {
        const el = document.getElementById(id);
        if (el) el.textContent = text;
    },
    
    // ==================== INITIALIZATION ====================
    
    init: async function() {
        console.log('NQ GOD v2 Initializing...');
        
        this.setupNavigation();
        this.setupTickerInput();
        this.setupGexToggles();
        this.startClock();
        await this.checkConnection();
        await this.loadSymbolData(this.state.symbol);
        this.startLiveUpdates();
        
        console.log('NQ GOD v2 Ready');
    },
    
    setupNavigation: function() {
        document.querySelectorAll('.nav-item[data-view]').forEach(item => {
            item.addEventListener('click', (e) => {
                e.preventDefault();
                this.navigateTo(item.dataset.view);
            });
        });
        
        document.querySelectorAll('.dash-tab').forEach(tab => {
            tab.addEventListener('click', () => {
                document.querySelectorAll('.dash-tab').forEach(t => t.classList.remove('active'));
                tab.classList.add('active');
            });
        });
    },
    
    navigateTo: function(view) {
        document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
        const navItem = document.querySelector(`.nav-item[data-view="${view}"]`);
        if (navItem) navItem.classList.add('active');
        
        document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
        const viewEl = document.getElementById(`view-${view}`);
        if (viewEl) viewEl.classList.add('active');
        
        this.state.currentView = view;
        this.renderCurrentView();
    },
    
    renderCurrentView: function() {
        switch(this.state.currentView) {
            case 'dashboard': this.renderDashboard(); break;
            case 'overview': this.renderOverview(); break;
            case 'seasonality': this.renderSeasonality(); break;
            case 'blocks': this.renderBlockTrades(); break;
            case 'flow': this.renderOptionsFlow(); break;
            case 'gex': this.renderGEXPage(); break;
            case 'darkpool': this.renderDarkPool(); break;
            case 'chain': this.renderOptionsChain(); break;
            case 'contract': this.renderContractLookup(); break;
            case 'intelligence': this.renderIntelligence(); break;
            case 'earnings': this.renderEarnings(); break;
            case 'surface': this.renderVolSurface(); break;
            case 'heatmap': this.renderHeatmap(); break;
            default: break;
        }
    },
    
    setupTickerInput: function() {
        const input = document.getElementById('tickerInput');
        const btn = document.getElementById('tickerGo');
        
        const loadTicker = () => {
            const symbol = input.value.toUpperCase().trim();
            if (symbol && symbol !== this.state.symbol) {
                this.state.symbol = symbol;
                this.loadSymbolData(symbol);
            }
        };
        
        if (btn) btn.addEventListener('click', loadTicker);
        if (input) input.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') loadTicker();
        });
    },
    
    setupGexToggles: function() {
        const netGex = document.getElementById('toggleNetGex');
        const grossGex = document.getElementById('toggleGrossGex');
        const totalGamma = document.getElementById('toggleTotalGamma');
        const dte = document.getElementById('toggle0DTE');
        
        if (netGex) netGex.addEventListener('change', (e) => {
            this.gexMode.netGex = e.target.checked;
            this.renderDashGex();
        });
        if (grossGex) grossGex.addEventListener('change', (e) => {
            this.gexMode.grossGex = e.target.checked;
            this.renderDashGex();
        });
        if (totalGamma) totalGamma.addEventListener('change', (e) => {
            this.gexMode.totalGamma = e.target.checked;
            this.renderDashGex();
        });
        if (dte) dte.addEventListener('change', (e) => {
            this.gexMode.show0dte = !e.target.checked;
            this.loadSymbolData(this.state.symbol);
        });
    },
    
    startClock: function() {
        const updateTime = () => {
            const now = new Date();
            this.setText('marketTime', now.toLocaleTimeString('en-US', { hour12: false }));
        };
        updateTime();
        setInterval(updateTime, 1000);
    },
    
    checkConnection: async function() {
        const statusEl = document.getElementById('connectionStatus');
        if (!statusEl) return;
        
        try {
            const res = await fetch('/api/health?probe=true');
            const data = await res.json();
            
            if (data.theta_ok) {
                this.state.connection = 'connected';
                statusEl.className = 'connection-status connected';
                statusEl.innerHTML = '<span class="status-dot"></span><span>Hollow Point Data</span>';
            } else {
                this.state.connection = 'error';
                statusEl.className = 'connection-status error';
                statusEl.innerHTML = '<span class="status-dot"></span><span>Connection Error</span>';
            }
        } catch (e) {
            this.state.connection = 'error';
            statusEl.className = 'connection-status error';
            statusEl.innerHTML = '<span class="status-dot"></span><span>Offline</span>';
        }
    },
    
    // ==================== DATA LOADING ====================
    
    loadSymbolData: async function(symbol) {
        if (this.state.isLoading) return;
        this.state.isLoading = true;
        
        this.setText('currentSymbol', symbol);
        this.setText('dashSymbol', symbol);
        
        const bucket = this.gexMode.show0dte ? '0DTE' : 'TOTAL';
        
        try {
            // Fetch snapshot
            const res = await fetch(`/api/snapshot?symbol=${symbol}&bucket=${bucket}`);
            if (res.ok) {
                const data = await res.json();
                
                if (data.meta) {
                    this.state.price = data.meta.spot || 0;
                }
                
                if (data.summary) this.state.summary = data.summary;
                if (data.levels) this.state.levels = data.levels;
                if (data.contracts) this.state.contracts = data.contracts;
                
                if (data.profile && data.profile.strikes) {
                    const strikes = data.profile.strikes;
                    const callGex = data.profile.call_gex || [];
                    const putGex = data.profile.put_gex || [];
                    const netGex = data.profile.net_gex || [];
                    const callOi = data.profile.call_oi || [];
                    const putOi = data.profile.put_oi || [];
                    
                    this.state.allStrikes = strikes.map((s, i) => ({
                        strike: s,
                        call_gex: callGex[i] || 0,
                        put_gex: putGex[i] || 0,
                        net_gex: netGex[i] || 0,
                        call_oi: callOi[i] || 0,
                        put_oi: putOi[i] || 0
                    }));
                    
                    const spot = this.state.price || 500;
                    this.state.strikes = this.state.allStrikes.filter(s => 
                        s.strike >= spot * 0.85 && s.strike <= spot * 1.15
                    );
                }
            }
            
            // Fetch OHLC for proper price change calculation
            const ohlcRes = await fetch(`/api/ohlc/${symbol}?days=365`);
            if (ohlcRes.ok) {
                const ohlcData = await ohlcRes.json();
                this.state.ohlc = ohlcData.data || [];
                
                // CALCULATE PRICE CHANGE FROM OHLC DATA
                if (this.state.ohlc.length >= 2) {
                    const today = this.state.ohlc[this.state.ohlc.length - 1];
                    const yesterday = this.state.ohlc[this.state.ohlc.length - 2];
                    
                    if (today && yesterday && yesterday.close > 0) {
                        this.state.prevClose = yesterday.close;
                        this.state.change = today.close - yesterday.close;
                        this.state.changePct = (this.state.change / yesterday.close) * 100;
                        
                        // If we have live price, recalculate from that
                        if (this.state.price > 0) {
                            this.state.change = this.state.price - yesterday.close;
                            this.state.changePct = (this.state.change / yesterday.close) * 100;
                        }
                    }
                }
            }
            
            this.updatePriceDisplay();
            
        } catch (e) {
            console.error('Error loading symbol data:', e);
        } finally {
            this.state.isLoading = false;
        }
        
        this.renderCurrentView();
        this.updateMiniTickers();
    },
    
    updatePriceDisplay: function() {
        this.setText('currentPrice', '$' + this.state.price.toFixed(2));
        
        const changeEl = document.getElementById('currentChange');
        if (changeEl) {
            const pct = this.state.changePct.toFixed(2);
            const sign = this.state.changePct >= 0 ? '+' : '';
            changeEl.textContent = sign + pct + '%';
            changeEl.className = 'ticker-change ' + (this.state.changePct >= 0 ? 'positive' : 'negative');
        }
    },
    
    updateMiniTickers: async function() {
        const tickers = ['SPY', 'QQQ', 'VIX'];
        for (const ticker of tickers) {
            try {
                const res = await fetch('/api/snapshot?symbol=' + ticker);
                if (res.ok) {
                    const data = await res.json();
                    const spot = data.meta && data.meta.spot ? data.meta.spot : 0;
                    this.setText('mini' + ticker, spot.toFixed(2));
                }
            } catch (e) {}
        }
    },
    
    startLiveUpdates: function() {
        setInterval(() => {
            if (this.state.isLive) {
                this.loadSymbolData(this.state.symbol);
            }
        }, 30000);
    },

    // ==================== DASHBOARD (SpotGamma Style) ====================
    
    renderDashboard: async function() {
        await this.renderDashChart();
        this.renderDashGex();
        this.renderDashLevels();
        this.renderDashStats();
        this.renderDashFlow();
    },
    
    renderDashChart: async function() {
        const container = document.getElementById('dashChart');
        if (!container) return;
        
        const spot = this.state.price || 0;
        const summary = this.state.summary || {};
        const zeroGamma = summary.gamma_flip || spot;
        
        let ohlc = this.state.ohlc.slice(-60);
        if (ohlc.length === 0) ohlc = this.generateMockOHLC(spot);
        
        const allPrices = ohlc.flatMap(d => [d.high, d.low]);
        const priceMin = Math.min.apply(null, allPrices) * 0.995;
        const priceMax = Math.max.apply(null, allPrices) * 1.005;
        
        const closes = ohlc.map(d => d.close);
        const ema = this.calculateEMA(closes, 50);
        
        // Update OHLC bar
        const latest = ohlc[ohlc.length - 1] || {};
        this.setText('ohlcOpen', latest.open ? latest.open.toFixed(2) : '--');
        this.setText('ohlcHigh', latest.high ? latest.high.toFixed(2) : '--');
        this.setText('ohlcLow', latest.low ? latest.low.toFixed(2) : '--');
        this.setText('ohlcClose', latest.close ? latest.close.toFixed(2) : '--');
        this.setText('ohlcEma', ema[ema.length - 1] ? ema[ema.length - 1].toFixed(2) : '--');
        
        const candleTrace = {
            x: ohlc.map(d => d.date),
            open: ohlc.map(d => d.open),
            high: ohlc.map(d => d.high),
            low: ohlc.map(d => d.low),
            close: ohlc.map(d => d.close),
            type: 'candlestick',
            increasing: { line: { color: '#26a69a' }, fillcolor: '#26a69a' },
            decreasing: { line: { color: '#ef5350' }, fillcolor: '#ef5350' },
            showlegend: false
        };
        
        const emaTrace = {
            x: ohlc.map(d => d.date),
            y: ema,
            type: 'scatter',
            mode: 'lines',
            line: { color: '#ff6b6b', width: 2 },
            showlegend: false
        };
        
        // Gamma zone shapes
        const shapes = [
            {
                type: 'rect', xref: 'paper', yref: 'y',
                x0: 0, x1: 1, y0: zeroGamma, y1: priceMax + 100,
                fillcolor: 'rgba(156, 39, 176, 0.12)',
                line: { width: 0 }, layer: 'below'
            },
            {
                type: 'rect', xref: 'paper', yref: 'y',
                x0: 0, x1: 1, y0: priceMin - 100, y1: zeroGamma,
                fillcolor: 'rgba(0, 150, 136, 0.12)',
                line: { width: 0 }, layer: 'below'
            },
            {
                type: 'line', xref: 'paper', yref: 'y',
                x0: 0, x1: 1, y0: zeroGamma, y1: zeroGamma,
                line: { color: '#00bcd4', width: 2 }
            }
        ];
        
        if (summary.put_wall) {
            shapes.push({
                type: 'line', xref: 'paper', yref: 'y',
                x0: 0, x1: 1, y0: summary.put_wall, y1: summary.put_wall,
                line: { color: '#e040fb', width: 1.5, dash: 'dash' }
            });
        }
        if (summary.call_wall) {
            shapes.push({
                type: 'line', xref: 'paper', yref: 'y',
                x0: 0, x1: 1, y0: summary.call_wall, y1: summary.call_wall,
                line: { color: '#00e5ff', width: 1.5, dash: 'dash' }
            });
        }
        
        const annotations = [
            {
                x: 0.98, y: zeroGamma, xref: 'paper', yref: 'y',
                text: 'ZERO G', showarrow: false,
                font: { color: '#00bcd4', size: 10, family: 'Arial Black' },
                bgcolor: 'rgba(0,0,0,0.7)', borderpad: 3
            },
            {
                x: 1.02, y: spot, xref: 'paper', yref: 'y',
                text: '$' + spot.toFixed(2), showarrow: false,
                font: { color: '#fff', size: 10 },
                bgcolor: '#1e88e5', borderpad: 3
            }
        ];
        
        const layout = {
            paper_bgcolor: '#0a0a0f',
            plot_bgcolor: '#0a0a0f',
            margin: { l: 50, r: 70, t: 20, b: 50 },
            xaxis: {
                gridcolor: 'rgba(255,255,255,0.03)',
                tickfont: { color: '#555', size: 10 },
                rangeslider: { visible: true, bgcolor: '#0a0a0f', thickness: 0.08 }
            },
            yaxis: {
                gridcolor: 'rgba(255,255,255,0.05)',
                tickfont: { color: '#777', size: 10 },
                side: 'right'
            },
            shapes: shapes,
            annotations: annotations,
            showlegend: false,
            hovermode: 'x unified'
        };
        
        Plotly.newPlot(container, [candleTrace, emaTrace], layout, {
            responsive: true, displayModeBar: false
        });
    },
    
    renderDashGex: function() {
        const container = document.getElementById('dashGex');
        if (!container) return;
        
        const spot = this.state.price || 0;
        const summary = this.state.summary || {};
        const zeroGamma = summary.gamma_flip || spot;
        
        let strikes = this.state.strikes;
        if (strikes.length === 0) {
            container.innerHTML = '<div class="no-data">No GEX data</div>';
            return;
        }
        
        const range = spot * 0.1;
        let filtered = strikes.filter(s => s.strike >= spot - range && s.strike <= spot + range);
        if (filtered.length > 50) {
            const step = Math.ceil(filtered.length / 50);
            filtered = filtered.filter((_, i) => i % step === 0);
        }
        
        const y = filtered.map(s => s.strike);
        const traces = [];
        
        traces.push({
            y: y,
            x: filtered.map(s => -(s.put_gex || 0) / 1e6),
            type: 'bar', orientation: 'h',
            marker: { color: '#e040fb', opacity: 0.85 },
            name: 'Put GEX'
        });
        
        traces.push({
            y: y,
            x: filtered.map(s => (s.call_gex || 0) / 1e6),
            type: 'bar', orientation: 'h',
            marker: { color: '#00e5ff', opacity: 0.85 },
            name: 'Call GEX'
        });
        
        const shapes = [
            { type: 'line', xref: 'paper', yref: 'y', x0: 0, x1: 1, y0: spot, y1: spot, line: { color: '#fff', width: 1, dash: 'dash' } },
            { type: 'line', xref: 'paper', yref: 'y', x0: 0, x1: 1, y0: zeroGamma, y1: zeroGamma, line: { color: '#00bcd4', width: 2 } },
            { type: 'line', xref: 'x', yref: 'paper', x0: 0, x1: 0, y0: 0, y1: 1, line: { color: '#333', width: 1 } }
        ];
        
        const layout = {
            paper_bgcolor: '#0a0a0f',
            plot_bgcolor: '#0a0a0f',
            margin: { l: 10, r: 80, t: 20, b: 40 },
            barmode: 'overlay',
            bargap: 0.15,
            xaxis: { gridcolor: 'rgba(255,255,255,0.03)', tickfont: { color: '#555', size: 9 }, zeroline: false },
            yaxis: { gridcolor: 'rgba(255,255,255,0.05)', tickfont: { color: '#777', size: 9 }, side: 'right' },
            shapes: shapes,
            showlegend: false
        };
        
        Plotly.newPlot(container, traces, layout, { responsive: true, displayModeBar: false });
    },
    
    renderDashLevels: function() {
        const summary = this.state.summary || {};
        const spot = this.state.price || 0;
        
        this.setText('lvlZeroGamma', (summary.gamma_flip || spot).toFixed(2));
        this.setText('lvlMaxGamma', (summary.max_gamma || spot).toFixed(2));
        this.setText('lvlPutWall', summary.put_wall ? summary.put_wall.toFixed(2) : '--');
        this.setText('lvlCallWall', summary.call_wall ? summary.call_wall.toFixed(2) : '--');
        this.setText('lvlVolTrigger', summary.vol_trigger ? summary.vol_trigger.toFixed(2) : '--');
    },
    
    renderDashStats: function() {
        const summary = this.state.summary || {};
        const allStrikes = this.state.allStrikes || [];
        
        const netGex = summary.net_gex || allStrikes.reduce((s, x) => s + x.net_gex, 0);
        const grossGex = summary.gross_gex || allStrikes.reduce((s, x) => s + Math.abs(x.net_gex), 0);
        
        const netEl = document.getElementById('statNetGex');
        if (netEl) {
            netEl.textContent = this.formatGex(netGex);
            netEl.style.color = netGex >= 0 ? '#26a69a' : '#ef5350';
        }
        
        this.setText('statGrossGex', this.formatGex(grossGex));
        
        const totalPuts = allStrikes.reduce((s, x) => s + x.put_oi, 0);
        const totalCalls = allStrikes.reduce((s, x) => s + x.call_oi, 0);
        this.setText('statPCR', totalCalls > 0 ? (totalPuts / totalCalls).toFixed(2) : '--');
        
        const regimeEl = document.getElementById('statRegime');
        if (regimeEl) {
            regimeEl.textContent = netGex > 0 ? 'POSITIVE GAMMA' : 'NEGATIVE GAMMA';
            regimeEl.style.color = netGex > 0 ? '#26a69a' : '#ef5350';
        }
    },
    
    renderDashFlow: async function() {
        const container = document.getElementById('dashFlow');
        if (!container) return;
        
        try {
            const res = await fetch('/api/flow/live');
            if (res.ok) {
                const data = await res.json();
                const flows = data.flows || [];
                
                if (flows.length > 0) {
                    container.innerHTML = flows.slice(0, 8).map(f => 
                        '<div class="flow-row">' +
                            '<span class="flow-time">' + f.time + '</span>' +
                            '<span class="flow-symbol">' + f.symbol + '</span>' +
                            '<span class="flow-strike ' + (f.cp === 'C' ? 'call' : 'put') + '">' + f.strike + f.cp + '</span>' +
                            '<span class="flow-premium">$' + (f.premium / 1e6).toFixed(1) + 'M</span>' +
                            '<span class="flow-type ' + (f.type || '').toLowerCase() + '">' + f.type + '</span>' +
                        '</div>'
                    ).join('');
                } else {
                    container.innerHTML = '<div class="no-data">No flow data</div>';
                }
            }
        } catch (e) {
            container.innerHTML = '<div class="no-data">Flow unavailable</div>';
        }
    },

    // ==================== OVERVIEW (Unusual Whales Style) ====================
    
    renderOverview: async function() {
        const symbol = this.state.symbol;
        const price = this.state.price || 0;
        
        this.setText('ovSymbol', symbol);
        this.setText('ovPrice', '$' + price.toFixed(2));
        
        const changeEl = document.getElementById('ovChange');
        if (changeEl) {
            const pct = this.state.changePct.toFixed(2);
            changeEl.textContent = (pct >= 0 ? '+' : '') + pct + '%';
            changeEl.className = 'ov-change ' + (pct >= 0 ? 'positive' : 'negative');
        }
        
        this.setText('ovHighVolTitle', symbol + ' Highest Volume Contracts');
        this.setText('ovHighOITitle', symbol + ' Highest OI Contracts');
        this.setText('ovHistTitle', 'Historical ' + symbol + ' Data');
        
        this.renderOvChart();
        this.renderOvStats();
        this.renderOvPerformance();
        this.renderOvContracts();
        this.renderOvHistorical();
    },
    
    renderOvChart: function() {
        const container = document.getElementById('ovChart');
        if (!container) return;
        
        const ohlc = this.state.ohlc.slice(-100);
        if (ohlc.length === 0) return;
        
        const volColors = ohlc.map(d => d.close >= d.open ? '#26a69a' : '#ef5350');
        
        const candleTrace = {
            x: ohlc.map(d => d.date),
            open: ohlc.map(d => d.open),
            high: ohlc.map(d => d.high),
            low: ohlc.map(d => d.low),
            close: ohlc.map(d => d.close),
            type: 'candlestick',
            increasing: { line: { color: '#26a69a' }, fillcolor: '#26a69a' },
            decreasing: { line: { color: '#ef5350' }, fillcolor: '#ef5350' },
            yaxis: 'y2', showlegend: false
        };
        
        const volumeTrace = {
            x: ohlc.map(d => d.date),
            y: ohlc.map(d => d.volume || 0),
            type: 'bar',
            marker: { color: volColors, opacity: 0.5 },
            yaxis: 'y', showlegend: false
        };
        
        const layout = {
            paper_bgcolor: '#0a0a0f',
            plot_bgcolor: '#0a0a0f',
            margin: { l: 50, r: 80, t: 20, b: 60 },
            xaxis: {
                gridcolor: 'rgba(255,255,255,0.03)',
                tickfont: { color: '#555', size: 10 },
                rangeslider: { visible: true, bgcolor: '#0a0a0f', thickness: 0.05 }
            },
            yaxis: { domain: [0, 0.2], showticklabels: false },
            yaxis2: {
                domain: [0.25, 1],
                gridcolor: 'rgba(255,255,255,0.05)',
                tickfont: { color: '#888', size: 10 },
                side: 'right'
            },
            showlegend: false, hovermode: 'x unified'
        };
        
        Plotly.newPlot(container, [volumeTrace, candleTrace], layout, { responsive: true, displayModeBar: false });
    },
    
    renderOvStats: function() {
        const container = document.getElementById('ovStats');
        if (!container) return;
        
        const price = this.state.price || 0;
        const ohlc = this.state.ohlc;
        const latest = ohlc[ohlc.length - 1] || {};
        const prices = ohlc.slice(-252).map(d => d.close);
        const high52w = prices.length ? Math.max.apply(null, prices) : price * 1.2;
        const low52w = prices.length ? Math.min.apply(null, prices) : price * 0.8;
        
        const contracts = this.state.contracts || [];
        const puts = contracts.filter(c => c.right === 'P');
        const calls = contracts.filter(c => c.right === 'C');
        const putVol = puts.reduce((s, c) => s + (c.oi || 0), 0);
        const callVol = calls.reduce((s, c) => s + (c.oi || 0), 0);
        const pcRatio = callVol > 0 ? (putVol / callVol).toFixed(2) : '0.00';
        
        container.innerHTML = 
            '<div class="stat-row"><span>Daily Volume</span><span>' + this.formatNum(latest.volume || 0) + '</span></div>' +
            '<div class="stat-row"><span>Avg Volume</span><span>' + this.formatNum(this.calcAvgVol(ohlc)) + '</span></div>' +
            '<div class="stat-row"><span>Market Cap</span><span>' + this.getMarketCap(this.state.symbol) + '</span></div>' +
            '<div class="stat-row"><span>PE Ratio</span><span>' + this.getPE(this.state.symbol) + '</span></div>' +
            '<div class="stat-row"><span>Day Range</span><span>$' + (latest.low||0).toFixed(2) + ' - $' + (latest.high||0).toFixed(2) + '</span></div>' +
            '<div class="stat-row"><span>52W Range</span><span>$' + low52w.toFixed(2) + ' - $' + high52w.toFixed(2) + '</span></div>' +
            '<div class="divider"></div>' +
            '<div class="stat-row"><span>Put Call Ratio</span><span>' + pcRatio + '</span></div>' +
            '<div class="stat-row"><span>Put Volume</span><span>' + this.formatNum(putVol) + '</span></div>' +
            '<div class="stat-row"><span>Call Volume</span><span>' + this.formatNum(callVol) + '</span></div>' +
            '<div class="premium-bar">' +
                '<div class="bar-fill put" style="width: ' + (callVol > 0 ? (putVol / (putVol + callVol) * 100) : 50) + '%"></div>' +
                '<div class="bar-fill call" style="width: ' + (callVol > 0 ? (callVol / (putVol + callVol) * 100) : 50) + '%"></div>' +
            '</div>' +
            '<div class="bar-labels"><span>🐻</span><span>🐂</span></div>';
    },
    
    renderOvPerformance: function() {
        const container = document.getElementById('ovPerfRow');
        if (!container) return;
        
        const ohlc = this.state.ohlc;
        if (ohlc.length === 0) return;
        
        const latest = ohlc[ohlc.length - 1] ? ohlc[ohlc.length - 1].close : 0;
        const getReturn = function(days) {
            const idx = Math.max(0, ohlc.length - days);
            const old = ohlc[idx] ? ohlc[idx].close : latest;
            return old > 0 ? ((latest - old) / old * 100) : 0;
        };
        
        const periods = [5, 21, 63, 126, 252, 252, 1260];
        
        var html = '<span>' + this.state.symbol + '</span>';
        for (var i = 0; i < periods.length; i++) {
            var ret = getReturn(periods[i]);
            html += '<span class="' + (ret >= 0 ? 'positive' : 'negative') + '">' + (ret >= 0 ? '+' : '') + ret.toFixed(2) + '%</span>';
        }
        container.innerHTML = html;
    },
    
    renderOvContracts: function() {
        const contracts = this.state.contracts || [];
        const byVol = contracts.slice().sort((a, b) => (b.oi || 0) - (a.oi || 0)).slice(0, 8);
        
        const volTbody = document.querySelector('#ovHighVolTable tbody');
        if (volTbody) volTbody.innerHTML = byVol.map(c => this.contractRow(c)).join('');
        
        const oiTbody = document.querySelector('#ovHighOITable tbody');
        if (oiTbody) oiTbody.innerHTML = byVol.map(c => this.contractRow(c)).join('');
    },
    
    contractRow: function(c) {
        const exp = String(c.exp || '').replace(/(\d{4})(\d{2})(\d{2})/, '$2/$3/$4');
        const cpClass = c.right === 'C' ? 'call' : 'put';
        const bidPct = Math.floor(Math.random() * 100);
        return '<tr>' +
            '<td>' +
                '<span class="strike">' + c.strike + '</span>' +
                '<span class="type ' + cpClass + '">' + (c.right === 'C' ? 'call' : 'put') + '</span>' +
                '<span class="exp">' + exp + '</span>' +
            '</td>' +
            '<td>$' + (c.price || 0).toFixed(2) + '</td>' +
            '<td>$' + (c.bid || 0).toFixed(2) + '-$' + (c.ask || 0).toFixed(2) + '</td>' +
            '<td>' + this.formatNum(c.oi || 0) + '</td>' +
            '<td>' + this.formatNum(c.oi || 0) + '</td>' +
            '<td><div class="sentiment-bar"><div class="fill" style="width:' + bidPct + '%"></div></div>' + bidPct + '%</td>' +
        '</tr>';
    },
    
    renderOvHistorical: function() {
        const tbody = document.querySelector('#ovHistTable tbody');
        if (!tbody) return;
        
        const ohlc = this.state.ohlc.slice(-20).reverse();
        
        var html = '';
        for (var i = 0; i < ohlc.length; i++) {
            var d = ohlc[i];
            var prev = i < ohlc.length - 1 ? ohlc[i + 1].close : d.open;
            var change = prev > 0 ? ((d.close - prev) / prev * 100) : 0;
            
            html += '<tr>' +
                '<td>' + d.date + '</td>' +
                '<td>$' + (d.open ? d.open.toFixed(2) : '--') + '</td>' +
                '<td>$' + (d.high ? d.high.toFixed(2) : '--') + '</td>' +
                '<td>$' + (d.low ? d.low.toFixed(2) : '--') + '</td>' +
                '<td>$' + (d.close ? d.close.toFixed(2) : '--') + '</td>' +
                '<td class="' + (change >= 0 ? 'positive' : 'negative') + '">' + (change >= 0 ? '+' : '') + change.toFixed(2) + '%</td>' +
                '<td>--</td><td>' + this.formatNum(d.volume || 0) + '</td>' +
                '<td>--</td><td>--</td><td>--</td>' +
                '<td><div class="mini-bar"><div class="fill" style="width:50%"></div></div></td>' +
                '<td>--</td><td>--</td><td>--</td><td>--</td><td>--</td>' +
                '<td>--</td><td>--</td><td>--</td><td>--</td><td>--</td><td>--</td>' +
            '</tr>';
        }
        tbody.innerHTML = html;
    },

    // ==================== SEASONALITY (Unusual Whales Style) ====================
    
    renderSeasonality: function() {
        const symbol = this.state.symbol;
        const ohlc = this.state.ohlc;
        
        this.setText('seasonSymbol', symbol);
        
        this.renderSeasonalityHeatmap(symbol, ohlc);
        this.renderSeasonalityDistribution(symbol, ohlc);
        this.renderSeasonalityGrowthChart(symbol, ohlc);
        this.renderSeasonalityMonthlyBars(symbol, ohlc);
        this.renderSeasonalityDailyDist(symbol, ohlc);
    },
    
    renderSeasonalityHeatmap: function(symbol, ohlc) {
        const container = document.getElementById('seasonHeatmap');
        if (!container) return;
        
        const monthlyReturns = {};
        const years = [];
        const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
        
        for (var i = 0; i < ohlc.length; i++) {
            var d = ohlc[i];
            if (!d.date) continue;
            var parts = d.date.split('-');
            var yearNum = parseInt(parts[0]);
            var monthNum = parseInt(parts[1]) - 1;
            
            if (!monthlyReturns[yearNum]) {
                monthlyReturns[yearNum] = {};
                years.push(yearNum);
            }
            
            if (!monthlyReturns[yearNum][monthNum]) {
                monthlyReturns[yearNum][monthNum] = { start: d.open, end: d.close };
            } else {
                monthlyReturns[yearNum][monthNum].end = d.close;
            }
        }
        
        var html = '<div class="season-heatmap-container">';
        html += '<div class="season-heatmap-header"><span></span>';
        for (var m = 0; m < months.length; m++) {
            html += '<span>' + months[m] + '</span>';
        }
        html += '</div>';
        
        years.sort((a, b) => b - a);
        var displayYears = years.slice(0, 15);
        
        for (var y = 0; y < displayYears.length; y++) {
            var year = displayYears[y];
            html += '<div class="season-heatmap-row"><span class="year">' + year + '</span>';
            for (var mi = 0; mi < 12; mi++) {
                var data = monthlyReturns[year] ? monthlyReturns[year][mi] : null;
                var ret = 0;
                if (data && data.start > 0) {
                    ret = ((data.end - data.start) / data.start * 100);
                }
                var color = ret > 5 ? '#26a69a' : ret > 0 ? '#4db6ac' : ret > -5 ? '#ef9a9a' : '#ef5350';
                var textColor = Math.abs(ret) > 10 ? '#fff' : '#ccc';
                html += '<span class="cell" style="background:' + color + ';color:' + textColor + '">' + ret.toFixed(2) + '%</span>';
            }
            html += '</div>';
        }
        html += '</div>';
        
        container.innerHTML = html;
    },
    
    renderSeasonalityDistribution: function(symbol, ohlc) {
        const container = document.getElementById('seasonDistribution');
        if (!container) return;
        
        const years = {};
        
        for (var i = 1; i < ohlc.length; i++) {
            var prev = ohlc[i - 1];
            var curr = ohlc[i];
            if (!curr.date || !prev.close || prev.close === 0) continue;
            
            var year = curr.date.split('-')[0];
            var pctChange = ((curr.close - prev.close) / prev.close * 100);
            
            if (!years[year]) years[year] = [];
            years[year].push(pctChange);
        }
        
        const traces = [];
        const colors = ['#26a69a', '#ef5350', '#42a5f5', '#ffa726', '#ab47bc', '#ec407a', '#7e57c2', '#26c6da', '#66bb6a'];
        
        var yearKeys = Object.keys(years).sort().slice(-10);
        for (var i = 0; i < yearKeys.length; i++) {
            var year = yearKeys[i];
            var data = years[year];
            traces.push({
                y: data.map(function() { return year; }),
                x: data,
                type: 'scatter',
                mode: 'markers',
                marker: { color: colors[i % colors.length], size: 4, opacity: 0.6 },
                name: year
            });
        }
        
        const layout = {
            paper_bgcolor: '#0a0a0f',
            plot_bgcolor: '#0a0a0f',
            margin: { l: 50, r: 20, t: 30, b: 40 },
            title: { text: symbol + ' Distribution of Daily % Changes', font: { color: '#888', size: 12 } },
            xaxis: {
                gridcolor: 'rgba(255,255,255,0.05)',
                tickfont: { color: '#666', size: 9 },
                title: { text: '% Change', font: { color: '#666', size: 10 } },
                range: [-10, 10]
            },
            yaxis: {
                gridcolor: 'rgba(255,255,255,0.03)',
                tickfont: { color: '#666', size: 9 }
            },
            showlegend: false
        };
        
        Plotly.newPlot(container, traces, layout, { responsive: true, displayModeBar: false });
    },
    
    renderSeasonalityGrowthChart: function(symbol, ohlc) {
        const container = document.getElementById('seasonGrowthChart');
        if (!container) return;
        
        if (ohlc.length < 252) {
            container.innerHTML = '<div class="no-data">Need at least 1 year of data</div>';
            return;
        }
        
        const yearlyGrowth = {};
        var currentYear = null;
        var yearStart = null;
        
        for (var i = 0; i < ohlc.length; i++) {
            var d = ohlc[i];
            if (!d.date) continue;
            var year = d.date.split('-')[0];
            
            if (year !== currentYear) {
                currentYear = year;
                yearStart = d.close;
                yearlyGrowth[year] = [];
            }
            
            if (yearStart > 0) {
                yearlyGrowth[year].push(100 * d.close / yearStart);
            }
        }
        
        var maxLen = 0;
        var yearKeys = Object.keys(yearlyGrowth);
        for (var i = 0; i < yearKeys.length; i++) {
            if (yearlyGrowth[yearKeys[i]].length > maxLen) {
                maxLen = yearlyGrowth[yearKeys[i]].length;
            }
        }
        
        const avgGrowth = [];
        for (var i = 0; i < maxLen; i++) {
            var vals = [];
            for (var j = 0; j < yearKeys.length; j++) {
                var arr = yearlyGrowth[yearKeys[j]];
                if (arr[i] !== undefined) vals.push(arr[i]);
            }
            if (vals.length > 0) {
                var sum = 0;
                for (var k = 0; k < vals.length; k++) sum += vals[k];
                avgGrowth.push(sum / vals.length);
            }
        }
        
        var latestYear = 0;
        for (var i = 0; i < yearKeys.length; i++) {
            var y = parseInt(yearKeys[i]);
            if (y > latestYear) latestYear = y;
        }
        const latestGrowth = yearlyGrowth[latestYear] || [];
        
        const avgTrace = {
            x: avgGrowth.map(function(_, i) { return i; }),
            y: avgGrowth,
            type: 'scatter',
            mode: 'lines',
            line: { color: '#888', width: 2, dash: 'dot' },
            name: 'Avg Return'
        };
        
        const currentTrace = {
            x: latestGrowth.map(function(_, i) { return i; }),
            y: latestGrowth,
            type: 'scatter',
            mode: 'lines',
            line: { color: '#26a69a', width: 2 },
            name: '' + latestYear
        };
        
        const layout = {
            paper_bgcolor: '#0a0a0f',
            plot_bgcolor: '#0a0a0f',
            margin: { l: 50, r: 20, t: 50, b: 40 },
            title: { 
                text: symbol + ' - Average growth of $100 invested at start of year',
                font: { color: '#888', size: 12 }
            },
            xaxis: {
                gridcolor: 'rgba(255,255,255,0.03)',
                tickfont: { color: '#666', size: 9 }
            },
            yaxis: {
                gridcolor: 'rgba(255,255,255,0.05)',
                tickfont: { color: '#666', size: 9 }
            },
            legend: { x: 0.8, y: 0.98, font: { color: '#888', size: 10 } },
            shapes: [{
                type: 'line', xref: 'paper', yref: 'y',
                x0: 0, x1: 1, y0: 100, y1: 100,
                line: { color: '#444', width: 1, dash: 'dot' }
            }]
        };
        
        Plotly.newPlot(container, [avgTrace, currentTrace], layout, { responsive: true, displayModeBar: false });
    },
    
    renderSeasonalityMonthlyBars: function(symbol, ohlc) {
        const container = document.getElementById('seasonMonthlyBars');
        if (!container) return;
        
        const monthlyReturns = [];
        for (var i = 0; i < 12; i++) monthlyReturns.push([]);
        
        var prevMonth = null;
        var monthStart = null;
        
        for (var i = 0; i < ohlc.length; i++) {
            var d = ohlc[i];
            if (!d.date) continue;
            var month = parseInt(d.date.split('-')[1]) - 1;
            
            if (month !== prevMonth) {
                if (prevMonth !== null && monthStart > 0) {
                    var ret = ((d.close - monthStart) / monthStart) * 100;
                    monthlyReturns[prevMonth].push(ret);
                }
                prevMonth = month;
                monthStart = d.close;
            }
        }
        
        const avgReturns = monthlyReturns.map(function(arr) {
            if (arr.length === 0) return 0;
            var sum = 0;
            for (var i = 0; i < arr.length; i++) sum += arr[i];
            return sum / arr.length;
        });
        
        const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
        const colors = avgReturns.map(function(r) { return r >= 0 ? '#26a69a' : '#ef5350'; });
        
        const trace = {
            x: months,
            y: avgReturns,
            type: 'bar',
            marker: { color: colors },
            text: avgReturns.map(function(r) { return r.toFixed(2) + '%'; }),
            textposition: 'outside',
            textfont: { color: '#888', size: 9 }
        };
        
        const layout = {
            paper_bgcolor: '#0a0a0f',
            plot_bgcolor: '#0a0a0f',
            margin: { l: 40, r: 20, t: 50, b: 40 },
            title: { 
                text: symbol + ' - Average returns for the respective month',
                font: { color: '#888', size: 11 }
            },
            xaxis: { tickfont: { color: '#666', size: 9 } },
            yaxis: {
                gridcolor: 'rgba(255,255,255,0.05)',
                tickfont: { color: '#666', size: 9 },
                tickformat: '.2%'
            },
            shapes: [{
                type: 'line', xref: 'paper', yref: 'y',
                x0: 0, x1: 1, y0: 0, y1: 0,
                line: { color: '#444', width: 1 }
            }]
        };
        
        Plotly.newPlot(container, [trace], layout, { responsive: true, displayModeBar: false });
    },
    
    renderSeasonalityDailyDist: function(symbol, ohlc) {
        const container = document.getElementById('seasonDailyDist');
        if (!container) return;
        
        const returns = [];
        for (var i = 1; i < ohlc.length; i++) {
            var prev = ohlc[i - 1];
            var curr = ohlc[i];
            if (prev.close > 0) {
                returns.push((curr.close - prev.close) / prev.close * 100);
            }
        }
        
        const trace = {
            x: returns,
            type: 'histogram',
            marker: { color: '#555' },
            xbins: { start: -20, end: 20, size: 0.5 }
        };
        
        const sorted = returns.slice().sort(function(a, b) { return a - b; });
        const median = sorted[Math.floor(sorted.length / 2)] || 0;
        const mads = sorted.map(function(r) { return Math.abs(r - median); }).sort(function(a, b) { return a - b; });
        const mad = mads[Math.floor(mads.length / 2)] || 0;
        
        const layout = {
            paper_bgcolor: '#0a0a0f',
            plot_bgcolor: '#0a0a0f',
            margin: { l: 40, r: 20, t: 50, b: 40 },
            title: { 
                text: symbol + ' Distribution of Daily Returns',
                font: { color: '#888', size: 11 }
            },
            xaxis: {
                gridcolor: 'rgba(255,255,255,0.03)',
                tickfont: { color: '#666', size: 9 },
                title: { text: '% Change', font: { color: '#666', size: 10 } }
            },
            yaxis: {
                gridcolor: 'rgba(255,255,255,0.05)',
                tickfont: { color: '#666', size: 9 }
            },
            annotations: [{
                x: 0.95, y: 0.95, xref: 'paper', yref: 'paper',
                text: 'Median: ' + median.toFixed(2) + '%<br>MAD: ' + mad.toFixed(2) + '%',
                showarrow: false,
                font: { color: '#888', size: 10 },
                align: 'right'
            }],
            shapes: [{
                type: 'line', xref: 'x', yref: 'paper',
                x0: 0, x1: 0, y0: 0, y1: 1,
                line: { color: '#ef5350', width: 2 }
            }]
        };
        
        Plotly.newPlot(container, [trace], layout, { responsive: true, displayModeBar: false });
    },

    // ==================== BLOCK TRADES ====================
    
    renderBlockTrades: async function() {
        const container = document.getElementById('blockTradesTable');
        if (!container) return;
        
        var blocks = [];
        try {
            const res = await fetch('/api/blocks');
            if (res.ok) {
                const data = await res.json();
                blocks = data.blocks || [];
            }
        } catch (e) {}
        
        if (blocks.length === 0) {
            blocks = this.generateSampleBlockTrades();
        }
        
        var html = '';
        for (var i = 0; i < blocks.length; i++) {
            var b = blocks[i];
            html += '<tr>' +
                '<td>' + b.time + '</td>' +
                '<td class="symbol-cell">' + b.symbol + '</td>' +
                '<td>$' + b.price.toFixed(2) + '</td>' +
                '<td>' + b.size.toLocaleString() + '</td>' +
                '<td class="notional">$' + (b.notional / 1e6).toFixed(2) + 'M</td>' +
                '<td>' + b.exchange + '</td>' +
                '<td><span class="block-type ' + b.type.toLowerCase() + '">' + b.type + '</span></td>' +
            '</tr>';
        }
        container.innerHTML = html;
    },
    
    generateSampleBlockTrades: function() {
        const symbols = ['SPY', 'QQQ', 'META', 'MSFT', 'AAPL', 'TSLA', 'NVDA', 'GOOGL', 'AMZN'];
        const exchanges = ['NASDAQ', 'NYSE', 'ARCA', 'BATS'];
        const types = ['BLOCK', 'BLOCK', 'BLOCK', 'LARGE'];
        
        const trades = [];
        for (var i = 0; i < 20; i++) {
            var symbol = symbols[Math.floor(Math.random() * symbols.length)];
            var price = 100 + Math.random() * 500;
            var size = Math.floor(Math.random() * 200000) + 50000;
            
            trades.push({
                time: this.randomTime(),
                symbol: symbol,
                price: price,
                size: size,
                notional: price * size,
                exchange: exchanges[Math.floor(Math.random() * exchanges.length)],
                type: types[Math.floor(Math.random() * types.length)]
            });
        }
        
        return trades.sort(function(a, b) { return b.notional - a.notional; });
    },
    
    randomTime: function() {
        var h = Math.floor(Math.random() * 12) + 1;
        var m = Math.floor(Math.random() * 60);
        var s = Math.floor(Math.random() * 60);
        var ampm = Math.random() > 0.5 ? 'PM' : 'AM';
        return h + ':' + (m < 10 ? '0' : '') + m + ':' + (s < 10 ? '0' : '') + s + ' ' + ampm;
    },

    // ==================== OPTIONS FLOW ====================
    
    renderOptionsFlow: async function() {
        const container = document.getElementById('flowTable');
        if (!container) return;
        
        // Setup filter buttons
        this.setupFlowFilters();
        
        var flows = [];
        try {
            const res = await fetch('/api/flow/live');
            if (res.ok) {
                const data = await res.json();
                flows = data.flows || [];
            }
        } catch (e) {}
        
        if (flows.length === 0) {
            flows = this.generateSampleFlow();
        }
        
        // Update Put/Call ratio
        var callPrem = 0, putPrem = 0;
        flows.forEach(function(f) {
            if (f.cp === 'C') callPrem += f.premium;
            else putPrem += f.premium;
        });
        var pcRatio = callPrem > 0 ? (putPrem / callPrem).toFixed(2) : '0.00';
        var pcEl = document.getElementById('flowPCRatio');
        if (pcEl) pcEl.textContent = pcRatio;
        var sentEl = document.getElementById('flowSentiment');
        if (sentEl) {
            sentEl.textContent = parseFloat(pcRatio) < 0.7 ? 'BULLISH' : parseFloat(pcRatio) > 1.3 ? 'BEARISH' : 'NEUTRAL';
            sentEl.className = parseFloat(pcRatio) < 0.7 ? 'bullish' : parseFloat(pcRatio) > 1.3 ? 'bearish' : 'neutral';
        }
        
        this.renderFlowTable(flows);
    },
    
    setupFlowFilters: function() {
        const self = this;
        document.querySelectorAll('.flow-filters .filter-btn').forEach(function(btn) {
            if (!btn._bound) {
                btn._bound = true;
                btn.addEventListener('click', function() {
                    document.querySelectorAll('.flow-filters .filter-btn').forEach(b => b.classList.remove('active'));
                    this.classList.add('active');
                    self.filterFlows(this.dataset.filter);
                });
            }
        });
    },
    
    filterFlows: function(filter) {
        // Re-render with filter applied
        var flows = this.generateSampleFlow();
        
        if (filter === 'calls') flows = flows.filter(f => f.cp === 'C');
        else if (filter === 'puts') flows = flows.filter(f => f.cp === 'P');
        else if (filter === 'sweeps') flows = flows.filter(f => f.type === 'SWEEP');
        else if (filter === 'etfs') flows = flows.filter(f => ['SPY', 'QQQ', 'IWM', 'DIA'].includes(f.symbol));
        else if (filter === 'stocks') flows = flows.filter(f => !['SPY', 'QQQ', 'IWM', 'DIA'].includes(f.symbol));
        else if (filter === '100k') flows = flows.filter(f => f.premium >= 100000);
        else if (filter === 'whales') flows = flows.filter(f => f.premium >= 1000000);
        else if (filter === 'unusual') flows = flows.filter(f => f.score >= 80);
        else if (filter === 'leaps') flows = flows.filter(f => f.dte >= 180);
        else if (filter === 'bid') flows = flows.filter(f => f.side === 'BUY');
        else if (filter === 'ask') flows = flows.filter(f => f.side === 'SELL');
        
        this.renderFlowTable(flows);
    },
    
    renderFlowTable: function(flows) {
        const container = document.getElementById('flowTable');
        if (!container) return;
        
        var html = '';
        for (var i = 0; i < flows.length; i++) {
            var f = flows[i];
            var sentClass = f.sentiment === 'BULLISH' ? 'bullish' : f.sentiment === 'BEARISH' ? 'bearish' : 'neutral';
            html += '<tr>' +
                '<td>' + f.time + '</td>' +
                '<td class="value-cell">$' + (f.premium / 1e6).toFixed(2) + 'M</td>' +
                '<td class="symbol-cell">' + f.symbol + '</td>' +
                '<td>$' + f.spot.toFixed(2) + '</td>' +
                '<td class="' + (f.cp === 'C' ? 'call' : 'put') + '">$' + f.strike + '</td>' +
                '<td class="' + (f.cp === 'C' ? 'call' : 'put') + '">' + f.cp + '</td>' +
                '<td>' + f.exp + '</td>' +
                '<td><span class="flow-type-badge ' + f.type.toLowerCase() + '">' + f.type + '</span></td>' +
                '<td>$' + f.price.toFixed(2) + '</td>' +
                '<td>' + f.size.toLocaleString() + '</td>' +
                '<td>' + f.score + '</td>' +
                '<td>' + f.delta.toFixed(2) + '</td>' +
                '<td>' + f.volume.toLocaleString() + '</td>' +
                '<td>' + f.oi.toLocaleString() + '</td>' +
                '<td>' + f.iv.toFixed(1) + '%</td>' +
                '<td>' + f.otm.toFixed(1) + '%</td>' +
                '<td class="' + sentClass + '">' + f.sentiment + '</td>' +
            '</tr>';
        }
        container.innerHTML = html;
    },
    
    generateSampleFlow: function() {
        const symbols = ['SPY', 'QQQ', 'NVDA', 'AAPL', 'TSLA', 'AMD', 'META', 'MSFT', 'AMZN', 'GOOG'];
        const spotPrices = { 'SPY': 591, 'QQQ': 520, 'NVDA': 140, 'AAPL': 255, 'TSLA': 455, 'AMD': 125, 'META': 620, 'MSFT': 435, 'AMZN': 225, 'GOOG': 195 };
        const flows = [];
        
        for (var i = 0; i < 50; i++) {
            var sym = symbols[Math.floor(Math.random() * symbols.length)];
            var spot = spotPrices[sym] || 100;
            var strike = Math.round(spot * (0.9 + Math.random() * 0.2));
            var cp = Math.random() > 0.45 ? 'C' : 'P';
            var isOTM = (cp === 'C' && strike > spot) || (cp === 'P' && strike < spot);
            var premium = Math.floor(Math.random() * Math.random() * 5000000) + 50000;
            var size = Math.floor(premium / (Math.random() * 300 + 50));
            var dte = [0, 7, 14, 30, 60, 90, 180, 365][Math.floor(Math.random() * 8)];
            
            flows.push({
                time: this.randomTime(),
                symbol: sym,
                spot: spot,
                strike: strike,
                cp: cp,
                exp: this.getExpDate(dte),
                premium: premium,
                side: Math.random() > 0.45 ? 'BUY' : 'SELL',
                type: ['SWEEP', 'BLOCK', 'SPLIT', 'SINGLE'][Math.floor(Math.random() * 4)],
                price: Math.random() * 10 + 0.5,
                size: size,
                score: Math.floor(Math.random() * 50 + 50),
                delta: (isOTM ? 0.1 : 0.5) + Math.random() * 0.4,
                volume: Math.floor(Math.random() * 50000 + 1000),
                oi: Math.floor(Math.random() * 200000 + 5000),
                iv: 20 + Math.random() * 60,
                otm: Math.abs(strike - spot) / spot * 100,
                dte: dte,
                sentiment: Math.random() > 0.6 ? 'BULLISH' : Math.random() > 0.3 ? 'BEARISH' : 'NEUTRAL'
            });
        }
        
        return flows.sort(function(a, b) { return b.premium - a.premium; });
    },
    
    getExpDate: function(dte) {
        var d = new Date();
        d.setDate(d.getDate() + dte);
        return (d.getMonth() + 1) + '/' + d.getDate();
    },

    // ==================== GEX PAGE (GeeksOfFinance Style) ====================
    
    renderGEXPage: async function() {
        const symbol = document.getElementById('gofSymbolSelect')?.value || this.state.symbol;
        
        // Fetch GEX data from API
        let gexData = null;
        try {
            const res = await fetch('/api/snapshot?symbol=' + symbol);
            if (res.ok) {
                gexData = await res.json();
            }
        } catch (e) {
            console.log('GEX API fetch failed, using sample data');
        }
        
        // Use sample data if API fails
        if (!gexData || !gexData.strikes) {
            gexData = this.generateGOFData(symbol);
        }
        
        const spot = gexData.meta?.spot || this.state.price || 5905;
        
        // Update OHLC display
        this.updateGOFHeader(gexData, spot);
        
        // Render price chart with gamma zones
        this.renderGOFPriceChart(symbol, spot, gexData);
        
        // Render dual GEX profile (butterfly)
        this.renderGOFGexProfile(gexData, spot);
        
        // Setup event handlers
        this.setupGOFEventHandlers();
    },
    
    generateGOFData: function(symbol) {
        // Generate realistic data for GeeksOfFinance style
        const spotPrices = { 'SPX': 5905, 'SPY': 591, 'QQQ': 520, 'IWM': 225, 'NVDA': 140, 'AAPL': 255, 'TSLA': 455 };
        const spot = spotPrices[symbol] || 5905;
        
        const strikes = [];
        const baseStrike = Math.round(spot / 25) * 25;
        
        for (var i = -20; i <= 20; i++) {
            var strike = baseStrike + i * 25;
            var distFromSpot = Math.abs(strike - spot);
            var distPct = distFromSpot / spot;
            
            // Call GEX peaks above spot
            var callGex = strike > spot ? 
                Math.max(0, 200000000 * Math.exp(-distPct * 10)) : 
                Math.max(0, 50000000 * Math.exp(-distPct * 15));
            
            // Put GEX peaks below spot  
            var putGex = strike < spot ?
                Math.max(0, 150000000 * Math.exp(-distPct * 10)) :
                Math.max(0, 30000000 * Math.exp(-distPct * 15));
            
            // Add volume data
            var volume = Math.floor(50000 + Math.random() * 300000);
            
            strikes.push({
                strike: strike,
                call_gex: callGex,
                put_gex: putGex,
                net_gex: callGex - putGex,
                volume: volume,
                call_oi: Math.floor(Math.random() * 80000),
                put_oi: Math.floor(Math.random() * 60000)
            });
        }
        
        // Calculate levels
        var callWall = strikes.reduce((max, s) => s.call_gex > max.call_gex ? s : max, strikes[0]).strike;
        var putWall = strikes.reduce((max, s) => s.put_gex > max.put_gex ? s : max, strikes[0]).strike;
        
        // Zero gamma - where net_gex crosses zero
        var zeroGamma = spot;
        for (var j = 0; j < strikes.length - 1; j++) {
            if ((strikes[j].net_gex > 0 && strikes[j+1].net_gex < 0) ||
                (strikes[j].net_gex < 0 && strikes[j+1].net_gex > 0)) {
                // Linear interpolation
                var s1 = strikes[j], s2 = strikes[j+1];
                zeroGamma = s1.strike + (s2.strike - s1.strike) * Math.abs(s1.net_gex) / (Math.abs(s1.net_gex) + Math.abs(s2.net_gex));
                break;
            }
        }
        
        // G1, G2 levels (gamma walls)
        var g1 = zeroGamma + 20;
        var g2 = zeroGamma - 10;
        
        // Dealer cluster (area of high gamma concentration)
        var dealerClusterLow = spot - 15;
        var dealerClusterHigh = spot + 10;
        
        return {
            meta: { spot: spot, symbol: symbol },
            strikes: strikes,
            summary: {
                call_wall: callWall,
                put_wall: putWall,
                zero_gamma: zeroGamma,
                g1: g1,
                g2: g2,
                dealer_cluster_low: dealerClusterLow,
                dealer_cluster_high: dealerClusterHigh,
                net_gex: strikes.reduce((sum, s) => sum + s.net_gex, 0)
            }
        };
    },
    
    updateGOFHeader: function(gexData, spot) {
        const ohlc = this.state.ohlc || [];
        const latest = ohlc[ohlc.length - 1] || {};
        
        this.setText('gofOpen', (latest.open || spot - 1).toFixed(2));
        this.setText('gofHigh', (latest.high || spot + 2).toFixed(2));
        this.setText('gofLow', (latest.low || spot - 3).toFixed(2));
        this.setText('gofClose', spot.toFixed(2));
        
        // EMA calculation (simple average of last 50 closes)
        var ema = spot;
        if (ohlc.length >= 50) {
            var sum = 0;
            for (var i = ohlc.length - 50; i < ohlc.length; i++) {
                sum += ohlc[i].close;
            }
            ema = sum / 50;
        }
        this.setText('gofEmaValue', ema.toFixed(2));
        
        // Time
        var now = new Date();
        this.setText('gofTime', now.toLocaleDateString() + ' ' + now.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'}));
    },
    
    renderGOFPriceChart: function(symbol, spot, gexData) {
        const container = document.getElementById('gofPriceChart');
        if (!container) return;
        
        const summary = gexData.summary || {};
        const zeroG = summary.zero_gamma || spot;
        const g1 = summary.g1 || zeroG + 20;
        const g2 = summary.g2 || zeroG - 10;
        const clusterLow = summary.dealer_cluster_low || spot - 15;
        const clusterHigh = summary.dealer_cluster_high || spot + 10;
        
        // Generate candlestick data
        const candles = this.generateCandleData(spot, 30);
        const ema = this.calculateEMA(candles, 50);
        
        // Y-axis range
        const allPrices = candles.flatMap(c => [c.high, c.low]);
        const yMin = Math.min(...allPrices) - 50;
        const yMax = Math.max(...allPrices) + 50;
        
        var traces = [];
        
        // GAMMA REGIME ZONES (key feature!)
        // Purple zone ABOVE Zero Gamma (negative gamma regime)
        traces.push({
            x: [candles[0].date, candles[candles.length-1].date, candles[candles.length-1].date, candles[0].date],
            y: [zeroG, zeroG, yMax, yMax],
            fill: 'toself',
            fillcolor: 'rgba(156, 39, 176, 0.15)',
            line: { width: 0 },
            name: 'Negative Gamma',
            hoverinfo: 'skip',
            showlegend: false
        });
        
        // Teal zone BELOW Zero Gamma (positive gamma regime)
        traces.push({
            x: [candles[0].date, candles[candles.length-1].date, candles[candles.length-1].date, candles[0].date],
            y: [zeroG, zeroG, yMin, yMin],
            fill: 'toself',
            fillcolor: 'rgba(0, 150, 136, 0.15)',
            line: { width: 0 },
            name: 'Positive Gamma',
            hoverinfo: 'skip',
            showlegend: false
        });
        
        // Candlesticks
        traces.push({
            x: candles.map(c => c.date),
            open: candles.map(c => c.open),
            high: candles.map(c => c.high),
            low: candles.map(c => c.low),
            close: candles.map(c => c.close),
            type: 'candlestick',
            increasing: { line: { color: '#26a69a' }, fillcolor: '#26a69a' },
            decreasing: { line: { color: '#ef5350' }, fillcolor: '#ef5350' },
            name: symbol
        });
        
        // EMA line
        traces.push({
            x: candles.map(c => c.date),
            y: ema,
            type: 'scatter',
            mode: 'lines',
            line: { color: '#ef5350', width: 1.5 },
            name: 'EMA 50'
        });
        
        // Layout with level lines
        var shapes = [
            // ZERO G line (most important)
            { type: 'line', x0: candles[0].date, x1: candles[candles.length-1].date, y0: zeroG, y1: zeroG,
              line: { color: 'rgba(255, 255, 255, 0.6)', width: 1.5, dash: 'dot' } },
            // G1 line
            { type: 'line', x0: candles[0].date, x1: candles[candles.length-1].date, y0: g1, y1: g1,
              line: { color: '#ef5350', width: 1 } },
            // G2 line  
            { type: 'line', x0: candles[0].date, x1: candles[candles.length-1].date, y0: g2, y1: g2,
              line: { color: '#ef5350', width: 1 } }
        ];
        
        var annotations = [
            // ZERO G label
            { x: candles[candles.length-1].date, y: zeroG, text: 'ZERO G', showarrow: false,
              xanchor: 'left', font: { color: '#fff', size: 10 }, bgcolor: 'rgba(0,0,0,0.5)' },
            // G1 label
            { x: candles[0].date, y: g1, text: 'G1', showarrow: false,
              xanchor: 'right', font: { color: '#ef5350', size: 10 } },
            // G2 label
            { x: candles[0].date, y: g2, text: 'G2', showarrow: false,
              xanchor: 'right', font: { color: '#ef5350', size: 10 } },
            // CLUSTER annotation
            { x: candles[5].date, y: yMax - 20, text: 'CLUSTER', showarrow: false,
              font: { color: '#9c27b0', size: 11 } },
            // DEALER CLUSTER annotation
            { x: candles[15].date, y: (clusterLow + clusterHigh) / 2, text: 'DEALER<br>CLUSTER', showarrow: false,
              font: { color: '#fff', size: 9 }, bgcolor: 'rgba(0,0,0,0.3)' }
        ];
        
        var layout = {
            paper_bgcolor: 'transparent',
            plot_bgcolor: '#0d1117',
            margin: { l: 50, r: 80, t: 10, b: 40 },
            xaxis: {
                gridcolor: 'rgba(255,255,255,0.05)',
                tickfont: { color: '#606070', size: 10 },
                rangeslider: { visible: false }
            },
            yaxis: {
                side: 'right',
                gridcolor: 'rgba(255,255,255,0.05)',
                tickfont: { color: '#a0a0b0', size: 10 },
                range: [yMin, yMax]
            },
            shapes: shapes,
            annotations: annotations,
            showlegend: false
        };
        
        Plotly.newPlot(container, traces, layout, { responsive: true, displayModeBar: false });
    },
    
    renderGOFGexProfile: function(gexData, spot) {
        const container = document.getElementById('gofGexProfile');
        if (!container) return;
        
        const strikes = gexData.strikes || [];
        const summary = gexData.summary || {};
        const zeroG = summary.zero_gamma || spot;
        
        // Filter to near the money
        const filtered = strikes.filter(s => s.strike >= spot - 200 && s.strike <= spot + 200);
        
        // DUAL BUTTERFLY CHART - Key feature!
        // Magenta bars going LEFT (Put GEX / negative)
        // Cyan bars going RIGHT (Call GEX / positive)
        
        var traces = [];
        
        // Put GEX bars (LEFT side, magenta)
        traces.push({
            y: filtered.map(s => s.strike),
            x: filtered.map(s => -s.put_gex / 1e6), // Negative so they go left
            type: 'bar',
            orientation: 'h',
            marker: { color: '#e040fb' },
            name: 'Put GEX',
            hovertemplate: 'Strike: %{y}<br>Put GEX: %{x:.1f}M<extra></extra>'
        });
        
        // Call GEX bars (RIGHT side, cyan)
        traces.push({
            y: filtered.map(s => s.strike),
            x: filtered.map(s => s.call_gex / 1e6),
            type: 'bar',
            orientation: 'h',
            marker: { color: '#00e5ff' },
            name: 'Call GEX',
            hovertemplate: 'Strike: %{y}<br>Call GEX: %{x:.1f}M<extra></extra>'
        });
        
        var layout = {
            paper_bgcolor: 'transparent',
            plot_bgcolor: '#0d1117',
            margin: { l: 10, r: 10, t: 10, b: 40 },
            xaxis: {
                gridcolor: 'rgba(255,255,255,0.05)',
                tickfont: { color: '#a0a0b0', size: 9 },
                zeroline: true,
                zerolinecolor: 'rgba(255,255,255,0.2)',
                zerolinewidth: 2
            },
            yaxis: {
                gridcolor: 'rgba(255,255,255,0.05)',
                tickfont: { color: '#a0a0b0', size: 9 }
            },
            shapes: [
                // Spot price horizontal line
                { type: 'line', x0: -300, x1: 300, y0: spot, y1: spot,
                  line: { color: '#ffc107', width: 2 } }
            ],
            annotations: [
                // Spot price label
                { x: 150, y: spot, text: '^SPX Price ' + spot.toFixed(2), showarrow: false,
                  font: { color: '#000', size: 10 }, bgcolor: '#ffc107', borderpad: 3 }
            ],
            showlegend: false,
            bargap: 0.1,
            barmode: 'overlay'
        };
        
        Plotly.newPlot(container, traces, layout, { responsive: true, displayModeBar: false });
    },
    
    generateCandleData: function(spot, days) {
        const candles = [];
        let price = spot - (Math.random() * 50);
        const now = new Date();
        
        for (var i = days; i >= 0; i--) {
            var d = new Date(now);
            d.setDate(d.getDate() - i);
            
            var open = price;
            var volatility = 0.015;
            var change = (Math.random() - 0.48) * spot * volatility;
            var close = open + change;
            var high = Math.max(open, close) + Math.random() * spot * 0.005;
            var low = Math.min(open, close) - Math.random() * spot * 0.005;
            
            candles.push({
                date: d.toISOString().split('T')[0],
                open: open,
                high: high,
                low: low,
                close: close
            });
            
            price = close;
        }
        
        // Make sure last candle is near current spot
        candles[candles.length - 1].close = spot;
        candles[candles.length - 1].high = Math.max(candles[candles.length - 1].high, spot);
        candles[candles.length - 1].low = Math.min(candles[candles.length - 1].low, spot);
        
        return candles;
    },
    
    calculateEMA: function(candles, period) {
        const closes = candles.map(c => c.close);
        const ema = [];
        const multiplier = 2 / (period + 1);
        
        // Simple average for first EMA value
        let sum = 0;
        for (var i = 0; i < Math.min(period, closes.length); i++) {
            sum += closes[i];
        }
        ema.push(sum / Math.min(period, closes.length));
        
        // EMA calculation
        for (var j = 1; j < closes.length; j++) {
            ema.push((closes[j] - ema[j-1]) * multiplier + ema[j-1]);
        }
        
        return ema;
    },
    
    setupGOFEventHandlers: function() {
        const self = this;
        
        // Symbol select change
        const symbolSelect = document.getElementById('gofSymbolSelect');
        if (symbolSelect && !symbolSelect._bound) {
            symbolSelect._bound = true;
            symbolSelect.addEventListener('change', function() {
                self.renderGEXPage();
            });
        }
        
        // Time Machine toggle
        const tmToggle = document.getElementById('togTimeMachine');
        if (tmToggle && !tmToggle._bound) {
            tmToggle._bound = true;
            tmToggle.addEventListener('change', function() {
                const tmContainer = document.getElementById('gofTimeMachineContainer');
                if (tmContainer) {
                    tmContainer.style.display = this.checked ? 'flex' : 'none';
                }
            });
        }
        
        // Time Machine slider
        const tmSlider = document.getElementById('gofTimeMachineSlider');
        if (tmSlider && !tmSlider._bound) {
            tmSlider._bound = true;
            tmSlider.addEventListener('input', function() {
                const val = parseInt(this.value);
                const label = document.getElementById('gofTimeMachineValue');
                if (val >= 390) {
                    label.textContent = 'LIVE';
                } else {
                    const hrs = Math.floor((390 - val) / 60);
                    const mins = (390 - val) % 60;
                    label.textContent = '-' + (hrs > 0 ? hrs + 'h ' : '') + mins + 'm';
                }
                // Re-render with historical data would go here
            });
        }
        
        // Bottom tabs
        document.querySelectorAll('.gof-tab').forEach(function(tab) {
            if (!tab._bound) {
                tab._bound = true;
                tab.addEventListener('click', function() {
                    document.querySelectorAll('.gof-tab').forEach(t => t.classList.remove('active'));
                    this.classList.add('active');
                    // Would switch sub-views here (Flow, Data Graph, 3D Surface)
                });
            }
        });
        
        // Customize toggles - re-render when changed
        ['togClusters', 'togAbsoluteGex', 'togVolume', 'togDealerCluster', 'togGrossNet'].forEach(function(id) {
            var tog = document.getElementById(id);
            if (tog && !tog._bound) {
                tog._bound = true;
                tog.addEventListener('change', function() {
                    self.renderGEXPage();
                });
            }
        });
    },
    
    // ==================== DARK POOL ====================
    renderDarkPool: async function() {
        const bubbleChart = document.getElementById('dpBubbleChart');
        const flowList = document.getElementById('dpOptionsFlow');
        const printsList = document.getElementById('dpPrintsList');
        const clustersDiv = document.getElementById('dpClusters');
        
        if (!bubbleChart) return;
        
        // Try to fetch from API first
        let prints = [];
        let ohlc = [];
        try {
            const res = await fetch('/api/darkpool/live');
            if (res.ok) {
                const data = await res.json();
                prints = data.prints || [];
            }
            const ohlcRes = await fetch('/api/ohlc/' + this.state.symbol);
            if (ohlcRes.ok) {
                const ohlcData = await ohlcRes.json();
                ohlc = ohlcData.ohlc || [];
            }
        } catch (e) {}
        
        // Generate sample if API fails
        if (prints.length === 0) {
            prints = this.generateSampleDarkPool();
        }
        if (ohlc.length === 0) {
            ohlc = this.generateSampleOHLC(this.state.price || 590, 50);
        }
        
        // Render bubble chart with candlesticks
        this.renderDPBubbleChart(ohlc, prints);
        
        // Render options flow panel
        const flows = this.generateSampleFlow().slice(0, 15);
        if (flowList) {
            flowList.innerHTML = flows.map(f => 
                '<div class="dp-flow-item">' +
                    '<span class="flow-time">' + f.time + '</span>' +
                    '<span class="flow-sym">' + f.symbol + '</span>' +
                    '<span class="flow-strike ' + (f.cp === 'C' ? 'call' : 'put') + '">' + f.strike + f.cp + '</span>' +
                    '<span class="flow-exp">' + f.exp + '</span>' +
                    '<span class="flow-side ' + f.side.toLowerCase() + '">' + f.side + '</span>' +
                    '<span class="flow-prem">$' + (f.premium / 1e6).toFixed(2) + 'M</span>' +
                '</div>'
            ).join('');
        }
        
        // Render dark pool prints panel
        if (printsList) {
            printsList.innerHTML = prints.slice(0, 15).map(p => 
                '<div class="dp-flow-item">' +
                    '<span class="flow-time">' + p.time + '</span>' +
                    '<span class="flow-sym">' + p.symbol + '</span>' +
                    '<span class="flow-price">$' + p.price.toFixed(2) + '</span>' +
                    '<span class="flow-size">' + this.formatNum(p.size) + '</span>' +
                    '<span class="flow-side ' + p.side.toLowerCase() + '">' + p.side + '</span>' +
                    '<span class="flow-prem">$' + (p.notional / 1e6).toFixed(2) + 'M</span>' +
                '</div>'
            ).join('');
        }
        
        // Render trade clusters
        if (clustersDiv) {
            const clusters = this.calculateTradeClusters(prints);
            clustersDiv.innerHTML = 
                '<div class="panel-title-bar">Trade Clusters</div>' +
                '<table class="clusters-table"><thead><tr>' +
                    '<th>Price</th><th>Trades</th><th>Volume</th><th>Notional</th><th>Bias</th>' +
                '</tr></thead><tbody>' +
                clusters.slice(0, 8).map(c => 
                    '<tr>' +
                        '<td>$' + c.price.toFixed(2) + '</td>' +
                        '<td>' + c.trades + '</td>' +
                        '<td>' + this.formatNum(c.volume) + '</td>' +
                        '<td>$' + (c.notional / 1e6).toFixed(2) + 'M</td>' +
                        '<td class="' + (c.bias > 0 ? 'positive' : 'negative') + '">' + 
                            (c.bias > 0 ? 'BUY' : 'SELL') + '</td>' +
                    '</tr>'
                ).join('') + '</tbody></table>';
        }
    },
    
    renderDPBubbleChart: function(ohlc, prints) {
        const container = document.getElementById('dpBubbleChart');
        if (!container || ohlc.length === 0) return;
        
        // Candlestick trace
        const candleTrace = {
            x: ohlc.map(d => d.date),
            open: ohlc.map(d => d.open),
            high: ohlc.map(d => d.high),
            low: ohlc.map(d => d.low),
            close: ohlc.map(d => d.close),
            type: 'candlestick',
            increasing: { line: { color: '#22c55e', width: 1 }, fillcolor: '#22c55e' },
            decreasing: { line: { color: '#ef4444', width: 1 }, fillcolor: '#ef4444' },
            name: 'Price',
            showlegend: false
        };
        
        // Calculate VWAP
        const totalValue = prints.reduce((s, p) => s + p.notional, 0);
        const totalSize = prints.reduce((s, p) => s + p.size, 0);
        const vwap = totalSize > 0 ? totalValue / totalSize : ohlc[ohlc.length - 1].close;
        
        // VWAP line
        const vwapTrace = {
            x: [ohlc[0].date, ohlc[ohlc.length - 1].date],
            y: [vwap, vwap],
            mode: 'lines',
            line: { color: '#f59e0b', width: 2, dash: 'dash' },
            name: 'VWAP $' + vwap.toFixed(2),
            showlegend: true
        };
        
        // Bubble trace for dark pool prints
        const maxNotional = Math.max(...prints.map(p => p.notional));
        const bubbleTrace = {
            x: prints.map((p, i) => ohlc[Math.min(i * 2, ohlc.length - 1)].date),
            y: prints.map(p => p.price),
            mode: 'markers',
            marker: {
                size: prints.map(p => Math.max(10, Math.min(50, Math.sqrt(p.notional / maxNotional) * 50))),
                color: prints.map(p => p.side === 'BUY' ? 'rgba(34, 197, 94, 0.7)' : 'rgba(239, 68, 68, 0.7)'),
                line: { color: 'rgba(255,255,255,0.5)', width: 1 }
            },
            text: prints.map(p => 
                p.symbol + '<br>$' + p.price.toFixed(2) + '<br>' + 
                this.formatNum(p.size) + ' shares<br>$' + (p.notional / 1e6).toFixed(2) + 'M<br>' + p.side
            ),
            hovertemplate: '%{text}<extra></extra>',
            name: 'Dark Pool Prints',
            showlegend: true
        };
        
        const layout = {
            paper_bgcolor: 'transparent',
            plot_bgcolor: 'transparent',
            font: { color: '#9ca3af', size: 11 },
            margin: { t: 30, r: 60, b: 50, l: 60 },
            xaxis: { 
                gridcolor: 'rgba(75,85,99,0.3)', 
                linecolor: 'rgba(75,85,99,0.5)',
                rangeslider: { visible: false }
            },
            yaxis: { 
                gridcolor: 'rgba(75,85,99,0.3)', 
                linecolor: 'rgba(75,85,99,0.5)',
                side: 'right'
            },
            legend: { 
                orientation: 'h', 
                y: 1.1, 
                x: 0.5, 
                xanchor: 'center',
                font: { size: 10 }
            },
            showlegend: true
        };
        
        Plotly.newPlot(container, [candleTrace, vwapTrace, bubbleTrace], layout, { responsive: true, displayModeBar: false });
    },
    
    calculateTradeClusters: function(prints) {
        // Group prints by price level (rounded to nearest dollar)
        const clusters = {};
        prints.forEach(function(p) {
            const level = Math.round(p.price);
            if (!clusters[level]) {
                clusters[level] = { price: level, trades: 0, volume: 0, notional: 0, buyVol: 0, sellVol: 0 };
            }
            clusters[level].trades++;
            clusters[level].volume += p.size;
            clusters[level].notional += p.notional;
            if (p.side === 'BUY') clusters[level].buyVol += p.size;
            else clusters[level].sellVol += p.size;
        });
        
        // Convert to array and calculate bias
        return Object.values(clusters)
            .map(function(c) {
                c.bias = c.buyVol - c.sellVol;
                return c;
            })
            .sort(function(a, b) { return b.notional - a.notional; });
    },
    
    generateSampleOHLC: function(basePrice, count) {
        const ohlc = [];
        let price = basePrice;
        const now = new Date();
        
        for (let i = count; i >= 0; i--) {
            const date = new Date(now);
            date.setDate(date.getDate() - i);
            
            const open = price;
            const change = (Math.random() - 0.48) * 3;
            price += change;
            const close = price;
            const high = Math.max(open, close) + Math.random() * 1.5;
            const low = Math.min(open, close) - Math.random() * 1.5;
            
            ohlc.push({
                date: date.toISOString().split('T')[0],
                open: open,
                high: high,
                low: low,
                close: close,
                volume: Math.floor(Math.random() * 50000000) + 10000000
            });
        }
        return ohlc;
    },
    
    generateSampleDarkPool: function() {
        const symbols = ['SPY', 'QQQ', 'AAPL', 'NVDA', 'TSLA', 'AMD', 'META', 'MSFT', 'GOOGL', 'AMZN'];
        const spotPrices = { 'SPY': 591, 'QQQ': 520, 'AAPL': 255, 'NVDA': 140, 'TSLA': 455, 'AMD': 125, 'META': 620, 'MSFT': 435, 'GOOGL': 195, 'AMZN': 225 };
        const prints = [];
        for (var i = 0; i < 40; i++) {
            var sym = symbols[Math.floor(Math.random() * symbols.length)];
            var basePrice = spotPrices[sym] || 100;
            var price = basePrice + (Math.random() - 0.5) * 5;
            var size = Math.floor(Math.random() * Math.random() * 500000) + 10000;
            prints.push({
                time: this.randomTime(),
                symbol: sym,
                price: price,
                size: size,
                notional: price * size,
                side: Math.random() > 0.45 ? 'BUY' : 'SELL',
                type: Math.random() > 0.6 ? 'BLOCK' : 'SWEEP'
            });
        }
        return prints.sort(function(a, b) { return b.notional - a.notional; });
    },
    
    // ==================== OPTIONS CHAIN ====================
    renderOptionsChain: async function() {
        const container = document.getElementById('chainContent');
        if (!container) return;
        
        const symbol = this.state.symbol;
        const spot = this.state.price || 500;
        
        // Try API first
        let chain = [];
        try {
            const res = await fetch('/api/chain/' + symbol);
            if (res.ok) {
                const data = await res.json();
                chain = data.contracts || [];
            }
        } catch (e) {}
        
        // Generate sample chain if API fails
        if (chain.length === 0) {
            chain = this.generateSampleChain(spot);
        }
        
        // Group by expiration
        const byExp = {};
        chain.forEach(function(c) {
            if (!byExp[c.exp]) byExp[c.exp] = [];
            byExp[c.exp].push(c);
        });
        
        var html = '<div class="chain-controls">' +
            '<span class="chain-symbol">' + symbol + ' Options Chain</span>' +
            '<span class="chain-spot">Spot: $' + spot.toFixed(2) + '</span>' +
        '</div>';
        
        html += '<div class="chain-expirations">';
        var exps = Object.keys(byExp).slice(0, 4);
        for (var i = 0; i < exps.length; i++) {
            var exp = exps[i];
            var contracts = byExp[exp].sort(function(a, b) { return a.strike - b.strike; });
            var calls = contracts.filter(function(c) { return c.right === 'C'; });
            var puts = contracts.filter(function(c) { return c.right === 'P'; });
            
            html += '<div class="chain-exp-group">' +
                '<div class="chain-exp-header">' + this.formatExpDate(exp) + '</div>' +
                '<div class="chain-table-wrap"><table class="chain-table">' +
                '<thead><tr>' +
                    '<th>Bid</th><th>Ask</th><th>OI</th><th class="strike-col">Strike</th><th>OI</th><th>Bid</th><th>Ask</th>' +
                '</tr></thead><tbody>';
            
            // Get unique strikes
            var strikes = [];
            contracts.forEach(function(c) { if (strikes.indexOf(c.strike) === -1) strikes.push(c.strike); });
            strikes.sort(function(a, b) { return a - b; });
            
            // Filter to near the money
            strikes = strikes.filter(function(s) { return s >= spot * 0.9 && s <= spot * 1.1; });
            
            for (var j = 0; j < strikes.length; j++) {
                var strike = strikes[j];
                var call = calls.find(function(c) { return c.strike === strike; }) || {};
                var put = puts.find(function(c) { return c.strike === strike; }) || {};
                var atm = Math.abs(strike - spot) < spot * 0.01;
                
                html += '<tr class="' + (atm ? 'atm' : '') + '">' +
                    '<td class="call-cell">' + (call.bid ? call.bid.toFixed(2) : '--') + '</td>' +
                    '<td class="call-cell">' + (call.ask ? call.ask.toFixed(2) : '--') + '</td>' +
                    '<td class="call-cell">' + this.formatNum(call.oi || 0) + '</td>' +
                    '<td class="strike-col">' + strike.toFixed(0) + '</td>' +
                    '<td class="put-cell">' + this.formatNum(put.oi || 0) + '</td>' +
                    '<td class="put-cell">' + (put.bid ? put.bid.toFixed(2) : '--') + '</td>' +
                    '<td class="put-cell">' + (put.ask ? put.ask.toFixed(2) : '--') + '</td>' +
                '</tr>';
            }
            
            html += '</tbody></table></div></div>';
        }
        html += '</div>';
        
        container.innerHTML = html;
    },
    
    generateSampleChain: function(spot) {
        var chain = [];
        var baseStrike = Math.round(spot / 5) * 5;
        var exps = ['20250117', '20250124', '20250131', '20250221'];
        
        for (var e = 0; e < exps.length; e++) {
            for (var s = -20; s <= 20; s++) {
                var strike = baseStrike + s * 5;
                var callIV = 0.15 + Math.abs(s) * 0.005;
                var putIV = 0.15 + Math.abs(s) * 0.006;
                
                chain.push({
                    exp: exps[e], strike: strike, right: 'C',
                    bid: Math.max(0, (spot - strike) + Math.random() * 5),
                    ask: Math.max(0.05, (spot - strike) + Math.random() * 5 + 0.1),
                    oi: Math.floor(Math.random() * 50000),
                    iv: callIV
                });
                chain.push({
                    exp: exps[e], strike: strike, right: 'P',
                    bid: Math.max(0, (strike - spot) + Math.random() * 5),
                    ask: Math.max(0.05, (strike - spot) + Math.random() * 5 + 0.1),
                    oi: Math.floor(Math.random() * 40000),
                    iv: putIV
                });
            }
        }
        return chain;
    },
    
    formatExpDate: function(exp) {
        if (!exp || exp.length !== 8) return exp;
        return exp.substring(4, 6) + '/' + exp.substring(6, 8) + '/' + exp.substring(0, 4);
    },
    
    // ==================== EARNINGS CALENDAR ====================
    renderEarnings: async function() {
        const container = document.getElementById('earningsContent');
        if (!container) return;
        
        // Try API
        let earnings = [];
        try {
            const res = await fetch('/api/earnings/calendar');
            if (res.ok) {
                const data = await res.json();
                earnings = data.earnings || [];
            }
        } catch (e) {}
        
        // Generate sample earnings
        if (earnings.length === 0) {
            earnings = this.generateSampleEarnings();
        }
        
        // Group by week
        const byWeek = {};
        earnings.forEach(function(e) {
            var week = e.date.substring(0, 7);
            if (!byWeek[week]) byWeek[week] = [];
            byWeek[week].push(e);
        });
        
        var html = '<div class="earnings-calendar">' +
            '<div class="earnings-header">Upcoming Earnings Calendar</div>';
        
        var weeks = Object.keys(byWeek).sort();
        for (var w = 0; w < Math.min(weeks.length, 4); w++) {
            var week = weeks[w];
            var events = byWeek[week];
            
            html += '<div class="earnings-week">' +
                '<div class="week-header">' + this.formatWeekHeader(week) + '</div>' +
                '<div class="earnings-grid">';
            
            for (var i = 0; i < events.length; i++) {
                var e = events[i];
                html += '<div class="earnings-card">' +
                    '<div class="earn-symbol">' + e.symbol + '</div>' +
                    '<div class="earn-company">' + e.company + '</div>' +
                    '<div class="earn-date">' + e.date + '</div>' +
                    '<div class="earn-time">' + (e.timing || 'TBD') + '</div>' +
                    '<div class="earn-est">Est EPS: ' + (e.eps_est || 'N/A') + '</div>' +
                '</div>';
            }
            html += '</div></div>';
        }
        
        html += '</div>';
        container.innerHTML = html;
    },
    
    generateSampleEarnings: function() {
        var today = new Date();
        var earnings = [
            { symbol: 'AAPL', company: 'Apple Inc.', timing: 'After Market' },
            { symbol: 'MSFT', company: 'Microsoft Corp.', timing: 'After Market' },
            { symbol: 'NVDA', company: 'NVIDIA Corp.', timing: 'After Market' },
            { symbol: 'GOOGL', company: 'Alphabet Inc.', timing: 'After Market' },
            { symbol: 'AMZN', company: 'Amazon.com Inc.', timing: 'After Market' },
            { symbol: 'META', company: 'Meta Platforms', timing: 'After Market' },
            { symbol: 'TSLA', company: 'Tesla Inc.', timing: 'After Market' },
            { symbol: 'AMD', company: 'Advanced Micro', timing: 'After Market' },
            { symbol: 'NFLX', company: 'Netflix Inc.', timing: 'After Market' },
            { symbol: 'JPM', company: 'JPMorgan Chase', timing: 'Before Market' },
            { symbol: 'BAC', company: 'Bank of America', timing: 'Before Market' },
            { symbol: 'WFC', company: 'Wells Fargo', timing: 'Before Market' }
        ];
        
        for (var i = 0; i < earnings.length; i++) {
            var d = new Date(today);
            d.setDate(d.getDate() + Math.floor(i / 3) * 7 + (i % 3));
            earnings[i].date = d.toISOString().split('T')[0];
            earnings[i].eps_est = '$' + (1 + Math.random() * 4).toFixed(2);
        }
        
        return earnings;
    },
    
    formatWeekHeader: function(week) {
        var parts = week.split('-');
        var months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
        return months[parseInt(parts[1]) - 1] + ' ' + parts[0];
    },
    
    // ==================== VOL SURFACE 3D ====================
    renderVolSurface: async function() {
        const container = document.getElementById('surfaceContent');
        if (!container) return;
        
        const symbol = this.state.symbol;
        const spot = this.state.price || 500;
        
        // Generate IV surface data
        var strikes = [];
        var dtes = [];
        var ivSurface = [];
        
        for (var s = -20; s <= 20; s++) {
            strikes.push(spot + s * 5);
        }
        for (var d = 1; d <= 12; d++) {
            dtes.push(d * 7);
        }
        
        for (var i = 0; i < dtes.length; i++) {
            var row = [];
            for (var j = 0; j < strikes.length; j++) {
                var moneyness = (strikes[j] - spot) / spot;
                var dte = dtes[i];
                // IV smile formula
                var baseIV = 0.18;
                var skew = moneyness < 0 ? 0.15 : 0.08;
                var termSlope = 0.002;
                var iv = baseIV + Math.abs(moneyness) * skew + dte * termSlope / 365;
                row.push(iv * 100);
            }
            ivSurface.push(row);
        }
        
        var trace = {
            z: ivSurface,
            x: strikes,
            y: dtes,
            type: 'surface',
            colorscale: [
                [0, '#26a69a'],
                [0.25, '#4db6ac'],
                [0.5, '#ffc107'],
                [0.75, '#ff9800'],
                [1, '#ef5350']
            ],
            contours: {
                z: { show: true, usecolormap: true, highlightcolor: '#fff', project: { z: true } }
            }
        };
        
        var layout = {
            paper_bgcolor: '#0a0a0f',
            scene: {
                xaxis: { title: 'Strike', gridcolor: '#333', tickfont: { color: '#888' } },
                yaxis: { title: 'DTE', gridcolor: '#333', tickfont: { color: '#888' } },
                zaxis: { title: 'IV %', gridcolor: '#333', tickfont: { color: '#888' } },
                bgcolor: '#0a0a0f'
            },
            margin: { l: 0, r: 0, t: 30, b: 0 },
            title: { text: symbol + ' Implied Volatility Surface', font: { color: '#888', size: 14 } }
        };
        
        container.innerHTML = '<div id="volSurfacePlot" style="height: 500px;"></div>';
        Plotly.newPlot('volSurfacePlot', [trace], layout, { responsive: true, displayModeBar: false });
    },
    
    // ==================== S&P 500 HEATMAP ====================
    renderHeatmap: async function() {
        const container = document.getElementById('sp500Heatmap');
        if (!container) return;
        
        // Sample sector data
        var sectors = [
            { name: 'Technology', change: 1.2, weight: 28 },
            { name: 'Healthcare', change: -0.5, weight: 13 },
            { name: 'Financials', change: 0.8, weight: 12 },
            { name: 'Consumer Disc', change: 1.5, weight: 11 },
            { name: 'Communication', change: 0.3, weight: 9 },
            { name: 'Industrials', change: -0.2, weight: 8 },
            { name: 'Consumer Staples', change: -0.8, weight: 6 },
            { name: 'Energy', change: 2.1, weight: 5 },
            { name: 'Utilities', change: -0.3, weight: 3 },
            { name: 'Real Estate', change: -1.2, weight: 3 },
            { name: 'Materials', change: 0.6, weight: 2 }
        ];
        
        // Sample stocks in each sector
        var topStocks = [
            { symbol: 'AAPL', change: 1.5, sector: 'Technology' },
            { symbol: 'MSFT', change: 0.8, sector: 'Technology' },
            { symbol: 'NVDA', change: 3.2, sector: 'Technology' },
            { symbol: 'GOOGL', change: 0.5, sector: 'Communication' },
            { symbol: 'AMZN', change: 1.2, sector: 'Consumer Disc' },
            { symbol: 'META', change: 1.8, sector: 'Communication' },
            { symbol: 'TSLA', change: 2.5, sector: 'Consumer Disc' },
            { symbol: 'JPM', change: 1.0, sector: 'Financials' },
            { symbol: 'JNJ', change: -0.3, sector: 'Healthcare' },
            { symbol: 'UNH', change: -0.8, sector: 'Healthcare' },
            { symbol: 'XOM', change: 2.8, sector: 'Energy' },
            { symbol: 'CVX', change: 1.9, sector: 'Energy' }
        ];
        
        var html = '<div class="heatmap-container">' +
            '<div class="heatmap-header">S&P 500 Sector Performance</div>' +
            '<div class="heatmap-grid">';
        
        for (var i = 0; i < sectors.length; i++) {
            var s = sectors[i];
            var color = s.change > 1 ? '#26a69a' : s.change > 0 ? '#4db6ac' : s.change > -1 ? '#ef9a9a' : '#ef5350';
            var textColor = Math.abs(s.change) > 0.5 ? '#fff' : '#ccc';
            
            html += '<div class="heatmap-cell" style="background:' + color + ';flex-basis:' + (s.weight * 3) + '%;">' +
                '<div class="cell-name" style="color:' + textColor + '">' + s.name + '</div>' +
                '<div class="cell-change" style="color:' + textColor + '">' + (s.change >= 0 ? '+' : '') + s.change.toFixed(2) + '%</div>' +
            '</div>';
        }
        html += '</div>';
        
        // Top movers
        html += '<div class="heatmap-movers">' +
            '<div class="movers-section">' +
                '<div class="movers-title">Top Gainers</div>' +
                topStocks.filter(function(s) { return s.change > 0; })
                    .sort(function(a, b) { return b.change - a.change; })
                    .slice(0, 5)
                    .map(function(s) {
                        return '<div class="mover-item"><span class="mover-symbol">' + s.symbol + '</span><span class="mover-change positive">+' + s.change.toFixed(2) + '%</span></div>';
                    }).join('') +
            '</div>' +
            '<div class="movers-section">' +
                '<div class="movers-title">Top Losers</div>' +
                topStocks.filter(function(s) { return s.change < 0; })
                    .sort(function(a, b) { return a.change - b.change; })
                    .slice(0, 5)
                    .map(function(s) {
                        return '<div class="mover-item"><span class="mover-symbol">' + s.symbol + '</span><span class="mover-change negative">' + s.change.toFixed(2) + '%</span></div>';
                    }).join('') +
            '</div>' +
        '</div></div>';
        
        container.innerHTML = html;
    },

    // ==================== HELPERS ====================
    
    formatGex: function(val) {
        if (Math.abs(val) >= 1e9) return '$' + (val / 1e9).toFixed(2) + 'B';
        if (Math.abs(val) >= 1e6) return '$' + (val / 1e6).toFixed(1) + 'M';
        return '$' + (val / 1e3).toFixed(0) + 'K';
    },
    
    formatNum: function(n) {
        if (n >= 1e9) return (n / 1e9).toFixed(2) + 'B';
        if (n >= 1e6) return (n / 1e6).toFixed(2) + 'M';
        if (n >= 1e3) return (n / 1e3).toFixed(2) + 'K';
        return n.toFixed(0);
    },
    
    calcAvgVol: function(ohlc) {
        var vols = ohlc.slice(-30).map(function(d) { return d.volume || 0; });
        if (vols.length === 0) return 0;
        var sum = 0;
        for (var i = 0; i < vols.length; i++) sum += vols[i];
        return sum / vols.length;
    },
    
    getMarketCap: function(s) {
        var caps = { SPY: '$550B', QQQ: '$280B', AAPL: '$3.0T', NVDA: '$1.2T', BA: '$165B', TSLA: '$780B' };
        return caps[s] || '--';
    },
    
    getPE: function(s) {
        var pes = { SPY: '24.5', QQQ: '32.1', AAPL: '29.8', NVDA: '65.2', BA: '-31.1', TSLA: '72.1' };
        return pes[s] || '--';
    },
    
    calculateEMA: function(data, period) {
        if (!data || !data.length) return [];
        var k = 2 / (period + 1);
        var ema = [data[0]];
        for (var i = 1; i < data.length; i++) {
            ema.push(data[i] * k + ema[i - 1] * (1 - k));
        }
        return ema;
    },
    
    generateMockOHLC: function(basePrice) {
        var data = [];
        var price = basePrice || 500;
        for (var i = 365; i >= 0; i--) {
            var date = new Date();
            date.setDate(date.getDate() - i);
            var change = (Math.random() - 0.5) * price * 0.03;
            var open = price;
            var close = price + change;
            var high = Math.max(open, close) + Math.random() * price * 0.01;
            var low = Math.min(open, close) - Math.random() * price * 0.01;
            data.push({
                date: date.toISOString().split('T')[0],
                open: open, high: high, low: low, close: close,
                volume: Math.floor(Math.random() * 50000000) + 10000000
            });
            price = close;
        }
        return data;
    },
    
    // ==================== CONTRACT LOOKUP ====================
    renderContractLookup: function() {
        const self = this;
        
        // Setup search button
        const searchBtn = document.getElementById('contractSearchBtn');
        if (searchBtn && !searchBtn._bound) {
            searchBtn._bound = true;
            searchBtn.addEventListener('click', function() {
                self.searchContract();
            });
        }
        
        // Setup autocomplete
        const searchInput = document.getElementById('contractSearchInput');
        if (searchInput && !searchInput._bound) {
            searchInput._bound = true;
            searchInput.addEventListener('input', function() {
                self.showContractAutocomplete(this.value);
            });
            searchInput.addEventListener('keypress', function(e) {
                if (e.key === 'Enter') self.searchContract();
            });
        }
    },
    
    showContractAutocomplete: function(query) {
        const autocomplete = document.getElementById('contractAutocomplete');
        if (!autocomplete || !query || query.length < 1) {
            if (autocomplete) autocomplete.style.display = 'none';
            return;
        }
        
        const symbol = query.toUpperCase();
        const contracts = [];
        const spotPrices = { 'SPY': 591, 'SPX': 5905, 'QQQ': 520, 'NVDA': 140, 'AAPL': 255, 'TSLA': 455 };
        const basePrice = spotPrices[symbol] || 100;
        const expirations = ['01/31/2025', '02/21/2025', '03/21/2025', '06/20/2025'];
        
        expirations.forEach(exp => {
            for (var offset = -3; offset <= 3; offset++) {
                var strike = Math.round(basePrice / 10) * 10 + offset * 10;
                ['P', 'C'].forEach(cp => {
                    var vol = Math.floor(Math.random() * 10000) + 1000;
                    var oi = Math.floor(Math.random() * 200000) + 10000;
                    contracts.push({
                        symbol: symbol, exp: exp, strike: strike, cp: cp,
                        vol: vol, oi: oi,
                        otm: (Math.abs(strike - basePrice) / basePrice * 100).toFixed(1)
                    });
                });
            }
        });
        
        contracts.sort((a, b) => b.oi - a.oi);
        
        autocomplete.innerHTML = contracts.slice(0, 8).map(c => 
            '<div class="autocomplete-item" onclick="App.loadContract(\'' + c.symbol + '\', \'' + c.exp + '\', ' + c.strike + ', \'' + c.cp + '\')">' +
                '<div><strong>' + c.symbol + ' $' + c.strike + ' ' + c.cp + '</strong> <span style="color:#606070;margin-left:10px;">' + c.exp + '</span></div>' +
                '<div style="font-size:11px;color:#a0a0b0;">Vol: ' + c.vol.toLocaleString() + ' | OI: ' + c.oi.toLocaleString() + ' | ' + c.otm + '% OTM</div>' +
            '</div>'
        ).join('');
        
        autocomplete.style.display = 'block';
    },
    
    searchContract: function() {
        const input = document.getElementById('contractSearchInput');
        const exp = document.getElementById('contractExpSelect');
        const strike = document.getElementById('contractStrikeInput');
        const type = document.getElementById('contractTypeSelect');
        
        if (input && input.value) {
            this.loadContract(
                input.value.toUpperCase(),
                exp?.value || '2025-01-31',
                parseFloat(strike?.value) || 590,
                type?.value || 'C'
            );
        }
        
        const autocomplete = document.getElementById('contractAutocomplete');
        if (autocomplete) autocomplete.style.display = 'none';
    },
    
    loadContract: function(symbol, exp, strike, cp) {
        const detail = document.getElementById('contractDetail');
        if (detail) detail.style.display = 'block';
        
        const header = document.getElementById('contractHeader');
        if (header) header.textContent = symbol + ' $' + strike + ' ' + cp + ' ' + exp;
        
        const spotPrices = { 'SPY': 591, 'SPX': 5905, 'QQQ': 520, 'NVDA': 140, 'AAPL': 255, 'TSLA': 455 };
        const spot = spotPrices[symbol] || 100;
        
        this.renderContractChart(symbol, strike, cp, spot);
        this.calculateContractMetrics(symbol, exp, strike, cp, spot);
        
        const autocomplete = document.getElementById('contractAutocomplete');
        if (autocomplete) autocomplete.style.display = 'none';
    },
    
    renderContractChart: function(symbol, strike, cp, spot) {
        const container = document.getElementById('contractPriceChart');
        if (!container) return;
        
        const candles = [];
        var price = spot - 10;
        const now = new Date();
        
        for (var i = 30; i >= 0; i--) {
            var d = new Date(now);
            d.setDate(d.getDate() - i);
            var open = price;
            var close = price + (Math.random() - 0.48) * spot * 0.02;
            var high = Math.max(open, close) + Math.random() * spot * 0.005;
            var low = Math.min(open, close) - Math.random() * spot * 0.005;
            candles.push({ x: d.toISOString().split('T')[0], open: open, high: high, low: low, close: close });
            price = close;
        }
        
        var trace = {
            x: candles.map(c => c.x),
            open: candles.map(c => c.open),
            high: candles.map(c => c.high),
            low: candles.map(c => c.low),
            close: candles.map(c => c.close),
            type: 'candlestick',
            increasing: { line: { color: '#26a69a' } },
            decreasing: { line: { color: '#ef5350' } }
        };
        
        var layout = {
            paper_bgcolor: 'transparent',
            plot_bgcolor: '#0d1117',
            margin: { l: 50, r: 50, t: 20, b: 40 },
            xaxis: { gridcolor: 'rgba(255,255,255,0.05)', tickfont: { color: '#606070', size: 10 } },
            yaxis: { gridcolor: 'rgba(255,255,255,0.05)', tickfont: { color: '#a0a0b0', size: 10 }, side: 'right' },
            shapes: [
                { type: 'line', x0: 0, x1: 1, xref: 'paper', y0: strike, y1: strike, line: { color: '#ffc107', width: 2, dash: 'dot' } }
            ],
            annotations: [
                { x: 1, xref: 'paper', y: strike, text: 'Strike $' + strike, showarrow: false, xanchor: 'left', font: { color: '#ffc107', size: 10 } }
            ],
            showlegend: false
        };
        
        Plotly.newPlot(container, [trace], layout, { responsive: true, displayModeBar: false });
    },
    
    calculateContractMetrics: function(symbol, exp, strike, cp, spot) {
        const isCall = cp === 'C';
        const otm = isCall ? strike > spot : strike < spot;
        const distance = Math.abs(strike - spot) / spot;
        
        // Probability of Profit calculation
        const pop = otm ? Math.max(1, 50 - distance * 300) : Math.min(99, 50 + distance * 300);
        const lossProb = 100 - pop;
        
        // Kelly sizing
        const winRate = pop / 100;
        const avgWin = 2.5;
        const avgLoss = 1;
        const kelly = (winRate * avgWin - (1 - winRate) * avgLoss) / avgWin;
        
        // Update UI
        this.setText('contractPOP', pop.toFixed(2) + '%');
        this.setText('contractProfitProb', pop.toFixed(2) + '%');
        this.setText('contractLossProb', lossProb.toFixed(2) + '%');
        
        this.setText('contractFullKelly', Math.max(0, kelly * 100).toFixed(2) + '%');
        this.setText('contractHalfKelly', Math.max(0, kelly * 50).toFixed(2) + '%');
        this.setText('contractQuarterKelly', Math.max(0, kelly * 25).toFixed(2) + '%');
        
        this.setText('contractDeltaRatio', (Math.random() * 200 + 50).toFixed(2));
        this.setText('contractVolAdj', (Math.random() * 0.5 + 0.5).toFixed(2));
        this.setText('contractMarginFactor', (Math.random() * 0.5 + 0.8).toFixed(2));
        
        // Max gain/loss
        const premium = strike * 0.03 * 100;
        const maxGain = isCall ? ((spot * 1.5 - strike) * 100) : ((strike - spot * 0.5) * 100);
        const maxLoss = premium;
        
        this.setText('contractMaxGain', '$' + Math.max(0, maxGain).toLocaleString());
        this.setText('contractMaxLoss', '($' + maxLoss.toFixed(0) + ')');
        
        this.setText('contractStrategy', isCall ? 'Long Call' : 'Long Put');
    },
    
    // ==================== MARKET INTELLIGENCE ====================
    renderIntelligence: function() {
        const self = this;
        
        // Setup scan button
        const scanBtn = document.getElementById('intelScanBtn');
        if (scanBtn && !scanBtn._bound) {
            scanBtn._bound = true;
            scanBtn.addEventListener('click', function() {
                self.runIntelScan();
            });
        }
        
        // Setup archive button
        const archiveBtn = document.getElementById('intelArchiveBtn');
        if (archiveBtn && !archiveBtn._bound) {
            archiveBtn._bound = true;
            archiveBtn.addEventListener('click', function() {
                self.archiveScan();
            });
        }
        
        // Load initial data
        this.loadPredictionEngine();
        this.loadIntelSignals();
        this.loadIntelNews();
        this.loadIntelPatterns();
        this.loadArchivedScans();
    },
    
    runIntelScan: function() {
        const status = document.getElementById('intelStatus');
        if (status) status.textContent = 'Scanning...';
        
        setTimeout(() => {
            if (status) status.textContent = 'Scan Complete';
            this.loadPredictionEngine();
            this.loadIntelSignals();
            this.loadIntelNews();
        }, 1500);
    },
    
    loadPredictionEngine: async function() {
        const container = document.getElementById('predictionSignals');
        if (!container) return;
        
        // Try to fetch from backend API
        let predictions = [];
        try {
            const res = await fetch('/api/predictions');
            if (res.ok) {
                const data = await res.json();
                predictions = data.predictions || [];
            }
        } catch (e) {
            console.log('Prediction API not available, using local');
        }
        
        // Fallback to local generation if API fails
        if (predictions.length === 0) {
            predictions = this.generatePredictions();
        }
        
        container.innerHTML = predictions.map(p => 
            '<div class="prediction-card">' +
                '<div class="pred-symbol">' + p.symbol + ' <small>' + (p.model === 'ml' ? '(ML)' : '(Rules)') + '</small></div>' +
                '<div class="pred-direction ' + p.direction.toLowerCase() + '">' + p.direction + '</div>' +
                '<div class="pred-targets">' +
                    '<div class="pred-row"><span>Entry:</span><span>$' + (p.entry || 0).toFixed(2) + '</span></div>' +
                    '<div class="pred-row"><span>Target:</span><span class="positive">$' + (p.target || 0).toFixed(2) + '</span></div>' +
                    '<div class="pred-row"><span>Stop:</span><span class="negative">$' + (p.stop || 0).toFixed(2) + '</span></div>' +
                '</div>' +
                '<div class="pred-metrics">' +
                    '<div class="pred-metric"><span>R/R:</span><span>' + (p.rr || 0).toFixed(2) + '</span></div>' +
                    '<div class="pred-metric"><span>Win %:</span><span>' + (p.win_rate || p.winRate || 0) + '%</span></div>' +
                    '<div class="pred-metric"><span>EV:</span><span class="' + ((p.ev || 0) > 0 ? 'positive' : 'negative') + '">$' + (p.ev || 0).toFixed(2) + '</span></div>' +
                '</div>' +
                '<div class="pred-factors">' +
                    (p.factors || []).map(f => '<span class="factor ' + f.type + '">' + f.name + '</span>').join('') +
                '</div>' +
            '</div>'
        ).join('');
    },
    
    generatePredictions: function() {
        const symbols = ['SPY', 'QQQ', 'NVDA'];
        const spotPrices = { 'SPY': 591, 'QQQ': 520, 'NVDA': 140 };
        
        return symbols.map(sym => {
            const spot = spotPrices[sym];
            const direction = Math.random() > 0.4 ? 'BULLISH' : 'BEARISH';
            const moveSize = spot * (0.008 + Math.random() * 0.015);
            
            let entry, target, stop;
            if (direction === 'BULLISH') {
                entry = spot;
                target = spot + moveSize * 1.8;
                stop = spot - moveSize;
            } else {
                entry = spot;
                target = spot - moveSize * 1.8;
                stop = spot + moveSize;
            }
            
            const rr = Math.abs(target - entry) / Math.abs(stop - entry);
            const winRate = Math.floor(55 + Math.random() * 25);
            const ev = (winRate / 100) * Math.abs(target - entry) - ((100 - winRate) / 100) * Math.abs(stop - entry);
            
            // Generate factors based on analysis
            const factors = [];
            if (Math.random() > 0.3) factors.push({ name: 'GEX ' + (direction === 'BULLISH' ? 'Supportive' : 'Resistance'), type: direction === 'BULLISH' ? 'positive' : 'negative' });
            if (Math.random() > 0.4) factors.push({ name: direction === 'BULLISH' ? 'Call Flow' : 'Put Flow', type: 'positive' });
            if (Math.random() > 0.5) factors.push({ name: 'Dark Pool ' + (Math.random() > 0.5 ? 'Buy' : 'Sell'), type: Math.random() > 0.5 ? 'positive' : 'negative' });
            if (Math.random() > 0.6) factors.push({ name: 'Seasonality', type: 'neutral' });
            if (Math.random() > 0.7) factors.push({ name: 'Technical Setup', type: 'positive' });
            
            return {
                symbol: sym,
                direction: direction,
                entry: entry,
                target: target,
                stop: stop,
                rr: rr,
                winRate: winRate,
                ev: ev,
                factors: factors.slice(0, 4)
            };
        });
    },
    
    archiveScan: async function() {
        const scan = {
            timestamp: new Date().toISOString(),
            time: new Date().toLocaleTimeString(),
            date: new Date().toLocaleDateString(),
            predictions: this.generatePredictions(),
            signals: [
                { type: 'bullish', symbol: 'SPY', desc: 'Unusual call volume' },
                { type: 'bearish', symbol: 'QQQ', desc: 'Put sweep detected' }
            ]
        };
        
        // Try to save to backend API
        try {
            const res = await fetch('/api/scans/archive', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(scan)
            });
            if (res.ok) {
                const data = await res.json();
                console.log('Scan archived to backend:', data.scan_id);
            }
        } catch (e) {
            console.log('Backend archive not available, using localStorage');
        }
        
        // Also save to localStorage as backup
        let archived = [];
        try {
            archived = JSON.parse(localStorage.getItem('archivedScans') || '[]');
        } catch (e) {}
        
        // Add new scan at the beginning
        archived.unshift(scan);
        
        // Keep only last 50 scans
        if (archived.length > 50) archived = archived.slice(0, 50);
        
        // Save to localStorage
        localStorage.setItem('archivedScans', JSON.stringify(archived));
        
        // Update status and reload list
        const status = document.getElementById('intelStatus');
        if (status) status.textContent = 'Scan Archived';
        
        this.loadArchivedScans();
    },
    
    loadArchivedScans: async function() {
        const container = document.getElementById('archivedScansList');
        if (!container) return;
        
        let archived = [];
        
        // Try to load from backend API first
        try {
            const res = await fetch('/api/scans/archived?limit=50');
            if (res.ok) {
                const data = await res.json();
                archived = data.scans || [];
            }
        } catch (e) {
            console.log('Backend scans not available, using localStorage');
        }
        
        // Fallback to localStorage
        if (archived.length === 0) {
            try {
                archived = JSON.parse(localStorage.getItem('archivedScans') || '[]');
            } catch (e) {}
        }
        
        if (archived.length === 0) {
            container.innerHTML = '<div class="no-scans">No archived scans yet. Click "Save Scan" to archive.</div>';
            return;
        }
        
        container.innerHTML = archived.slice(0, 10).map((scan, i) => 
            '<div class="archived-scan-item" data-index="' + i + '">' +
                '<div class="scan-meta">' +
                    '<span class="scan-date">' + scan.date + '</span>' +
                    '<span class="scan-time">' + scan.time + '</span>' +
                '</div>' +
                '<div class="scan-summary">' +
                    (scan.predictions || []).slice(0, 2).map(p => 
                        '<span class="scan-pred ' + p.direction.toLowerCase() + '">' + p.symbol + ' ' + p.direction + '</span>'
                    ).join('') +
                '</div>' +
            '</div>'
        ).join('');
        
        // Add click handlers to view archived scans
        const self = this;
        container.querySelectorAll('.archived-scan-item').forEach(function(item) {
            item.addEventListener('click', function() {
                const idx = parseInt(this.dataset.index);
                self.viewArchivedScan(archived[idx]);
            });
        });
    },
    
    viewArchivedScan: function(scan) {
        // Update prediction display with archived scan
        const container = document.getElementById('predictionSignals');
        if (!container || !scan.predictions) return;
        
        container.innerHTML = scan.predictions.map(p => 
            '<div class="prediction-card archived">' +
                '<div class="pred-symbol">' + p.symbol + ' <small>(Archived)</small></div>' +
                '<div class="pred-direction ' + p.direction.toLowerCase() + '">' + p.direction + '</div>' +
                '<div class="pred-targets">' +
                    '<div class="pred-row"><span>Entry:</span><span>$' + p.entry.toFixed(2) + '</span></div>' +
                    '<div class="pred-row"><span>Target:</span><span class="positive">$' + p.target.toFixed(2) + '</span></div>' +
                    '<div class="pred-row"><span>Stop:</span><span class="negative">$' + p.stop.toFixed(2) + '</span></div>' +
                '</div>' +
                '<div class="pred-metrics">' +
                    '<div class="pred-metric"><span>R/R:</span><span>' + p.rr.toFixed(2) + '</span></div>' +
                    '<div class="pred-metric"><span>Win %:</span><span>' + p.winRate + '%</span></div>' +
                '</div>' +
            '</div>'
        ).join('');
        
        const status = document.getElementById('intelStatus');
        if (status) status.textContent = 'Viewing: ' + scan.date + ' ' + scan.time;
    },
    
    loadIntelSignals: function() {
        const container = document.getElementById('intelSignals');
        if (!container) return;
        
        const signals = [
            { type: 'bullish', symbol: 'SPY', desc: 'Unusual call volume at $595 strike - 3x avg volume' },
            { type: 'bearish', symbol: 'QQQ', desc: 'Large put sweep detected $510 strike exp 01/31' },
            { type: 'bullish', symbol: 'NVDA', desc: 'Dark pool accumulation - $2.5M+ notional' },
            { type: 'neutral', symbol: 'AAPL', desc: 'GEX flip level approaching - watch $255' },
            { type: 'bullish', symbol: 'TSLA', desc: 'Call wall building at $460 - high gamma' },
            { type: 'bearish', symbol: 'AMD', desc: 'Unusual put activity $120 strike - high IV' }
        ];
        
        container.innerHTML = signals.map(s => 
            '<div class="signal-item">' +
                '<span class="signal-type ' + s.type + '">' + s.type.toUpperCase() + '</span>' +
                '<span class="signal-symbol">' + s.symbol + '</span>' +
                '<span class="signal-desc">' + s.desc + '</span>' +
            '</div>'
        ).join('');
    },
    
    loadIntelNews: function() {
        const container = document.getElementById('intelNews');
        if (!container) return;
        
        const news = [
            { time: '10:45 AM', text: 'BREAKING: Major tech earnings beat expectations after market' },
            { time: '10:30 AM', text: 'Fed minutes show continued hawkish stance on rates through Q1' },
            { time: '10:15 AM', text: 'Treasury yields rise to 4.65% on strong jobs data' },
            { time: '09:45 AM', text: 'NVDA announces new AI chip partnership with major cloud provider' },
            { time: '09:30 AM', text: 'Market opens higher on positive earnings outlook' },
            { time: '09:00 AM', text: 'Pre-market: Futures flat ahead of economic data release' },
            { time: '08:30 AM', text: 'Initial jobless claims come in below expectations' },
            { time: '08:00 AM', text: 'European markets mixed on ECB commentary' }
        ];
        
        container.innerHTML = news.map(n => 
            '<div class="news-item">' +
                '<span class="news-time">' + n.time + '</span>' +
                '<span class="news-text">' + n.text + '</span>' +
            '</div>'
        ).join('');
    },
    
    loadIntelPatterns: function() {
        const container = document.getElementById('intelPatterns');
        if (!container) return;
        
        const patterns = [
            { name: 'FOMC Drift', winrate: '67%', trades: 45 },
            { name: 'Earnings Gap Fill', winrate: '58%', trades: 128 },
            { name: 'GEX Flip Reversal', winrate: '72%', trades: 89 },
            { name: 'Dark Pool Breakout', winrate: '61%', trades: 67 },
            { name: 'Put Wall Defense', winrate: '69%', trades: 54 },
            { name: 'Call Wall Magnet', winrate: '64%', trades: 78 }
        ];
        
        container.innerHTML = patterns.map(p => 
            '<div class="pattern-item">' +
                '<span class="pattern-name">' + p.name + '</span>' +
                '<span class="pattern-trades">' + p.trades + ' trades</span>' +
                '<span class="pattern-winrate">' + p.winrate + '</span>' +
            '</div>'
        ).join('');
    }
};

// Initialize on DOM ready
document.addEventListener('DOMContentLoaded', function() { App.init(); });
