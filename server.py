from flask import Flask, jsonify, request
import requests
from flask_cors import CORS
from datetime import datetime, timedelta
from pycoingecko import CoinGeckoAPI
import yfinance as yf
import pandas as pd
import numpy as np  # noqa: F401
import csv
import math

app = Flask(__name__)
CORS(app)
cg = CoinGeckoAPI()
cache_timeout = timedelta(minutes=1)


# Cachés de datos
crypto_cache = {}
stocks_cache = {}
forex_cache = {}

# Variables globales
crypto_symbols_map = {}  # Mapa para nombres y símbolos de criptomonedas
crypto_ids = {}  # Mapa de IDs y simbolos de criptomonedas
stocks_symbols_map = {}  # Mapa para nombres y símbolos de acciones
forex_symbols_map = {}  # Mapa para nombres y símbolos de pares de divisas
all_forex_symbols = []  # Lista solo de símbolos de divisas
all_stock_symbols = []  # Lista solo de símbolos de acciones

# Funciones auxiliares


# Comprueba si el rango de índices está en la caché y si los datos están actualizados
def __is_cache_up_to_date(cache, startIndex):
    return (
        startIndex in cache
        and (datetime.now() - cache[startIndex]["timestamp"]) <= cache_timeout
    )


def get_coin_id(symbol):
    return crypto_ids.get(symbol.upper())


# ---------------------------------------------------------------------------


# Funciones de inicialización de datos


def initialize_crypto_symbols(limit=250):
    global crypto_symbols_map, crypto_ids
    try:
        coins_list = cg.get_coins_markets(
            vs_currency="usd", order="market_cap_desc", per_page=limit, page=1
        )
        for coin in coins_list:
            symbol = coin.get("symbol", "").upper()
            name = coin.get("name", "")
            coin_id = coin.get("id", "")
            crypto_symbols_map[symbol] = name
            crypto_ids[symbol] = coin_id
    except Exception as e:
        print(f"Error al inicializar los símbolos de criptomonedas: {e}")


def initialize_stock_symbols():
    global stocks_symbols_map, all_stock_symbols
    try:
        with open("data/stocks.csv", newline="", encoding="utf-8") as csvfile:
            reader = csv.DictReader(csvfile, delimiter=";")
            for row in reader:
                symbol = row["Symbol"]
                name = row["Name"]
                stocks_symbols_map[symbol] = name
                all_stock_symbols.append(symbol)
    except Exception as e:
        print(f"Error al inicializar los símbolos de acciones: {e}")


def initialize_forex_symbols():
    global forex_symbols_map, all_forex_symbols
    try:
        with open("data/forex.csv", newline="", encoding="utf-8") as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                symbol = row["Ticker"]
                name = row["Instrument"]
                forex_symbols_map[name] = symbol
                all_forex_symbols.append(symbol)
    except Exception as e:
        print(f"Error al inicializar los símbolos de pares de divisas: {e}")


# ---------------------------------------------------------------------------


# Endpoints para obtener listados de los simbolos de criptomonedas, acciones y divisas para barra de busqueda


@app.route("/api/crypto-symbols")
def api_crypto_symbols():
    # Devuelve el mapa de símbolos y nombres de criptomonedas
    return jsonify(crypto_symbols_map)


@app.route("/api/stock-symbols")
def api_stock_symbols():
    # Devuelve el mapa de símbolos y nombres de acciones
    return jsonify(stocks_symbols_map)


@app.route("/api/forex-symbols")
def api_forex_symbols():
    # Devuelve el mapa de símbolos y nombres de pares de divisas
    return jsonify(forex_symbols_map)


# ---------------------------------------------------------------------------


# Endpoints para listado de activos financieros


# ------------------------Criptomonedas-------------------


def __get_crypto_data_from_api():
    coins = cg.get_coins_markets(
        vs_currency="usd",
        order="market_cap_desc",
        per_page=250,  # Obtener 250 criptomonedas de una vez
        page=1,
        sparkline=True,
        price_change_percentage="7d",
    )

    crypto_cache.clear()
    for index, coin in enumerate(coins):
        price_change_24h = coin["price_change_percentage_24h"]
        price_change_7d = coin["price_change_percentage_7d_in_currency"]

        crypto_info = {
            "symbol": coin["symbol"].upper(),
            "name": coin["name"],
            "image": coin["image"],
            "current_price": coin["current_price"],
            "price_change_24h": round(price_change_24h, 2)
            if price_change_24h is not None
            else 0.0,
            "price_change_7d": round(price_change_7d, 2)
            if price_change_7d is not None
            else 0.0,
            "market_cap": coin["market_cap"],
            "sparkline": coin["sparkline_in_7d"]["price"]
            if "sparkline_in_7d" in coin
            else [],
        }
        crypto_cache[index] = {"timestamp": datetime.now(), "data": crypto_info}


