from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import logging
from collections import deque
import talib

app = Flask(__name__)
CORS(app, origins=["https://www.arsolx.ir"], supports_credentials=True)

# ==================== پروکسی ====================
PROXY = {
    'http': 'http://39zmquxEEQP25hgeDMdSYfef8W1_5UczDcrnDJnAvuaVFUuCm:@proxy.packetstream.io:31113',
    'https': 'http://39zmquxEEQP25hgeDMdSYfef8W1_5UczDcrnDJnAvuaVFUuCm:@proxy.packetstream.io:31113'
}

# ==================== تنظیمات پیشرفته ====================
BINANCE_FUTURES_URL = "https://fapi.binance.com/fapi/v1"
TIMEOUT = 10
MAX_RETRIES = 3

# ==================== کلاس تحلیلگر حرفه‌ای ====================
class ProfessionalAnalyzer:
    def __init__(self, symbol, timeframe, limit=200):
        self.symbol = symbol.upper()
        self.timeframe = timeframe
        self.limit = max(limit, 200)
        self.data = None
        self.indicators = {}
        self.patterns = []
        self.divergences = []
        self.signals = []
        
    def fetch_data(self):
        """دریافت داده با پروکسی"""
        for attempt in range(MAX_RETRIES):
            try:
                url = f"{BINANCE_FUTURES_URL}/klines"
                params = {
                    "symbol": self.symbol,
                    "interval": self.timeframe,
                    "limit": self.limit
                }
                response = requests.get(url, params=params, timeout=TIMEOUT, proxies=PROXY)
                if response.status_code == 200:
                    data = response.json()
                    df = pd.DataFrame(data, columns=[
                        'timestamp', 'open', 'high', 'low', 'close', 'volume',
                        'close_time', 'quote_asset_volume', 'number_of_trades',
                        'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'
                    ])
                    
                    for col in ['open', 'high', 'low', 'close', 'volume']:
                        df[col] = pd.to_numeric(df[col])
                    
                    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                    self.data = df
                    
                    self.fetch_open_interest()
                    return True
                    
            except Exception as e:
                logging.warning(f"Attempt {attempt+1} failed: {e}")
                
                # Fallback به کوکوین بدون پروکسی
                try:
                    ku_symbol = self.symbol.replace("USDT", "-USDT")
                    tf_map = {"1m":"1min","5m":"5min","15m":"15min","30m":"30min","1h":"1hour","4h":"4hour","1d":"1day","1w":"1week"}
                    tf = tf_map.get(self.timeframe, "4hour")
                    url = f"https://api.kucoin.com/api/v1/market/candles?symbol={ku_symbol}&type={tf}"
                    response = requests.get(url, timeout=TIMEOUT)
                    if response.status_code == 200:
                        data = response.json()
                        if data.get("code") == "200000":
                            candles = []
                            for c in data["data"][:self.limit]:
                                candles.append([c[0], c[1], c[3], c[4], c[2], c[5], 0, 0, 0, 0, 0, 0])
                            df = pd.DataFrame(candles, columns=[
                                'timestamp', 'open', 'high', 'low', 'close', 'volume',
                                'close_time', 'quote_asset_volume', 'number_of_trades',
                                'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'
                            ])
                            for col in ['open', 'high', 'low', 'close', 'volume']:
                                df[col] = pd.to_numeric(df[col])
                            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                            self.data = df
                            return True
                except:
                    continue
        
        return False
    
    def fetch_open_interest(self):
        try:
            url = f"{BINANCE_FUTURES_URL}/openInterest"
            params = {"symbol": self.symbol}
            response = requests.get(url, params=params, timeout=TIMEOUT, proxies=PROXY)
            if response.status_code == 200:
                data = response.json()
                self.indicators['open_interest'] = float(data['openInterest'])
            else:
                self.indicators['open_interest'] = None
        except:
            self.indicators['open_interest'] = None

    def calculate_all_indicators(self):
        """محاسبه تمام اندیکاتورهای تکنیکال"""
        close = self.data['close'].values
        high = self.data['high'].values
        low = self.data['low'].values
        volume = self.data['volume'].values
        
        # میانگین‌های متحرک
        self.indicators['ma_20'] = talib.SMA(close, timeperiod=20)[-1]
        self.indicators['ma_50'] = talib.SMA(close, timeperiod=50)[-1]
        self.indicators['ma_200'] = talib.SMA(close, timeperiod=200)[-1] if len(close) >= 200 else None
        self.indicators['ema_12'] = talib.EMA(close, timeperiod=12)[-1]
        self.indicators['ema_26'] = talib.EMA(close, timeperiod=26)[-1]
        
        # RSI با سه بازه مختلف
        self.indicators['rsi_14'] = talib.RSI(close, timeperiod=14)[-1]
        self.indicators['rsi_21'] = talib.RSI(close, timeperiod=21)[-1]
        self.indicators['rsi_28'] = talib.RSI(close, timeperiod=28)[-1]
        
        # MACD
        macd, macd_signal, macd_hist = talib.MACD(close, fastperiod=12, slowperiod=26, signalperiod=9)
        self.indicators['macd'] = macd[-1]
        self.indicators['macd_signal'] = macd_signal[-1]
        self.indicators['macd_histogram'] = macd_hist[-1]
        
        # باندهای بولینگر
        upper, middle, lower = talib.BBANDS(close, timeperiod=20, nbdevup=2, nbdevdn=2)
        self.indicators['bb_upper'] = upper[-1]
        self.indicators['bb_middle'] = middle[-1]
        self.indicators['bb_lower'] = lower[-1]
        self.indicators['bb_width'] = (upper[-1] - lower[-1]) / middle[-1]
        self.indicators['bb_position'] = (close[-1] - lower[-1]) / (upper[-1] - lower[-1])
        
        # ATR (نوسان)
        self.indicators['atr_14'] = talib.ATR(high, low, close, timeperiod=14)[-1]
        self.indicators['atr_percent'] = (self.indicators['atr_14'] / close[-1]) * 100
        
        # ADX (قدرت روند)
        self.indicators['adx_14'] = talib.ADX(high, low, close, timeperiod=14)[-1]
        self.indicators['plus_di'] = talib.PLUS_DI(high, low, close, timeperiod=14)[-1]
        self.indicators['minus_di'] = talib.MINUS_DI(high, low, close, timeperiod=14)[-1]
        
        # OBV (حجم)
        self.indicators['obv'] = talib.OBV(close, volume)[-1]
        obv_ma = talib.SMA(talib.OBV(close, volume), timeperiod=20)
        self.indicators['obv_trend'] = 'صعودی' if self.indicators['obv'] > obv_ma[-1] else 'نزولی'
        
        # استوکاستیک
        slowk, slowd = talib.STOCH(high, low, close, fastk_period=14, slowk_period=3, slowk_matype=0, slowd_period=3, slowd_matype=0)
        self.indicators['stoch_k'] = slowk[-1]
        self.indicators['stoch_d'] = slowd[-1]
        
        # حجم
        self.indicators['volume_avg'] = talib.SMA(volume, timeperiod=20)[-1]
        self.indicators['volume_ratio'] = volume[-1] / self.indicators['volume_avg'] if self.indicators['volume_avg'] > 0 else 1
        self.indicators['volume_trend'] = 'افزایشی' if volume[-1] > volume[-5:].mean() else 'کاهشی'
    
    def detect_candlestick_patterns(self):
        """تشخیص الگوهای کندلی"""
        open_prices = self.data['open'].values
        high = self.data['high'].values
        low = self.data['low'].values
        close = self.data['close'].values
        
        patterns = {
            'doji': talib.CDLDOJI(open_prices, high, low, close)[-1],
            'hammer': talib.CDLHAMMER(open_prices, high, low, close)[-1],
            'engulfing': talib.CDLENGULFING(open_prices, high, low, close)[-1],
            'morning_star': talib.CDLMORNINGSTAR(open_prices, high, low, close, penetration=0.3)[-1],
            'evening_star': talib.CDLEVENINGSTAR(open_prices, high, low, close, penetration=0.3)[-1],
            'shooting_star': talib.CDLSHOOTINGSTAR(open_prices, high, low, close)[-1],
            'harami': talib.CDLHARAMI(open_prices, high, low, close)[-1],
            'piercing': talib.CDLPIERCING(open_prices, high, low, close)[-1],
            'dark_cloud': talib.CDLDARKCLOUDCOVER(open_prices, high, low, close, penetration=0.5)[-1],
            'three_white_soldiers': talib.CDL3WHITESOLDIERS(open_prices, high, low, close)[-1],
            'three_black_crows': talib.CDL3BLACKCROWS(open_prices, high, low, close)[-1]
        }
        
        self.patterns = [name for name, value in patterns.items() if value != 0]
    
    def detect_divergences(self):
        """تشخیص واگرایی‌ها"""
        close = self.data['close'].values
        rsi = talib.RSI(close, timeperiod=14)
        macd, _, _ = talib.MACD(close, fastperiod=12, slowperiod=26, signalperiod=9)
        
        # بررسی 10 کندل آخر
        last_10_close = close[-10:]
        last_10_rsi = rsi[-10:]
        last_10_macd = macd[-10:]
        
        # واگرایی صعودی (قیمت کف پایین‌تر، RSI کف بالاتر)
        if (min(last_10_close[-5:]) < min(last_10_close[-10:-5]) and 
            min(last_10_rsi[-5:]) > min(last_10_rsi[-10:-5])):
            self.divergences.append('bullish_rsi_divergence')
        
        # واگرایی نزولی (قیمت سقف بالاتر، RSI سقف پایین‌تر)
        if (max(last_10_close[-5:]) > max(last_10_close[-10:-5]) and 
            max(last_10_rsi[-5:]) < max(last_10_rsi[-10:-5])):
            self.divergences.append('bearish_rsi_divergence')
        
        # واگرایی مخفی صعودی
        if (min(last_10_close[-5:]) > min(last_10_close[-10:-5]) and 
            min(last_10_rsi[-5:]) < min(last_10_rsi[-10:-5])):
            self.divergences.append('hidden_bullish_divergence')
        
        # واگرایی مخفی نزولی
        if (max(last_10_close[-5:]) < max(last_10_close[-10:-5]) and 
            max(last_10_rsi[-5:]) > max(last_10_rsi[-10:-5])):
            self.divergences.append('hidden_bearish_divergence')
    
    def detect_trend(self):
        """تشخیص روند با ۷ حالت مختلف"""
        close = self.data['close'].values[-20:]
        high = self.data['high'].values[-20:]
        low = self.data['low'].values[-5:]
        
        # محاسبه شیب
        slope = (close[-1] - close[0]) / close[0] * 100
        
        # تشخیص ساختار
        higher_highs = all(high[i] < high[i+1] for i in range(len(high)-1))
        lower_lows = all(low[i] > low[i+1] for i in range(len(low)-1))
        
        # قدرت روند با ADX
        adx = self.indicators['adx_14']
        
        # موقعیت قیمت نسبت به میانگین‌ها
        price_vs_ma20 = close[-1] - self.indicators['ma_20']
        price_vs_ma50 = close[-1] - self.indicators['ma_50']
        
        # تشخیص حالت روند
        if higher_highs and slope > 2 and adx > 25:
            trend = 'صعودی قوی'
            strength = 85
        elif higher_highs and slope > 0:
            trend = 'صعودی'
            strength = 70
        elif slope > 0 and adx < 25:
            trend = 'صعودی ضعیف'
            strength = 55
        elif abs(slope) < 1 and adx < 20:
            trend = 'خنثی'
            strength = 40
        elif lower_lows and slope < -2 and adx > 25:
            trend = 'نزولی قوی'
            strength = 85
        elif lower_lows and slope < 0:
            trend = 'نزولی'
            strength = 70
        elif slope < 0 and adx < 25:
            trend = 'نزولی ضعیف'
            strength = 55
        else:
            trend = 'خنثی'
            strength = 50
        
        return trend, strength
    
    def detect_market_phase(self):
        """تشخیص فاز بازار (Accumulation/Distribution/Markup/Markdown)"""
        close = self.data['close'].values
        volume = self.data['volume'].values
        high = self.data['high'].values
        low = self.data['low'].values
        
        # تشخیص ساختار
        recent_highs = high[-10:]
        recent_lows = low[-10:]
        
        if max(recent_highs[-5:]) > max(recent_highs[-10:-5]) and min(recent_lows[-5:]) > min(recent_lows[-10:-5]):
            structure = "HH/HL (صعودی)"
        elif max(recent_highs[-5:]) < max(recent_highs[-10:-5]) and min(recent_lows[-5:]) < min(recent_lows[-10:-5]):
            structure = "LH/LL (نزولی)"
        else:
            structure = "رنج"
        
        # تشخیص فاز
        atr = self.indicators['atr_14']
        volume_ratio = self.indicators['volume_ratio']
        avg_volume = np.mean(volume[-20:])
        recent_volume = volume[-1]
        
        if structure == "HH/HL (صعودی)":
            if recent_volume > avg_volume * 1.2 and self.indicators['adx_14'] > 25:
                phase = "markup"
                phase_prob = 85
            else:
                phase = "markup"
                phase_prob = 70
        elif structure == "LH/LL (نزولی)":
            if recent_volume > avg_volume * 1.2 and self.indicators['adx_14'] > 25:
                phase = "markdown"
                phase_prob = 85
            else:
                phase = "markdown"
                phase_prob = 70
        else:
            if atr < np.mean(high - low) * 0.3:
                if recent_volume < avg_volume * 0.8:
                    phase = "accumulation"
                    phase_prob = 75
                else:
                    phase = "distribution"
                    phase_prob = 75
            else:
                if recent_volume > avg_volume:
                    phase = "distribution"
                    phase_prob = 65
                else:
                    phase = "accumulation"
                    phase_prob = 60
        
        return phase, phase_prob, structure
    
    def generate_signals(self, trend, phase):
        """تولید سیگنال‌های ترکیبی"""
        signals = []
        
        # سیگنال بر اساس روند و فاز
        if trend in ['صعودی قوی', 'صعودی'] and phase == 'markup':
            signals.append('🟢 خرید قوی - همسویی روند و فاز')
        elif trend in ['نزولی قوی', 'نزولی'] and phase == 'markdown':
            signals.append('🔴 فروش قوی - همسویی روند و فاز')
        elif trend == 'صعودی ضعیف' and phase == 'accumulation':
            signals.append('🟡 آماده خرید - منطقه انباشت')
        elif trend == 'نزولی ضعیف' and phase == 'distribution':
            signals.append('🟠 آماده فروش - منطقه توزیع')
        
        # سیگنال بر اساس واگرایی
        for div in self.divergences:
            if 'bullish' in div:
                signals.append('🟢 واگرایی صعودی - احتمال برگشت')
            elif 'bearish' in div:
                signals.append('🔴 واگرایی نزولی - احتمال اصلاح')
        
        # سیگنال بر اساس الگوهای کندلی
        for pattern in self.patterns:
            if pattern in ['hammer', 'morning_star', 'three_white_soldiers']:
                signals.append(f'🟢 الگوی {pattern} - صعودی')
            elif pattern in ['shooting_star', 'evening_star', 'three_black_crows']:
                signals.append(f'🔴 الگوی {pattern} - نزولی')
        
        # سیگنال بر اساس اندیکاتورها
        if self.indicators['rsi_14'] < 30:
            signals.append('🟢 اشباع فروش - احتمال خرید')
        elif self.indicators['rsi_14'] > 70:
            signals.append('🔴 اشباع خرید - احتمال فروش')
        
        if self.indicators['macd_histogram'] > 0 and self.indicators['macd'] > self.indicators['macd_signal']:
            signals.append('🟢 MACD مثبت - momentum صعودی')
        elif self.indicators['macd_histogram'] < 0 and self.indicators['macd'] < self.indicators['macd_signal']:
            signals.append('🔴 MACD منفی - momentum نزولی')
        
        return signals
    
    def get_support_resistance(self):
        """محاسبه سطوح حمایت و مقاومت داینامیک"""
        close = self.data['close'].values
        high = self.data['high'].values
        low = self.data['low'].values
        
        # سطوح کلیدی
        pivot = (high[-1] + low[-1] + close[-1]) / 3
        r1 = 2 * pivot - low[-1]
        s1 = 2 * pivot - high[-1]
        r2 = pivot + (high[-1] - low[-1])
        s2 = pivot - (high[-1] - low[-1])
        
        return {
            'pivot': round(pivot, 2),
            'r1': round(r1, 2),
            'r2': round(r2, 2),
            's1': round(s1, 2),
            's2': round(s2, 2)
        }
    
    def get_analysis(self):
        """دریافت تحلیل کامل"""
        if not self.fetch_data():
            return {"error": "خطا در دریافت داده"}
        
        self.calculate_all_indicators()
        self.detect_candlestick_patterns()
        self.detect_divergences()
        trend, trend_strength = self.detect_trend()
        phase, phase_prob, structure = self.detect_market_phase()
        signals = self.generate_signals(trend, phase)
        sr_levels = self.get_support_resistance()
        
        # رأی‌گیری نهایی
        votes = {
            'trend': 1 if trend in ['صعودی', 'صعودی قوی'] else -1 if trend in ['نزولی', 'نزولی قوی'] else 0,
            'rsi': 1 if self.indicators['rsi_14'] < 30 else -1 if self.indicators['rsi_14'] > 70 else 0,
            'macd': 1 if self.indicators['macd_histogram'] > 0 else -1,
            'volume': 1 if self.indicators['volume_ratio'] > 1.2 else -1 if self.indicators['volume_ratio'] < 0.8 else 0
        }
        
        total_score = sum(votes.values()) / len(votes)
        
        result = {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "last_price": f"{self.data['close'].iloc[-1]:,.2f}",
            "trend": {
                "direction": trend,
                "strength": trend_strength,
                "adx": round(self.indicators['adx_14'], 2)
            },
            "market_phase": {
                "phase": phase,
                "probability": phase_prob,
                "structure": structure
            },
            "indicators": {
                "rsi": {
                    "rsi_14": round(self.indicators['rsi_14'], 2),
                    "rsi_21": round(self.indicators['rsi_21'], 2),
                    "rsi_28": round(self.indicators['rsi_28'], 2),
                    "status": "اشباع خرید" if self.indicators['rsi_14'] > 70 else "اشباع فروش" if self.indicators['rsi_14'] < 30 else "خنثی"
                },
                "macd": {
                    "macd": round(self.indicators['macd'], 2),
                    "signal": round(self.indicators['macd_signal'], 2),
                    "histogram": round(self.indicators['macd_histogram'], 2),
                    "status": "مثبت" if self.indicators['macd_histogram'] > 0 else "منفی"
                },
                "moving_averages": {
                    "ma_20": round(self.indicators['ma_20'], 2),
                    "ma_50": round(self.indicators['ma_50'], 2),
                    "ma_200": round(self.indicators['ma_200'], 2) if self.indicators['ma_200'] else None,
                    "position": "بالای MA20" if self.data['close'].iloc[-1] > self.indicators['ma_20'] else "پایین MA20"
                },
                "bollinger": {
                    "upper": round(self.indicators['bb_upper'], 2),
                    "middle": round(self.indicators['bb_middle'], 2),
                    "lower": round(self.indicators['bb_lower'], 2),
                    "width": round(self.indicators['bb_width'] * 100, 2),
                    "position": round(self.indicators['bb_position'] * 100, 2)
                },
                "volatility": {
                    "atr": round(self.indicators['atr_14'], 2),
                    "atr_percent": round(self.indicators['atr_percent'], 2)
                },
                "volume": {
                    "current": f"{self.data['volume'].iloc[-1]:,.0f}",
                    "average": f"{self.indicators['volume_avg']:,.0f}",
                    "ratio": round(self.indicators['volume_ratio'], 2),
                    "trend": self.indicators['volume_trend']
                },
                "stochastic": {
                    "k": round(self.indicators['stoch_k'], 2),
                    "d": round(self.indicators['stoch_d'], 2),
                    "status": "اشباع خرید" if self.indicators['stoch_k'] > 80 else "اشباع فروش" if self.indicators['stoch_k'] < 20 else "خنثی"
                },
                "obv": {
                    "value": f"{self.indicators['obv']:,.0f}",
                    "trend": self.indicators['obv_trend']
                },
                "open_interest": f"{self.indicators.get('open_interest', 0)/1000000:.2f}M USDT" if self.indicators.get('open_interest') else "نامشخص"
            },
            "patterns": self.patterns,
            "divergences": self.divergences,
            "support_resistance": sr_levels,
            "votes": votes,
            "total_score": round(total_score, 2),
            "signals": signals,
            "recommendation": self.generate_final_recommendation(trend, phase, signals, total_score),
            "timestamp": datetime.now().isoformat()
        }
        
        return result
    
    def generate_final_recommendation(self, trend, phase, signals, score):
        """تولید توصیه نهایی"""
        if score > 0.5 and trend in ['صعودی', 'صعودی قوی'] and phase == 'markup':
            return "✅ خرید قوی - هم‌جهت با روند و فاز بازار"
        elif score < -0.5 and trend in ['نزولی', 'نزولی قوی'] and phase == 'markdown':
            return "✅ فروش قوی - هم‌جهت با روند و فاز بازار"
        elif score > 0.3 and phase == 'accumulation':
            return "🟡 منطقه انباشت - آماده خرید در شکست مقاومت"
        elif score < -0.3 and phase == 'distribution':
            return "🟠 منطقه توزیع - آماده فروش در شکست حمایت"
        elif abs(score) < 0.2:
            return "⏳ بدون روند واضح - منتظر سیگنال قوی‌تر"
        else:
            return "⚪ موقعیت نامشخص - احتیاط در معامله"

# ==================== اندپوینت اصلی ====================
@app.route('/analyze', methods=['POST', 'OPTIONS'])
def analyze():
    if request.method == 'OPTIONS':
        return '', 200
    
    try:
        data = request.json
        symbol = data.get('symbol', 'BTCUSDT')
        timeframe = data.get('timeframe', '4h')
        limit = data.get('limit', 200)
        
        analyzer = ProfessionalAnalyzer(symbol, timeframe, limit)
        result = analyzer.get_analysis()
        
        return jsonify(result)
        
    except Exception as e:
        logging.error(f"خطا: {str(e)}")
        return jsonify({"error": str(e)}), 500

# ==================== اجرای سرور ====================
if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)

    app.run(host='0.0.0.0', port=5000, debug=True)


