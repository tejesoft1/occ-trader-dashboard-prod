import logging
from datetime import datetime, timezone, timedelta
from flask import Flask, request, jsonify

import config_dashboard as config
import database_dashboard as db
from binance_client_dashboard import BinanceFuturesReader

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
)
logger = logging.getLogger(__name__)

app = Flask(__name__)


# ── Helpers ────────────────────────────────────────────────────────────────
def _check_token():
    """Token simple en query string o header, para no dejar el endpoint
    completamente abierto. No es autenticación fuerte -- es solo lectura,
    pero evita scraping casual desde GitHub Pages público."""
    if not config.API_TOKEN:
        return True  # sin token configurado -> abierto (solo para pruebas)
    sent = request.args.get('token') or request.headers.get('X-Dashboard-Token')
    return sent == config.API_TOKEN


def _cors(resp):
    resp.headers['Access-Control-Allow-Origin'] = config.CORS_ORIGIN
    resp.headers['Access-Control-Allow-Headers'] = 'X-Dashboard-Token, Content-Type'
    resp.headers['Access-Control-Allow-Methods'] = 'GET, OPTIONS'
    return resp


@app.after_request
def add_cors(resp):
    return _cors(resp)


def _parse_ts(s, default):
    if not s:
        return default
    try:
        return datetime.strptime(s, '%Y-%m-%d').replace(tzinfo=timezone.utc)
    except ValueError:
        return datetime.strptime(s, '%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc)


def _ms(dt):
    return int(dt.timestamp() * 1000)


def _fmt_ts(s):
    """'YYYY-MM-DD HH:MM:SS' (UTC, como lo guarda database.py) -> ISO 8601."""
    if not s:
        return None
    return s.replace(' ', 'T') + 'Z'


# ── Reconciliación: Binance fills <-> Postgres trades ────────────────────────
def _group_binance_fills_by_order(fills):
    """Agrupa fills (puede haber partial fills) por orderId, sumando qty,
    realizedPnl y commission, y promediando el precio ponderado por qty."""
    grouped = {}
    for f in fills:
        oid = f['orderId']
        qty = float(f['qty'])
        price = float(f['price'])
        pnl = float(f.get('realizedPnl', 0))
        comm = float(f.get('commission', 0))
        if oid not in grouped:
            grouped[oid] = {
                'order_id': str(oid),
                'side': f['side'],
                'qty': 0.0,
                'notional': 0.0,
                'realized_pnl': 0.0,
                'commission': 0.0,
                'time_ms': f['time'],
            }
        g = grouped[oid]
        g['qty'] += qty
        g['notional'] += qty * price
        g['realized_pnl'] += pnl
        g['commission'] += comm
        g['time_ms'] = min(g['time_ms'], f['time'])

    out = []
    for g in grouped.values():
        g['avg_price'] = g['notional'] / g['qty'] if g['qty'] else 0.0
        g['time'] = datetime.fromtimestamp(g['time_ms'] / 1000, tz=timezone.utc) \
            .strftime('%Y-%m-%d %H:%M:%S')
        out.append(g)
    return out


@app.route('/api/reconciliation', methods=['GET', 'OPTIONS'])
def reconciliation():
    if request.method == 'OPTIONS':
        return _cors(jsonify({}))
    if not _check_token():
        return jsonify({'error': 'unauthorized'}), 403

    now = datetime.now(timezone.utc)
    default_start = now - timedelta(days=int(request.args.get('days', 30)))
    start_dt = _parse_ts(request.args.get('start'), default_start)
    end_dt = _parse_ts(request.args.get('end'), now)

    account_name = request.args.get('account', config.ACCOUNT_NAME)
    symbol = request.args.get('symbol', config.SYMBOL)

    start_ts_str = start_dt.strftime('%Y-%m-%d %H:%M:%S')
    end_ts_str = end_dt.strftime('%Y-%m-%d %H:%M:%S')

    # 1) Trades registrados en Postgres por el bot
    db_trades = db.get_trades_for_reconciliation(account_name, symbol,
                                                   start_ts_str, end_ts_str)

    # 2) Fills reales en Binance
    binance_orders = []
    binance_error = None
    if config.BINANCE_API_KEY and config.BINANCE_API_SECRET:
        try:
            reader = BinanceFuturesReader(config.BINANCE_API_KEY,
                                          config.BINANCE_API_SECRET,
                                          testnet=config.BINANCE_TESTNET)
            fills = reader.get_account_trades_paginated(symbol, _ms(start_dt), _ms(end_dt))
            binance_orders = _group_binance_fills_by_order(fills)
        except Exception as e:
            logger.error(f"Error consultando Binance: {e}", exc_info=True)
            binance_error = str(e)
    else:
        binance_error = "DASH_BINANCE_API_KEY / DASH_BINANCE_API_SECRET no configurados"

    # 3) Match: cada trade de Postgres = 2 órdenes en Binance (apertura y
    # cierre). La apertura matchea por order_id; el cierre se busca por
    # proximidad temporal a closed_at, side opuesto a la apertura, y qty
    # similar (dentro de 1%), entre las órdenes de Binance aún no usadas.
    binance_by_oid = {o['order_id']: o for o in binance_orders}
    used_oids = set()

    CLOSE_SIDE = {'BUY': 'SELL', 'SELL': 'BUY'}
    CLOSE_TOLERANCE = timedelta(minutes=10)
    QTY_TOLERANCE = 0.01  # 1%

    def _find_close_match(open_side, qty, closed_at_dt):
        if closed_at_dt is None:
            return None
        want_side = CLOSE_SIDE.get(open_side)
        best = None
        best_diff = None
        for oid, o in binance_by_oid.items():
            if oid in used_oids:
                continue
            if o['side'] != want_side:
                continue
            if qty and abs(o['qty'] - qty) / qty > QTY_TOLERANCE:
                continue
            o_time = datetime.strptime(o['time'], '%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc)
            diff = abs(o_time - closed_at_dt)
            if diff > CLOSE_TOLERANCE:
                continue
            if best is None or diff < best_diff:
                best, best_diff = oid, diff
        return best

    reconciled = []
    for t in db_trades:
        oid = str(t['order_id']) if t['order_id'] else None
        b_open = binance_by_oid.get(oid) if oid else None
        if b_open:
            used_oids.add(oid)

        closed_at_dt = None
        if t['closed_at']:
            closed_at_dt = datetime.strptime(t['closed_at'], '%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc)

        open_side_binance = 'BUY' if t['side'] == 'long' else 'SELL'
        close_oid = _find_close_match(open_side_binance, float(t['quantity']), closed_at_dt)
        b_close = binance_by_oid.get(close_oid) if close_oid else None
        if close_oid:
            used_oids.add(close_oid)

        reconciled.append({
            'db_trade_id': t['id'],
            'order_id': oid,
            'timestamp': _fmt_ts(t['timestamp']),
            'side': t['side'],
            'signal': t['signal'],
            'status': t['status'],
            'db_price': float(t['price']),
            'db_quantity': float(t['quantity']),
            'db_notional': float(t['notional']),
            'db_pnl_usdt': float(t['pnl_usdt']) if t['pnl_usdt'] is not None else None,
            'db_pnl_pct': float(t['pnl_pct']) if t['pnl_pct'] is not None else None,
            'closed_at': _fmt_ts(t['closed_at']),
            'close_signal': t['close_signal'],
            'binance_open': {
                'order_id': oid,
                'price': b_open['avg_price'],
                'quantity': b_open['qty'],
                'time': _fmt_ts(b_open['time']),
            } if b_open else None,
            'binance_close': {
                'order_id': close_oid,
                'price': b_close['avg_price'],
                'quantity': b_close['qty'],
                'realized_pnl': b_close['realized_pnl'],
                'commission': b_close['commission'] + (b_open['commission'] if b_open else 0),
                'time': _fmt_ts(b_close['time']),
            } if b_close else None,
        })

    # Órdenes que existen en Binance pero no se usaron como apertura ni cierre
    orphan_binance = [
        {
            'order_id': oid,
            'side': o['side'],
            'price': o['avg_price'],
            'quantity': o['qty'],
            'realized_pnl': o['realized_pnl'],
            'commission': o['commission'],
            'time': _fmt_ts(o['time']),
        }
        for oid, o in binance_by_oid.items() if oid not in used_oids
    ]

    matched_count = len([r for r in reconciled if r['binance_open'] and r['binance_close']])
    partial_count = len([r for r in reconciled
                          if (r['binance_open'] is None) != (r['binance_close'] is None)])
    unmatched_count = len([r for r in reconciled
                            if r['binance_open'] is None and r['binance_close'] is None])

    summary = {
        'db_trades_count': len(db_trades),
        'binance_orders_count': len(binance_orders),
        'matched_count': matched_count,
        'partial_count': partial_count,
        'unmatched_db_count': unmatched_count,
        'orphan_binance_count': len(orphan_binance),
    }

    return jsonify({
        'account': account_name,
        'symbol': symbol,
        'start': start_dt.isoformat(),
        'end': end_dt.isoformat(),
        'summary': summary,
        'trades': reconciled,
        'orphan_binance_orders': orphan_binance,
        'binance_error': binance_error,
    }), 200


# ── Curva de capital ──────────────────────────────────────────────────────
@app.route('/api/capital-curve', methods=['GET', 'OPTIONS'])
def capital_curve():
    if request.method == 'OPTIONS':
        return _cors(jsonify({}))
    if not _check_token():
        return jsonify({'error': 'unauthorized'}), 403

    now = datetime.now(timezone.utc)
    default_start = now - timedelta(days=int(request.args.get('days', 30)))
    start_dt = _parse_ts(request.args.get('start'), default_start)
    end_dt = _parse_ts(request.args.get('end'), now)

    account_name = request.args.get('account', config.ACCOUNT_NAME)

    start_ts_str = start_dt.strftime('%Y-%m-%d %H:%M:%S')
    end_ts_str = end_dt.strftime('%Y-%m-%d %H:%M:%S')

    capital_history = db.get_capital_curve_range(account_name, start_ts_str, end_ts_str)
    equity_snapshots = db.get_equity_snapshots_range(account_name, start_ts_str, end_ts_str)

    # Combinar y ordenar por timestamp -- capital_history tiene un punto por
    # trade, equity_snapshots tiene un punto por hora. Juntos dan la curva
    # completa de evolución del capital.
    points = []
    for r in capital_history:
        points.append({
            'timestamp': _fmt_ts(r['timestamp']),
            'total_equity': float(r['total_equity']),
            'balance_usdt': float(r['balance_usdt']),
            'unrealized_pnl': float(r['unrealized_pnl']),
            'drawdown_pct': float(r['drawdown_pct']),
            'peak_equity': float(r['peak_equity']),
            'source': 'trade',
            'trade_id': r['trade_id'],
        })
    for r in equity_snapshots:
        points.append({
            'timestamp': _fmt_ts(r['timestamp']),
            'total_equity': float(r['total_equity']),
            'balance_usdt': float(r['balance_usdt']),
            'unrealized_pnl': float(r['unrealized_pnl']),
            'drawdown_pct': float(r['drawdown_pct']),
            'peak_equity': float(r['peak_equity']),
            'source': 'hourly',
            'open_positions': r['open_positions'],
        })
    points.sort(key=lambda p: p['timestamp'])

    # Balance actual real desde Binance (si hay key configurada)
    live_balance = None
    binance_error = None
    if config.BINANCE_API_KEY and config.BINANCE_API_SECRET:
        try:
            reader = BinanceFuturesReader(config.BINANCE_API_KEY,
                                          config.BINANCE_API_SECRET,
                                          testnet=config.BINANCE_TESTNET)
            live_balance = reader.get_balance()
            pos = reader.get_position(config.SYMBOL)
            live_balance['position'] = pos
        except Exception as e:
            logger.error(f"Error consultando balance Binance: {e}", exc_info=True)
            binance_error = str(e)
    else:
        binance_error = "DASH_BINANCE_API_KEY / DASH_BINANCE_API_SECRET no configurados"

    return jsonify({
        'account': account_name,
        'start': start_dt.isoformat(),
        'end': end_dt.isoformat(),
        'points': points,
        'live_balance': live_balance,
        'binance_error': binance_error,
    }), 200


@app.route('/api/health', methods=['GET'])
def health():
    return jsonify({'status': 'up', 'account': config.ACCOUNT_NAME,
                     'symbol': config.SYMBOL}), 200


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)