@app.route("/crypto_listings")
def crypto_listings():
    if not __is_cache_up_to_date(crypto_cache, 0):
        __get_crypto_data_from_api()

    crypto_data = [crypto_cache[index]["data"] for index in crypto_cache]
    return jsonify(crypto_data)


# ------------------------Acciones------------------------


def __get_stocks_data_from_api():
    try:
        data = yf.download(all_stock_symbols, period="7d", group_by="ticker")
    except Exception as e:
        print(f"Error descargando datos para los símbolos: {e}")
        return

    stocks_cache.clear()
    for index, symbol in enumerate(all_stock_symbols):
        try:
            if symbol not in data or len(data[symbol]) < 2:
                continue

            hist = data[symbol]
            today_price = hist["Close"].iloc[-1]
            if math.isnan(today_price):
                continue

            price_change_24h = (
                (today_price - hist["Close"].iloc[-2]) / hist["Close"].iloc[-2] * 100
            )
            price_change_7d = (
                (today_price - hist["Close"].iloc[0]) / hist["Close"].iloc[0] * 100
            )

            stock = yf.Ticker(symbol)
            stock_info = {
                "symbol": symbol,
                "name": stock.info.get("shortName", ""),
                "current_price": round(today_price, 2),
                "price_change_24h": round(price_change_24h, 2),
                "price_change_7d": round(price_change_7d, 2)
                if not math.isnan(price_change_7d)
                else "-",
                "sparkline": hist["Close"].tolist(),
                "market_cap": stock.info.get("marketCap", 0),
            }
            stocks_cache[index] = {
                "timestamp": datetime.now(),
                "data": stock_info,
            }

        except Exception as e:
            print(f"Error procesando el símbolo {symbol}: {e}")


@app.route("/stocks_listings")
def stocks_listings():
    if not __is_cache_up_to_date(stocks_cache, 0):
        __get_stocks_data_from_api()

    stocks_data = [stocks_cache[index]["data"] for index in stocks_cache]
    return jsonify(stocks_data)


# ------------------------Divisas-------------------------


def __get_forex_data_from_api():
    subset_symbols = all_forex_symbols
    try:
        data = yf.download(subset_symbols, period="7d", group_by="ticker")
    except Exception as e:
        print(f"Error descargando datos para los símbolos: {e}")
        return

    forex_cache.clear()
    for index, symbol in enumerate(subset_symbols):
        try:
            if symbol not in data or len(data[symbol]) < 2:
                continue

            hist = data[symbol]
            today_price = hist["Close"].iloc[-1]
            if math.isnan(today_price):
                continue

            price_change_24h = (
                (today_price - hist["Close"].iloc[-2]) / hist["Close"].iloc[-2] * 100
            )
            price_change_7d = (
                (today_price - hist["Close"].iloc[0]) / hist["Close"].iloc[0] * 100
            )

            stock = yf.Ticker(symbol)
            stock_info = {
                "symbol": symbol,
                "name": stock.info.get("shortName", "-")
                if stock.info.get("shortName")
                else "-",
                "current_price": today_price if not math.isnan(today_price) else "-",
                "price_change_24h": round(price_change_24h, 2)
                if not math.isnan(price_change_24h)
                else "-",
                "price_change_7d": round(price_change_7d, 2)
                if not math.isnan(price_change_7d)
                else "-",
                "sparkline": [
                    price for price in hist["Close"].tolist() if not math.isnan(price)
                ],
            }
            forex_cache[index] = {
                "timestamp": datetime.now(),
                "data": stock_info,
            }

        except Exception as e:
            print(f"Error procesando el símbolo {symbol}: {e}")


@app.route("/forex_listings")
def forex_listings():
    if not __is_cache_up_to_date(forex_cache, 0):
        __get_forex_data_from_api()

    forex_data = [forex_cache[index]["data"] for index in forex_cache]
    return jsonify(forex_data)


# ---------------------------------------------------------------------------


# Endpoints para obtener resúmenes de activos financieros


@app.route("/api/summary")
def api_summary():
    symbol = request.args.get("symbol")

    if symbol in crypto_symbols_map:
        return get_crypto_summary(symbol)
    elif symbol in stocks_symbols_map:
        return get_stock_summary(symbol)
    elif symbol in forex_symbols_map:
        return get_forex_summary(forex_symbols_map[symbol], symbol)
    else:
        return jsonify({"error": "Símbolo no encontrado"}), 404


