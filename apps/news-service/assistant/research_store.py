"""SQLite storage for local watchlists and price alerts."""

import time

from .db import get_connection


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def list_watchlist():
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, symbol, name, asset_type, note, created_at "
            "FROM watchlist ORDER BY id DESC"
        ).fetchall()
    return [dict(row) for row in rows]


def save_watch(symbol, name="", asset_type="stock", note=""):
    symbol = str(symbol or "").strip()
    if not symbol:
        raise ValueError("symbol 不能为空")
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO watchlist(symbol, name, asset_type, note, created_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(symbol) DO UPDATE SET
              name=excluded.name, asset_type=excluded.asset_type, note=excluded.note
            """,
            (symbol, str(name or "").strip(), str(asset_type or "stock"), str(note or ""), _now()),
        )


def delete_watch(watch_id):
    with get_connection() as conn:
        conn.execute("DELETE FROM watchlist WHERE id=?", (int(watch_id),))


def list_alerts():
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, symbol, name, condition, threshold, enabled, triggered_at, created_at "
            "FROM price_alerts ORDER BY id DESC"
        ).fetchall()
    return [dict(row) for row in rows]


def save_alert(symbol, name, condition, threshold):
    condition = str(condition or "").strip().lower()
    if condition not in {"above", "below"}:
        raise ValueError("condition 必须是 above 或 below")
    threshold = float(threshold)
    with get_connection() as conn:
        cur = conn.execute(
            """
            INSERT INTO price_alerts(symbol, name, condition, threshold, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (str(symbol).strip(), str(name or "").strip(), condition, threshold, _now()),
        )
        return cur.lastrowid


def delete_alert(alert_id):
    with get_connection() as conn:
        conn.execute("DELETE FROM price_alerts WHERE id=?", (int(alert_id),))


def mark_alert_triggered(alert_id):
    with get_connection() as conn:
        conn.execute(
            "UPDATE price_alerts SET triggered_at=?, enabled=0 WHERE id=?",
            (_now(), int(alert_id)),
        )
