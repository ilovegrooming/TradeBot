import yfinance as yf

# Ask user for stock ticker
ticker = input("Enter stock ticker (e.g., AAPL): ")

# Download last 7 days of hourly price data
data = yf.download(ticker, period="7d", interval="1h")

# Get the 'Close' prices
close_prices = data["Close"]

# Get latest price and 3-hour moving average
latest_price = close_prices[-1]
moving_average = close_prices[-3:].mean()

# Print signal based on basic trend
if latest_price > moving_average:
    print("Signal: BUY")
else:
    print("Signal: SELL")