def get_crypto_summary(symbol):
    try:
        coin_id = get_coin_id(symbol)
        if not coin_id:
            return jsonify({"error": "Símbolo no encontrado en CoinGecko"}), 404

        print(f"Coin ID for {symbol}: {coin_id}")  # Agregar para depuración

        coin_data = cg.get_coin_by_id(coin_id, localization=False)
        summary = {
            "symbol": coin_data["symbol"].upper(),
            "name": coin_data["name"],
            "current_price": coin_data["market_data"]["current_price"]["usd"],
            "market_cap": coin_data["market_data"]["market_cap"]["usd"],
            "total_volume": coin_data["market_data"]["total_volume"]["usd"],
            "high_24h": coin_data["market_data"]["high_24h"]["usd"],
            "low_24h": coin_data["market_data"]["low_24h"]["usd"],
            "price_change_percentage_1h": coin_data["market_data"][
                "price_change_percentage_1h_in_currency"
            ]["usd"],
            "price_change_percentage_24h": coin_data["market_data"][
                "price_change_percentage_24h"
            ],
            "price_change_percentage_7d": coin_data["market_data"][
                "price_change_percentage_7d"
            ],
            "circulating_supply": coin_data["market_data"]["circulating_supply"],
            "total_supply": coin_data["market_data"]["total_supply"],
            "ath": coin_data["market_data"]["ath"]["usd"],
            "ath_date": coin_data["market_data"]["ath_date"]["usd"],
            "atl": coin_data["market_data"]["atl"]["usd"],
            "atl_date": coin_data["market_data"]["atl_date"]["usd"],
            "sentiment_votes_up_percentage": coin_data["sentiment_votes_up_percentage"],
            "sentiment_votes_down_percentage": coin_data[
                "sentiment_votes_down_percentage"
            ],
        }
        return jsonify(summary)
    except Exception as e:
        return jsonify({"error": f"Error al obtener datos de criptomoneda: {e}"}), 500


def get_stock_summary(symbol):
    try:
        stock = yf.Ticker(symbol)
        stock_info = stock.info
        summary = {
            "symbol": symbol.upper(),
            "name": stock_info.get("shortName", ""),
            "current_price": stock_info.get("currentPrice", 0),
            "market_cap": stock_info.get("marketCap", 0),
            "total_volume": stock_info.get("volume", 0),
            "high_24h": stock_info.get("dayHigh", 0),
            "low_24h": stock_info.get("dayLow", 0),
            "high_52_weeks": stock_info.get("fiftyTwoWeekHigh", 0),
            "low_52_weeks": stock_info.get("fiftyTwoWeekLow", 0),
            "beta": stock_info.get("beta", 0),
            "pe_ratio": stock_info.get("trailingPE", 0),
            "eps": stock_info.get("trailingEps", 0),
            "dividend_yield": stock_info.get("dividendYield", 0),
            "dividend_date": stock_info.get("dividendDate", ""),
        }
        return jsonify(summary)
    except Exception as e:
        return jsonify({"error": f"Error al obtener datos de acción: {e}"}), 500


def get_forex_summary(forex_ticker, symbol):
    try:
        forex_data = yf.Ticker(forex_ticker)
        hist = forex_data.history(period="1d")

        if hist.empty:
            return jsonify({"error": "No se encontraron datos para el símbolo"}), 404

        current_price = hist["Close"].iloc[-1]
        summary = {
            "symbol": forex_ticker,
            "name": symbol,
            "current_price": current_price,
            "market_cap": None,
            "total_volume": None,
            "high_24h": hist["High"].iloc[-1],
            "low_24h": hist["Low"].iloc[-1],
        }
        return jsonify(summary)
    except Exception as e:
        return jsonify({"error": f"Error al obtener datos de divisas: {e}"}), 500


# ---------------------------------------------------------------------------


# Endpoint para obtener datos de gráfico de los activos financieros (Primera versión de BacktestingPage)


@app.route("/api/chart", methods=["GET"])
def get_chart_data():
    symbol = request.args.get("symbol").upper()
    interval = request.args.get("interval", "1d")

    if symbol in crypto_symbols_map:
        return get_crypto_chart_data_yf(symbol, interval)
    elif symbol in stocks_symbols_map:
        return get_stock_chart_data(symbol, interval)
    elif symbol in forex_symbols_map:
        return get_forex_chart_data(forex_symbols_map[symbol], interval)
    else:
        return jsonify({"error": "Símbolo no encontrado"}), 404


