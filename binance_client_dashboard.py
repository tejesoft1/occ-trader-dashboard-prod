import logging
from binance.client import Client

logger = logging.getLogger(__name__)


class BinanceFuturesReader:
    """
    Cliente de SOLO LECTURA para Futures. Pensado para usar una API key
    separada con permiso "Enable Reading" / "Read Info" únicamente -- sin
    "Enable Futures" de trading. Métodos de escritura (market_order,
    set_leverage, close_all, etc.) NO existen en esta clase a propósito.
    """

    def __init__(self, api_key, api_secret, testnet=True):
        self.client = Client(api_key, api_secret, testnet=testnet)

    def get_balance(self):
        acc = self.client.futures_account()
        for a in acc['assets']:
            if a['asset'] == 'USDT':
                return {
                    'balance':        float(a['walletBalance']),
                    'unrealized_pnl': float(a['unrealizedProfit']),
                    'total_equity':   float(a['marginBalance']),
                }
        raise ValueError("USDT no encontrado en la cuenta de futuros")

    def get_position(self, symbol):
        positions = self.client.futures_position_information(symbol=symbol)
        for p in positions:
            amt = float(p['positionAmt'])
            if p['symbol'] == symbol and amt != 0:
                return {
                    'side':           'long' if amt > 0 else 'short',
                    'quantity':       abs(amt),
                    'entry_price':    float(p['entryPrice']),
                    'unrealized_pnl': float(p['unRealizedProfit']),
                }
        return None

    def get_account_trades(self, symbol, start_time_ms=None, end_time_ms=None,
                            limit=1000):
        """
        Fills de Futures para un símbolo. Cada fill incluye orderId, price,
        qty, realizedPnl, commission, side, time (ms epoch UTC).
        """
        params = {'symbol': symbol, 'limit': limit}
        if start_time_ms is not None:
            params['startTime'] = start_time_ms
        if end_time_ms is not None:
            params['endTime'] = end_time_ms
        return self.client.futures_account_trades(**params)

    def get_account_trades_paginated(self, symbol, start_time_ms, end_time_ms):
        """
        Pagina get_account_trades en ventanas de 7 días (límite de Binance
        cuando se usa startTime/endTime juntos) y por timestamp si una
        ventana devuelve 1000 resultados (el máximo).
        """
        SEVEN_DAYS_MS = 7 * 24 * 60 * 60 * 1000
        all_trades = []
        cursor = start_time_ms
        while cursor < end_time_ms:
            window_end = min(cursor + SEVEN_DAYS_MS, end_time_ms)
            trades = self.get_account_trades(symbol, cursor, window_end, limit=1000)
            all_trades.extend(trades)
            if len(trades) == 1000:
                last_time = trades[-1]['time']
                cursor = last_time + 1
            else:
                cursor = window_end

        seen = set()
        deduped = []
        for t in all_trades:
            key = (t['orderId'], t['time'], t['price'], t['qty'], t.get('side'), t.get('buyer'))
            if key not in seen:
                seen.add(key)
                deduped.append(t)
        return deduped
