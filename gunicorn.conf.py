import threading
import time
from datetime import datetime
from zoneinfo import ZoneInfo

def post_worker_init(worker):
    def earnings_loop():
        kampala = ZoneInfo("Africa/Kampala")
        last_run_date = None

        while True:
            now = datetime.now(kampala)
            today = now.date().isoformat()

            if today != last_run_date:
                try:
                    from daily_earnings import run_vip
                    run_vip()
                    last_run_date = today
                    worker.log.info(
                        "TESLA daily VIP earnings completed for %s", today
                    )
                except Exception:
                    worker.log.exception("TESLA daily VIP earnings failed")

            time.sleep(30)

    threading.Thread(
        target=earnings_loop,
        daemon=True,
        name="tesla-vip-earnings"
    ).start()