def get_stock_chart_data(symbol, interval):
    try:
        yf_intervals = {
            "15m": "15m",
            "30m": "30m",
            "1h": "1h",
            "1D": "1d",
        }
        yf_interval = yf_intervals.get(interval, "1d")

        end_date = datetime.now()
        if yf_interval == "15m" or yf_interval == "30m":
            start_date = end_date - timedelta(days=59)
        elif yf_interval == "1h":
            start_date = end_date - timedelta(days=729)
        else:
            start_date = end_date - timedelta(days=1460)

        hist = yf.Ticker(symbol).history(
            interval=yf_interval,
            start=start_date.strftime("%Y-%m-%d"),
            end=end_date.strftime("%Y-%m-%d"),
        )

        print(
            f"Datos obtenidos para {symbol} en intervalo {interval}: {len(hist)} registros"
        )

        chart_data = [
            {
                "time": int(row.name.timestamp()),
                "open": row["Open"],
                "high": row["High"],
                "low": row["Low"],
                "close": row["Close"],
            }
            for index, row in hist.iterrows()
        ]
        return jsonify(chart_data)
    except Exception as e:
        return jsonify(
            {"error": f"Error al obtener datos del gráfico de acción: {e}"}
        ), 500


def get_forex_chart_data(symbol, interval):
    try:
        yf_intervals = {
            "15m": "15m",
            "30m": "30m",
            "1h": "1h",
            "1D": "1d",
        }
        yf_interval = yf_intervals.get(interval, "1d")

        end_date = datetime.now()
        if yf_interval == "15m" or yf_interval == "30m":
            start_date = end_date - timedelta(days=59)
        elif yf_interval == "1h":
            start_date = end_date - timedelta(days=729)
        else:
            start_date = end_date - timedelta(days=1460)

        hist = yf.Ticker(symbol).history(
            interval=yf_interval,
            start=start_date.strftime("%Y-%m-%d"),
            end=end_date.strftime("%Y-%m-%d"),
        )

        print(
            f"Datos obtenidos para {symbol} en intervalo {interval}: {len(hist)} registros"
        )

        chart_data = [
            {
                "time": int(row.name.timestamp()),
                "open": row["Open"],
                "high": row["High"],
                "low": row["Low"],
                "close": row["Close"],
            }
            for index, row in hist.iterrows()
        ]
        return jsonify(chart_data)
    except Exception as e:
        return jsonify(
            {"error": f"Error al obtener datos del gráfico de divisas: {e}"}
        ), 500


def get_crypto_chart_data_yf(symbol, interval):
    try:
        yf_intervals = {
            "15m": "15m",
            "30m": "30m",
            "1h": "1h",
            "1D": "1d",
        }
        yf_interval = yf_intervals.get(interval, "1d")

        symbol_yf = f"{symbol}-USD"

        end_date = datetime.now()
        if yf_interval == "15m" or yf_interval == "30m":
            start_date = end_date - timedelta(days=59)
        elif yf_interval == "1h":
            start_date = end_date - timedelta(days=729)
        else:
            start_date = end_date - timedelta(days=1460)

        hist = yf.Ticker(symbol_yf).history(
            interval=yf_interval,
            start=start_date.strftime("%Y-%m-%d"),
            end=end_date.strftime("%Y-%m-%d"),
        )

        print(
            f"Datos obtenidos para {symbol_yf} en intervalo {interval}: {len(hist)} registros"
        )

        chart_data = [
            {
                "time": int(row.name.timestamp()),
                "open": row["Open"],
                "high": row["High"],
                "low": row["Low"],
                "close": row["Close"],
            }
            for index, row in hist.iterrows()
        ]
        return jsonify(chart_data)
    except Exception as e:
        return jsonify(
            {"error": f"Error al obtener datos del gráfico de criptomoneda: {e}"}
        ), 500


# ---------------------------------------------------------------------------


# Funciones para obtener datos históricos de activos financieros necesarias para el backtesting


def __get_historical_data(symbol, start_date, end_date, interval):
    yf_intervals = {
        "15m": "15m",
        "30m": "30m",
        "1h": "1h",
        "1D": "1d",
    }
    yf_interval = yf_intervals.get(interval, "1d")

    print("historical_data 1")
    if symbol in crypto_symbols_map:
        print("historical_data dentro de crypto")
        return __get_crypto_historical_data(symbol, yf_interval, start_date, end_date)
    elif symbol in stocks_symbols_map:
        print("historical_data dentro de stocks")
        return __get_Stocks_Forex_historical_data(
            symbol, yf_interval, start_date, end_date
        )
    elif symbol in forex_symbols_map:
        print("historical_data dentro de forex")
        return __get_Stocks_Forex_historical_data(
            forex_symbols_map[symbol], yf_interval, start_date, end_date
        )
    else:
        return ValueError("Simbolo no encontrado")


