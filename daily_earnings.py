import os
import sqlite3
from datetime import date, datetime
from machine_catalog import MACHINE_CATALOG

DB = os.environ.get("DATABASE_PATH", "space_x.db")

def run():
    today = date.today()
    credited = 0

    con = sqlite3.connect(DB, timeout=30)
    con.row_factory = sqlite3.Row

    try:
        con.execute("BEGIN IMMEDIATE")
        purchases = con.execute("""
            SELECT id, user_id, machine_code, purchased_at
            FROM machine_purchases
            WHERE status='successful'
        """).fetchall()

        for p in purchases:
            item = MACHINE_CATALOG.get(p["machine_code"])
            if not item:
                continue

            _, duration, _, daily, _ = item

            try:
                purchased = datetime.fromisoformat(
                    str(p["purchased_at"]).replace("Z", "+00:00")
                ).date()
            except (ValueError, TypeError):
                continue

            eligible_days = min(
                duration, max(0, (today - purchased).days + 1)
            )

            for day in range(1, eligible_days + 1):
                cur = con.execute("""
                    INSERT OR IGNORE INTO machine_earnings
                    (purchase_id, user_id, earning_day, amount_usd)
                    VALUES (?, ?, ?, ?)
                """, (p["id"], p["user_id"], day, daily))

                if cur.rowcount == 1:
                    con.execute("""
                        UPDATE users SET balance = balance + ?
                        WHERE id = ?
                    """, (daily, p["user_id"]))
                    credited += 1

        con.commit()
        print(f"Daily earnings complete. New daily credits: {credited}")
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()

if __name__ == "__main__":
    run()
