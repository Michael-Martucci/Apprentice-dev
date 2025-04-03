import requests
import time
import threading
import json
import logging

# Constants
PRICE_UPDATE_INTERVAL = 10800  # CoinGecko updates every 3 hours
ALERT_CHECK_INTERVAL = 1800  # Price/volume alerts every 30 minutes
MOONSHOT_UPDATE_INTERVAL = 300  # Moonshot trading activity every 5 minutes
MAX_API_RETRIES = 5  # Max retries before failing

# Logging
logging.basicConfig(
    filename="crypto_tracker.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# Moonshot API (Bitquery)
BITQUERY_URL = "https://graphql.bitquery.io/"
BITQUERY_API_KEY = "YOUR_API_KEY"  # Replace with your actual Bitquery API key

BITQUERY_QUERY = """
{
  solana {
    trades(
      where: { Trade: {Currency: {Symbol: {is: "PEPE"} } } }
      limit: 10
      orderBy: { block: DESC }
    ) {
      Trade {
        BuyAmount
        SellAmount
        BuyCurrency {
          Symbol
        }
        SellCurrency {
          Symbol
        }
        Block
        Transaction {
          Hash
        }
      }
    }
  }
}
"""

def fetch_json(url, headers=None, retries=MAX_API_RETRIES):
    """Fetches JSON from an API with error handling and retry logic."""
    for attempt in range(retries):
        try:
            response = requests.get(url, headers=headers)

            # Handle rate limits
            if response.status_code == 429:
                logging.warning("Rate limit hit! Retrying in 60 seconds...")
                time.sleep(60)
                continue

            response.raise_for_status()  # Raise an error for bad HTTP responses (4xx, 5xx)
            data = response.json()  # Parse JSON safely

            # Handle errors
            if "error" in data or "message" in data:
                logging.error(f"API Error: {data.get('message', 'Unknown Error')}")
                return None

            return data
        
        except requests.exceptions.RequestException as e:
            logging.error(f"API request error: {e}")

        except json.JSONDecodeError:
            logging.error("Error: API response is not valid JSON. Possible server error.")

        time.sleep(2 ** attempt)  # Backoff
    return None  # If retries fail


def track_price():
    """Tracks CoinGecko price and volume data."""
    coins = ["pepe", "dogecoin", "shiba-inu"] # Example coins
    COINGECKO_URL = f"https://api.coingecko.com/api/v3/simple/price?ids={','.join(coins)}&vs_currencies=usd&include_24hr_vol=true"

    prev_data = {coin: {"price": None, "volume": None} for coin in coins}

    while any(prev_data[coin]["price"] is None for coin in coins):
        data = fetch_json(COINGECKO_URL)

        if data:
            for coin in coins:
                if coin in data:
                    prev_data[coin]["price"] = data[coin].get("usd", 0)
                    prev_data[coin]["volume"] = data[coin].get("usd_24h_vol", 0)
                    logging.info(f"Initial {coin.upper()} price: ${prev_data[coin]['price']}, Volume: {prev_data[coin]['volume']}")
                else:
                    logging.warning(f"'{coin}' not found in CoinGecko API response. May be temporarily unavailable or delisted.")

        time.sleep(10)

    while True:
        time.sleep(PRICE_UPDATE_INTERVAL)

        data = fetch_json(COINGECKO_URL)

        if data:
            for coin in coins:
                if coin in data:
                    price = data[coin].get("usd", 0)
                    volume = data[coin].get("usd_24h_vol", 0)

                    if price is None:
                        logging.warning(f"Missing price data for {coin.upper()}, skipping.")
                        continue  

                    price_change = ((price - prev_data[coin]["price"]) / prev_data[coin]["price"]) * 100
                    if price_change > 10:
                        logging.info(f"ALERT: {coin.upper()} price up {round(price_change, 2)}% in 30 minutes!")

                    volume_change = ((volume - prev_data[coin]["volume"]) / prev_data[coin]["volume"]) * 100
                    if volume_change > 300:
                        logging.info(f"ALERT: {coin.upper()} volume surged {round(volume_change, 2)}% in 24h!")

                    prev_data[coin]["price"], prev_data[coin]["volume"] = price, volume

            time.sleep(ALERT_CHECK_INTERVAL)


def track_moonshot_trades():
    """Tracks Moonshot buy/sell volume."""
    while True:
        headers = {"Content-Type": "application/json", "X-API-KEY": BITQUERY_API_KEY}
        data = fetch_json(BITQUERY_URL, headers=headers)

        if data:
            trades = data.get("data", {}).get("solana", {}).get("trades", [])

            if not trades:
                logging.info("No new trades found for PEPE.")
                time.sleep(MOONSHOT_UPDATE_INTERVAL)
                continue

            buy_volume = sum(trade.get("Trade", {}).get("BuyAmount", 0) for trade in trades)
            sell_volume = sum(trade.get("Trade", {}).get("SellAmount", 0) for trade in trades)

            logging.info(f"Moonshot Trades (PEPE): Buy Volume = {buy_volume}, Sell Volume = {sell_volume}")

            if buy_volume > sell_volume * 2:
                logging.info("ALERT: Buy pressure increasing! Possible pump incoming.")

        time.sleep(MOONSHOT_UPDATE_INTERVAL)


if __name__ == "__main__":
    threading.Thread(target=track_price).start()
    threading.Thread(target=track_moonshot_trades).start()