def __get_Stocks_Forex_historical_data(symbol, interval, start_date, end_date):
    hist = yf.Ticker(symbol).history(
        interval=interval,
        start=start_date,
        end=end_date,
    )

    print(
        f"Datos obtenidos para {symbol} en intervalo {interval}: {len(hist)} registros"
    )

    if hist.empty:
        raise ValueError(
            "No se han encontrado datos para el símbolo y el rango de fechas proporcionados"
        )
    return hist[["Open", "High", "Low", "Close"]]


def __get_crypto_historical_data(symbol, interval, start_date, end_date):
    symbol_yf = f"{symbol}-USD"

    hist = yf.Ticker(symbol_yf).history(
        interval=interval,
        start=start_date,
        end=end_date,
    )

    print(
        f"Datos obtenidos para {symbol_yf} en intervalo {interval}: {len(hist)} registros"
    )
    if hist.empty:
        raise ValueError(
            "No se han encontrado datos para el símbolo y el rango de fechas proporcionados"
        )
    return hist[["Open", "High", "Low", "Close"]]


def calculate_stop_loss_take_profit(trade_amount, risk_reward_ratio, leverage):
    print("risk_in_dollars", trade_amount)
    
    desired_profit_in_dollars = trade_amount * risk_reward_ratio

    total_position = trade_amount * leverage

    sl_percentage = trade_amount / total_position

    tp_percentage = desired_profit_in_dollars / total_position

    print("percentage_change_stop_loss", sl_percentage)
    print("percentage_change_take_profit", tp_percentage)

    return sl_percentage, tp_percentage


# ---------------------------------------------------------------------------


# Endpoint para backtesting de estrategias de trading


