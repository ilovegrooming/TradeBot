import sys
import threading
import time
import requests
import pandas as pd
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QLabel, QPushButton,
    QTextEdit, QLineEdit, QHBoxLayout, QSizePolicy
)
from PyQt5.QtCore import Qt, pyqtSignal, QObject
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

API_KEY = "ZZML566OBAZXY0W4"  # <-- Your real API key here!

def get_alpha_vantage_data(symbol):
    url = (
        "https://www.alphavantage.co/query?function=TIME_SERIES_INTRADAY"
        f"&symbol={symbol}&interval=60min&outputsize=compact&apikey={API_KEY}"
    )
    try:
        response = requests.get(url)
        data = response.json()
        if "Time Series (60min)" not in data:
            print(f"API Error or limit reached for {symbol}: {data.get('Note') or data.get('Error Message')}")
            return None
        ts = data["Time Series (60min)"]
        df = pd.DataFrame.from_dict(ts, orient='index')
        df = df.rename(columns={
            '1. open': 'Open',
            '2. high': 'High',
            '3. low': 'Low',
            '4. close': 'Close',
            '5. volume': 'Volume'
        })
        df = df.astype(float)
        df.index = pd.to_datetime(df.index)
        df.sort_index(inplace=True)
        return df
    except Exception as e:
        print(f"Error fetching data for {symbol}: {e}")
        return None

def compute_rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -1 * delta.clip(upper=0)
    avg_gain = gain.rolling(window=period).mean()
    avg_loss = loss.rolling(window=period).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def compute_macd(series):
    exp1 = series.ewm(span=12, adjust=False).mean()
    exp2 = series.ewm(span=26, adjust=False).mean()
    macd = exp1 - exp2
    signal = macd.ewm(span=9, adjust=False).mean()
    return macd, signal

def calculate_indicators(df):
    df['EMA'] = df['Close'].ewm(span=20).mean()
    df['SMA'] = df['Close'].rolling(window=10).mean()
    df['RSI'] = compute_rsi(df['Close'])
    df['MACD'], df['Signal'] = compute_macd(df['Close'])
    return df

def get_signals(df):
    df_clean = df.dropna(subset=['RSI', 'MACD', 'Signal', 'EMA', 'SMA', 'Close'])
    if df_clean.empty:
        return {"RSI":"HOLD", "MACD":"HOLD", "EMA":"HOLD", "SMA":"HOLD"}
    latest = df_clean.iloc[-1]
    signals = {}
    signals["RSI"] = "BUY" if latest['RSI'] < 30 else "SELL" if latest['RSI'] > 70 else "HOLD"
    signals["MACD"] = "BUY" if latest['MACD'] > latest['Signal'] else "SELL" if latest['MACD'] < latest['Signal'] else "HOLD"
    signals["EMA"] = "BUY" if latest['Close'] > latest['EMA'] else "SELL"
    signals["SMA"] = "BUY" if latest['Close'] > latest['SMA'] else "SELL"
    return signals

class WorkerSignals(QObject):
    update_labels = pyqtSignal(dict)
    update_overall = pyqtSignal(str)
    update_scan_results = pyqtSignal(str)
    update_chart = pyqtSignal(pd.DataFrame)
    error = pyqtSignal()

