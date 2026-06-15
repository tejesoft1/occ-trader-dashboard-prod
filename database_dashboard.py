import psycopg2
import psycopg2.extras
import config_dashboard as config


def get_conn():
    # El usuario DASH_DB_USER (occ_reader) debe tener permisos SELECT
    # únicamente -- ver create_readonly_user.sql. Si por error se intenta
    # un INSERT/UPDATE desde este módulo, Postgres lo rechazará.
    return psycopg2.connect(
        host=config.DB_HOST, port=config.DB_PORT, dbname=config.DB_NAME,
        user=config.DB_USER, password=config.DB_PASSWORD,
    )


def _cur(conn):
    return conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)


def get_trades_for_reconciliation(account_name, symbol, start_ts=None, end_ts=None):
    """
    Trades (abiertos y cerrados) de una cuenta/símbolo, con order_id, para
    matchear contra el historial de fills de Binance. start_ts/end_ts son
    strings 'YYYY-MM-DD HH:MM:SS' UTC.
    """
    conn = get_conn(); c = _cur(conn)
    query = '''
        SELECT id, timestamp, symbol, side, signal, price, quantity,
               notional, leverage, order_id, status, pnl_usdt, pnl_pct,
               closed_at, close_signal
        FROM trades
        WHERE account_name=%s AND symbol=%s
    '''
    params = [account_name, symbol]
    if start_ts:
        query += ' AND timestamp >= %s'
        params.append(start_ts)
    if end_ts:
        query += ' AND timestamp <= %s'
        params.append(end_ts)
    query += ' ORDER BY id ASC'
    c.execute(query, params)
    rows = [dict(r) for r in c.fetchall()]
    c.close(); conn.close()
    return rows


def get_capital_curve_range(account_name, start_ts=None, end_ts=None):
    """
    Curva de capital (capital_history) de una cuenta, opcionalmente
    acotada por rango de tiempo.
    """
    conn = get_conn(); c = _cur(conn)
    query = '''
        SELECT timestamp, balance_usdt, unrealized_pnl, total_equity,
               drawdown_pct, peak_equity, trade_id
        FROM capital_history WHERE account_name=%s
    '''
    params = [account_name]
    if start_ts:
        query += ' AND timestamp >= %s'
        params.append(start_ts)
    if end_ts:
        query += ' AND timestamp <= %s'
        params.append(end_ts)
    query += ' ORDER BY id ASC'
    c.execute(query, params)
    rows = [dict(r) for r in c.fetchall()]
    c.close(); conn.close()
    return rows


def get_equity_snapshots_range(account_name, start_ts=None, end_ts=None):
    """Snapshots horarios (equity_snapshots), para complementar la curva
    de capital_history con puntos aunque no haya habido trades."""
    conn = get_conn(); c = _cur(conn)
    query = '''
        SELECT timestamp, balance_usdt, unrealized_pnl, total_equity,
               open_positions, drawdown_pct, peak_equity
        FROM equity_snapshots WHERE account_name=%s
    '''
    params = [account_name]
    if start_ts:
        query += ' AND timestamp >= %s'
        params.append(start_ts)
    if end_ts:
        query += ' AND timestamp <= %s'
        params.append(end_ts)
    query += ' ORDER BY id ASC'
    c.execute(query, params)
    rows = [dict(r) for r in c.fetchall()]
    c.close(); conn.close()
    return rows