def backtest(
    data,
    signals,
    initial_capital,
    risk_reward_ratio,
    trade_amount,
    sl_percentage,
    tp_percentage,
    leverage,
    use_auto_sl_tp,
    exit_conditions,
):
    # Inicialización de variables
    positions = pd.DataFrame(index=signals.index).fillna(0.0)
    portfolio = pd.DataFrame(index=signals.index).fillna(0.0)
    portfolio["cash"] = float(initial_capital)
    portfolio["total"] = float(initial_capital)
    portfolio["hold"] = data["Close"] * (initial_capital / data["Close"].iloc[0])

    open_positions = []
    current_cash = float(initial_capital)

    winning_trades = 0
    losing_trades = 0
    trade_durations = []
    peak = float(initial_capital)
    trough = float(initial_capital)

    for date, signal in signals.iterrows():
        entry_price = data.loc[date, "Close"]
        signals.loc[date, "price"] = entry_price

        # Verificar y cerrar posiciones abiertas
        for position in open_positions[:]:
            current_price = data.loc[date, "Close"]

            if exit_conditions and exit_conditions(position, current_price, date):
                # Cerrar posición por condiciones de salida
                gain_loss = (current_price - position["entry_price"]) / position[
                    "entry_price"
                ]
                gain_loss *= position["leverage"]
                if gain_loss < -1:
                    gain_loss = -1
                trade_value = position["trade_amount"] * (1 + gain_loss)
                current_cash += trade_value
                open_positions.remove(position)
                if gain_loss > 0:
                    winning_trades += 1
                else:
                    losing_trades += 1
                trade_durations.append((date - position["entry_date"]).days)
            elif position["direction"] == 1:
                gain_loss = (current_price - position["entry_price"]) / position[
                    "entry_price"
                ]
                gain_loss *= position["leverage"]
                if gain_loss < -1:
                    losing_trades += 1
                    open_positions.remove(position)
                elif (
                    current_price <= position["sl_price"]
                    or current_price >= position["tp_price"]
                ):
                    trade_value = position["trade_amount"] * (1 + gain_loss)
                    current_cash += trade_value
                    open_positions.remove(position)
                    if gain_loss > 0:
                        winning_trades += 1
                    else:
                        losing_trades += 1
                    trade_durations.append((date - position["entry_date"]).days)
            elif position["direction"] == -1:
                gain_loss = (position["entry_price"] - current_price) / position[
                    "entry_price"
                ]
                gain_loss *= position["leverage"]
                if gain_loss < -1:
                    losing_trades += 1
                    open_positions.remove(position)
                elif (
                    current_price >= position["sl_price"]
                    or current_price <= position["tp_price"]
                ):
                    trade_value = position["trade_amount"] * (1 + gain_loss)
                    current_cash += trade_value
                    open_positions.remove(position)
                    if gain_loss > 0:
                        winning_trades += 1
                    else:
                        losing_trades += 1
                    trade_durations.append((date - position["entry_date"]).days)

        # Verificar si hay efectivo suficiente para abrir nuevas posiciones
        if current_cash >= trade_amount:
            # Abrir nuevas posiciones
            if signal["positions"] > 0:  # Señal de compra
                sl_price = (
                    entry_price - (entry_price * sl_percentage)
                    if use_auto_sl_tp
                    else signal.get("stop_loss", None)
                )
                tp_price = (
                    entry_price + (entry_price * tp_percentage)
                    if use_auto_sl_tp
                    else signal.get("take_profit", None)
                )
                signals.loc[date, "sl_price"] = sl_price
                signals.loc[date, "tp_price"] = tp_price
                open_positions.append(
                    {
                        "entry_date": date,
                        "entry_price": entry_price,
                        "sl_price": sl_price,
                        "tp_price": tp_price,
                        "direction": 1,
                        "trade_amount": trade_amount,
                        "leverage": leverage,
                    }
                )
                current_cash -= trade_amount

            elif signal["positions"] < 0:  # Señal de venta
                sl_price = (
                    entry_price + (entry_price * sl_percentage)
                    if use_auto_sl_tp
                    else signal.get("stop_loss", None)
                )
                tp_price = (
                    entry_price - (entry_price * tp_percentage)
                    if use_auto_sl_tp
                    else signal.get("take_profit", None)
                )
                signals.loc[date, "sl_price"] = sl_price
                signals.loc[date, "tp_price"] = tp_price
                open_positions.append(
                    {
                        "entry_date": date,
                        "entry_price": entry_price,
                        "sl_price": sl_price,
                        "tp_price": tp_price,
                        "direction": -1,
                        "trade_amount": trade_amount,
                        "leverage": leverage,
                    }
                )
                current_cash -= trade_amount

        totalUnrealizedPnl = 0
        # Actualizar el valor de las posiciones abiertas
        for position in open_positions:
            current_price = data.loc[date, "Close"]
            if position["direction"] == 1:
                change_percentage = (
                    current_price - position["entry_price"]
                ) / position["entry_price"]
            elif position["direction"] == -1:
                change_percentage = (
                    position["entry_price"] - current_price
                ) / position["entry_price"]
            change_percentage *= position["leverage"]
            unrealizedPnl = position["trade_amount"] * (1 + change_percentage)
            totalUnrealizedPnl += unrealizedPnl

        positions.loc[date, "asset"] = totalUnrealizedPnl
        portfolio.loc[date, "cash"] = current_cash

        # Calcular el valor total del portafolio
        total_value = current_cash + totalUnrealizedPnl
        if total_value > peak:
            peak = total_value
        if total_value < trough:
            trough = total_value

        portfolio.loc[date, "total"] = total_value

    max_drawdown = (peak - trough) / peak
    max_increase = (peak - initial_capital) / initial_capital

    if trade_durations:
        average_duration = sum(trade_durations) / len(trade_durations)
    else:
        average_duration = 0

    portfolio["positions"] = positions["asset"]
    portfolio["total"] = portfolio["positions"] + portfolio["cash"]
    portfolio["returns"] = portfolio["total"].pct_change()

    final_hold_value = portfolio["hold"].iloc[-1]
    final_strategy_value = portfolio["total"].iloc[-1]
    unrealized_pnl = totalUnrealizedPnl

    summary = {
        "winning_trades": winning_trades,
        "losing_trades": losing_trades,
        "max_drawdown": max_drawdown,
        "max_increase": max_increase,
        "average_duration": average_duration,
        "num_trades": winning_trades + losing_trades,
        "num_positions": len(open_positions),
        "final_hold_value": final_hold_value,
        "unrealized_pnl": unrealized_pnl,
        "final_cash_value": current_cash,
        "final_strategy_value": final_strategy_value,
    }

    return portfolio, summary


