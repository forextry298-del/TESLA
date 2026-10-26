import os
import sqlite3
from datetime import date, datetime
from machine_catalog import MACHINE_CATALOG

DB = os.environ.get("DATABASE_PATH", "tesla.db")

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


def run_vip():
    from zoneinfo import ZoneInfo
    from datetime import datetime
    con = sqlite3.connect(DB, timeout=30)
    con.row_factory = sqlite3.Row
    credited = 0
    today = datetime.now(ZoneInfo("Africa/Kampala")).date().isoformat()
    try:
        con.execute("BEGIN IMMEDIATE")
        con.execute("""
            CREATE TABLE IF NOT EXISTS vip_daily_earnings (
                purchase_id INTEGER NOT NULL,
                earning_date TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                amount REAL NOT NULL,
                PRIMARY KEY (purchase_id, earning_date)
            )
        """)
        products = {
            1: 5000, 2: 13000, 3: 32400, 4: 70000,
            5: 145000, 6: 300000, 7: 775000, 8: 2000000
        }
        rows = con.execute("""
            SELECT id, user_id, product_id, purchased_at, term_days, status
            FROM purchases
        """).fetchall()
        for r in rows:
            daily = products.get(r["product_id"])
            if not daily or (r["status"] or "").lower() not in ("active", "successful", "approved"):
                continue
            try:
                start = datetime.fromisoformat(
                    str(r["purchased_at"]).replace("Z", "+00:00")
                ).date()
            except (ValueError, TypeError):
                continue
            day_num = (datetime.fromisoformat(today).date() - start).days + 1
            if day_num < 1 or day_num > (r["term_days"] or 360):
                continue
            cur = con.execute("""
                INSERT OR IGNORE INTO vip_daily_earnings
                (purchase_id, earning_date, user_id, amount)
                VALUES (?, ?, ?, ?)
            """, (r["id"], today, r["user_id"], daily))
            if cur.rowcount == 1:
                con.execute(
                    "UPDATE users SET balance=balance+? WHERE id=?",
                    (daily, r["user_id"])
                )
                credited += 1
        con.commit()
        print(f"VIP daily earnings complete: {credited} credits.")
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "vip":
        run_vip()
    else:
        run()