class StockScannerApp(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Alpha Vantage Stock Scanner")
        self.resize(900, 700)
        self.setStyleSheet(dark_stylesheet)

        self.layout = QVBoxLayout()

        # Input for single ticker
        input_layout = QHBoxLayout()
        self.ticker_input = QLineEdit()
        self.ticker_input.setPlaceholderText("Enter ticker symbol, e.g. AAPL")
        self.load_button = QPushButton("Load Stock")
        self.load_button.clicked.connect(self.on_load_stock)
        input_layout.addWidget(self.ticker_input)
        input_layout.addWidget(self.load_button)
        self.layout.addLayout(input_layout)

        # Indicator labels
        self.labels = {}
        for indicator in ["RSI", "MACD", "EMA", "SMA"]:
            lbl = QLabel(f"{indicator}: Loading...")
            lbl.setStyleSheet("font-size: 16px;")
            self.labels[indicator] = lbl
            self.layout.addWidget(lbl)

        # Overall recommendation
        self.recommendation_label = QLabel("Overall Recommendation: Loading...")
        self.recommendation_label.setStyleSheet("font-weight: bold; font-size: 18px;")
        self.layout.addWidget(self.recommendation_label)

        # Scan button and results
        self.scan_button = QPushButton("Scan 10 Big Stocks")
        self.scan_button.clicked.connect(self.start_scan)
        self.layout.addWidget(self.scan_button)

        self.scan_results = QTextEdit()
        self.scan_results.setReadOnly(True)
        self.scan_results.setStyleSheet("background-color: #222; color: #ddd; font-size: 14px;")
        self.layout.addWidget(self.scan_results)

        # Matplotlib Chart embedded
        self.figure = Figure(facecolor="#121212")
        self.canvas = FigureCanvas(self.figure)
        self.canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.layout.addWidget(self.canvas)

        self.setLayout(self.layout)

        # Setup signals
        self.signals = WorkerSignals()
        self.signals.update_labels.connect(self.update_labels_ui)
        self.signals.update_overall.connect(self.update_overall_ui)
        self.signals.update_scan_results.connect(self.update_scan_results_ui)
        self.signals.update_chart.connect(self.update_chart_ui)
        self.signals.error.connect(self.set_labels_error)

        # Load default ticker on start (threaded)
        threading.Thread(target=self.update_stock_data, args=("AAPL",), daemon=True).start()

    def update_labels_ui(self, signals):
        colors = {"BUY": "#00ff00", "SELL": "#ff5555", "HOLD": "#cccccc"}
        for key, label in self.labels.items():
            signal = signals.get(key, "HOLD")
            label.setText(f"{key}: <span style='color:{colors[signal]}; font-weight:bold'>{signal}</span>")

    def update_overall_ui(self, overall):
        colors = {"BUY": "#00ff00", "SELL": "#ff5555", "HOLD": "#cccccc"}
        self.recommendation_label.setText(
            f"Overall Recommendation: <span style='color:{colors[overall]}; font-weight:bold'>{overall}</span>"
        )

    def update_scan_results_ui(self, text):
        self.scan_results.setText(text)

    def set_labels_error(self):
        for label in self.labels.values():
            label.setText("Error loading data")
        self.recommendation_label.setText("Overall Recommendation: Error")

    def update_stock_data(self, symbol):
        df = get_alpha_vantage_data(symbol)
        if df is None or df.empty:
            self.signals.error.emit()
            return

        df = calculate_indicators(df)
        signals = get_signals(df)
        buy_count = sum(1 for v in signals.values() if v == "BUY")

        self.signals.update_labels.emit(signals)

        overall = "BUY" if buy_count >= 3 else "SELL" if buy_count <= 1 else "HOLD"
        self.signals.update_overall.emit(overall)
        self.signals.update_chart.emit(df)

    def on_load_stock(self):
        symbol = self.ticker_input.text().strip().upper()
        if symbol:
            self.scan_results.clear()
            threading.Thread(target=self.update_stock_data, args=(symbol,), daemon=True).start()

    def start_scan(self):
        self.scan_results.setText("Scanning...\n")
        threading.Thread(target=self.scan_market, daemon=True).start()

    def scan_market(self):
        tickers = ['AAPL', 'GOOG', 'MSFT', 'AMZN', 'META', 'TSLA', 'NVDA', 'JPM', 'NFLX', 'BRK-B']
        matches = []
        for symbol in tickers:
            df = get_alpha_vantage_data(symbol)
            if df is None or df.empty:
                continue
            df = calculate_indicators(df)
            signals = get_signals(df)
            buy_count = sum(1 for v in signals.values() if v == "BUY")
            if buy_count >= 3:
                matches.append(f"{symbol}: {buy_count}/4 indicators say BUY")
            time.sleep(15)  # Respect API limits

        result = "\n".join(matches) if matches else "No strong BUY signals found."
        self.signals.update_scan_results.emit(result)

    def update_chart_ui(self, df):
        self.figure.clear()
        ax = self.figure.add_subplot(111)
        ax.set_facecolor("#121212")
        ax.plot(df.index, df['Close'], color="#00ff00", label="Close Price")
        ax.set_title("Close Price (60min Interval)", color="white")
        ax.tick_params(axis='x', colors='white')
        ax.tick_params(axis='y', colors='white')
        ax.spines['bottom'].set_color('white')
        ax.spines['top'].set_color('white')
        ax.spines['left'].set_color('white')
        ax.spines['right'].set_color('white')
        ax.legend(facecolor="#121212", edgecolor="white", labelcolor="white")
        self.canvas.draw()

dark_stylesheet = """
    QWidget {
        background-color: #121212;
        color: #ddd;
        font-family: "Segoe UI", Tahoma, Geneva, Verdana, sans-serif;
    }
    QLineEdit, QTextEdit {
        background-color: #222;
        color: #ddd;
        border: 1px solid #333;
        padding: 4px;
        border-radius: 4px;
    }
    QPushButton {
        background-color: #333;
        color: #ddd;
        border-radius: 6px;
        padding: 6px;
        font-weight: bold;
        font-size: 14px;
    }
    QPushButton:hover {
        background-color: #555;
    }
"""

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = StockScannerApp()
    window.show()
    sys.exit(app.exec_())