@app.route("/api/backtest", methods=["POST"])
def backtest_endpoint():
    data = request.json  # Obtener los datos del request en formato JSON

    # Obtener los parámetros
    symbol = data["symbol"]
    start_date = data["start_date"]
    end_date = data["end_date"]
    temporalidad = data["temporalidad"]
    generate_signals_code = data["generate_signals"]
    exit_conditions_code = data.get("exit_conditions", None)
    initial_capital = data.get("initial_capital", 10000.0)
    trade_risk = data.get("trade_risk", 1)
    leverage = data.get("leverage", 50)
    risk_reward_ratio = data.get("risk_reward_ratio", 2)
    use_auto_sl_tp = data.get("use_auto_sl_tp", 1)

    # Calcular la cantidad de trade
    trade_amount = initial_capital * (trade_risk / 100)

    # Calcular SL y TP automáticos si se requiere
    if use_auto_sl_tp:
        sl_percentage, tp_percentage = calculate_stop_loss_take_profit(
            trade_amount, risk_reward_ratio, leverage
        )
    else:
        sl_percentage = tp_percentage = None

    # Obtener datos históricos del símbolo
    try:
        historical_data = __get_historical_data(
            symbol, start_date, end_date, temporalidad
        )
    except Exception as e:
        return jsonify({"error": f"Error obteniendo datos históricos: {str(e)}"}), 500

    # Crear un diccionario para el espacio de nombres local y ejecutar las funciones proporcionadas
    local_namespace = {}
    try:
        exec(generate_signals_code, globals(), local_namespace)
        generate_signals = local_namespace.get("generate_signals")

        if exit_conditions_code:
            exec(exit_conditions_code, globals(), local_namespace)
            exit_conditions = local_namespace.get("exit_conditions")
        else:
            exit_conditions = None

        if not generate_signals or not callable(generate_signals):
            return jsonify(
                {"error": "Función 'generate_signals' no encontrada o no es callable"}
            ), 400
        if exit_conditions_code and (
            not exit_conditions or not callable(exit_conditions)
        ):
            return jsonify(
                {"error": "Función 'exit_conditions' no encontrada o no es callable"}
            ), 400

    except Exception as e:
        return jsonify(
            {"error": f"Error ejecutando el código del usuario: {str(e)}"}
        ), 500

    # Generar señales
    try:
        signals = generate_signals(historical_data)
        if not use_auto_sl_tp:
            if "stop_loss" not in signals.columns:
                return jsonify(
                    {"error": "Columna 'stop_loss' no encontrada en señales"}
                ), 400
            if "take_profit" not in signals.columns:
                return jsonify(
                    {"error": "Columna 'take_profit' no encontrada en señales"}
                ), 400
        if "positions" not in signals.columns:
            return jsonify(
                {"error": "Columna 'positions' no encontrada en señales"}
            ), 400
    except Exception as e:
        return jsonify({"error": f"Error ejecutando 'generate_signals': {str(e)}"}), 500

    # Ejecutar backtest
    try:
        portfolio, summary = backtest(
            historical_data,
            signals,
            initial_capital,
            risk_reward_ratio,
            trade_amount,
            sl_percentage,
            tp_percentage,
            leverage,
            use_auto_sl_tp,
            exit_conditions,
        )
    except Exception as e:
        return jsonify({"error": f"Error ejecutando backtest: {str(e)}"}), 500

    # Convertir los índices a strings en el formato adecuado
    def format_date_index(index):
        return index.strftime("%Y-%m-%dT%H:%M:%S")

    signals.index = signals.index.map(format_date_index)
    portfolio.index = portfolio.index.map(format_date_index)

    # Función para limpiar valores NaN e Infinity
    def clean_data(data):
        for key, value in data.items():
            if isinstance(value, dict):
                clean_data(value)
            else:
                if pd.isna(value) or value == float("inf") or value == float("-inf"):
                    data[key] = None

    # Convertir a diccionario y limpiar datos
    signals_dict = signals.to_dict()
    portfolio_dict = portfolio.to_dict()
    clean_data(signals_dict)
    clean_data(portfolio_dict)

    results = {
        "signals": signals_dict,
        "portfolio": portfolio_dict,
        "summary": {
            **summary,
        },
    }

    # Devolvemos los resultados del backtest
    return jsonify(results)


# ---------------------------------------------------------------------------

# Función para obtener la respuesta de OpenAI

def chat_with_gpt3(prompt):
    return requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={
            "Authorization": "Bearer sk-proj-fvWacwpnqYYfG1HAM5t4T3BlbkFJIz7oBhwcUYcmDbHBvqxE",
            "Content-Type": "application/json",
        },
        json={
            "model": "gpt-3.5-turbo",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 2500,
            "n": 1,
            "stop": ["\n\n"],
        },
    )



# Endpoint para obtener la respuesta de OpenAI

@app.route("/api/generate-algorithm", methods=["POST"])
def generate_algorithm():
    data = request.get_json()
    generate_signals = data.get("generate_signals", "")
    exit_conditions = data.get("exit_conditions", "")

    print("generate_signals:", generate_signals)
    print("exit_conditions:", exit_conditions)
    print("-------------------------------------")
    # Preparamos la consulta para la API de OpenAI incluyendo las instrucciones del usuario.
    prompt = (
        "Quiero que escribas la funcion generate_signals(data) cuyo funcionamiento se describe a continuación:\n\n"
        f"Descripción de generate_signals: {generate_signals}\n\n"
        "Respetando las siguientes instrucciones:\n\n"
        "generate_signals(data) debe seguir esta estructura:\n"
        "def generate_signals(data):\n"
        "    signals = pd.DataFrame(index=data.index)\n"
        "    signals['positions'] = ...  # Valores > 0: posición larga, < 0: posición corta, 0: sin operación.\n"
        "    signals['stop_loss'] = ...  # Opcional: valor de stop_loss.\n"
        "    signals['take_profit'] = ...  # Opcional: valor de take_profit.\n"
        "    return signals\n\n"
        "Estructura del DataFrame 'data'\n\n"
        "El DataFrame 'data' tiene las siguientes columnas:\n"
        "- 'Close': Precio de cierre.\n"
        "- 'High': Precio máximo.\n"
        "- 'Low': Precio mínimo.\n"
        "- 'Open': Precio de apertura.\n\n"
        "Librerías Disponibles\n"
        "- pandas as pd\n"
        "- numpy as np\n"
        "Por favor ES MUY IMPORTANTE que solo proporciones el código de las funciones (Que sea ejecutable), no incluyas comentarios adicionales ni etiquetas de código. Necesito que la respuesta sea consistente y sin ruido adicional.\n\n"
    )

    # Realizamos la consulta a la API de OpenAI
    response = chat_with_gpt3(prompt)

    if response.status_code == 200:
        # Recuperamos la respuesta completa de la API.
        chatgpt_response = response.json()["choices"][0]["message"]["content"].strip()
        print("chatgpt_response:", response.json()["choices"][0]["message"]["content"])

        # Eliminamos las etiquetas de código ("```python" y "```") si están presentes.
        if chatgpt_response.startswith("```python"):
            chatgpt_response = chatgpt_response[9:].strip()
        if chatgpt_response.endswith("```"):
            chatgpt_response = chatgpt_response[:-3].strip()

        # Si se proporcionaron instrucciones para la función exit_conditions, solicitamos la respuesta al usuario.
        if exit_conditions != "":
            prompt = (
                "Quiero que escribas la función exit_conditions(position, current_price, date) en base a la siguiente descripción:\n\n"
                f"{exit_conditions}\n"
                "Aegurandote de que cumple las siguientes instrucciones:\n\n"
                "exit_conditions(position, current_price, date) debe seguir esta estructura:\n\n"
                "def exit_conditions(position, current_price, date):\n"
                "    # Lógica del usuario para definir condiciones de salida.\n"
                "    return (boolean)\n\n"
                "Estructura del Diccionario position:\n"
                "- 'entry_date': Fecha de entrada.\n"
                "- 'entry_price': Precio de entrada.\n"
                "- 'position_size': Tamaño de la posición (ajustado por apalancamiento).\n"
                "- 'sl_price': Precio de stop_loss.\n"
                "- 'tp_price': Precio de take_profit.\n"
                "- 'direction': Dirección de la posición (1 para larga, -1 para corta).\n"
                "- 'trade_amount': Cantidad invertida en la posición.\n"
                "- 'leverage': Apalancamiento aplicado.\n\n"
                "Librerías Disponibles\n"
                "- pandas as pd\n"
                "- numpy as np\n"
                "Por favor ES MUY IMPORTANTE que solo proporciones el código de las funciones, no incluyas comentarios adicionales ni etiquetas de código. Necesito que la respuesta sea consistente y sin ruido adicional.\n\n"
            )

            # Realizamos la consulta a la API de OpenAI
            response = chat_with_gpt3(prompt)

            if response.status_code == 200:
                # Recuperamos la respuesta completa de la API.
                chatgpt_response2 = response.json()["choices"][0]["message"]["content"].strip()
                print("chatgpt_response:", response.json()["choices"][0]["message"]["content"])

                # Eliminamos las etiquetas de código ("```python" y "```") si están presentes.
                if chatgpt_response2.startswith("```python"):
                    chatgpt_response2 = chatgpt_response2[9:].strip()
                if chatgpt_response2.endswith("```"):
                    chatgpt_response2 = chatgpt_response2[:-3].strip()
            else:
                # Devolvemos un mensaje de error si la solicitud falló.
                return jsonify(
                    {"error": "Error al generar el algoritmo", "details": response.text}
                ), 500

            # Concatenamos las respuestas generadas por OpenAI.
            chatgpt_response = chatgpt_response + "\n\n" + chatgpt_response2

        # Devolvemos la respuesta generada por OpenAI.
        return jsonify({"codigo": chatgpt_response})
    else:
        # Devolvemos un mensaje de error si la solicitud falló.
        return jsonify(
            {"error": "Error al generar el algoritmo", "details": response.text}
        ), 500


# ----------------------------------------------------------------------------

if __name__ == "__main__":
    initialize_crypto_symbols()  # Cargar símbolos de criptomonedas al iniciar
    initialize_stock_symbols()  # Cargar símbolos de acciones al iniciar
    initialize_forex_symbols()  # Cargar símbolos de pares de divisas al iniciar
    app.run(debug=True, port=8080)
