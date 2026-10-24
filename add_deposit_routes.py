from pathlib import Path

p = Path("app.py")
s = p.read_text()
marker = '@app.route("/logout")'

if 'def deposit_instructions(' in s:
    print("Deposit routes already exist.")
    raise SystemExit

routes = '''

@app.route("/deposit", methods=["GET", "POST"])
def deposit():
    import json, time
    from urllib.request import Request, urlopen
    if "uid" not in session:
        return redirect(url_for("login"))
    if request.method == "POST":
        network = request.form.get("network", "").upper()
        phone = request.form.get("sender_phone", "").strip()
        try:
            amount = float(request.form.get("amount_ugx", ""))
        except (ValueError, TypeError):
            amount = 0
        if network not in ("MTN", "AIRTEL"):
            flash("Choose MTN or Airtel.", "error")
            return redirect(url_for("deposit"))
        if not phone or len(phone) < 9 or len(phone) > 16 or not 1000 <= amount <= 10000000:
            flash("Check the phone number and amount.", "error")
            return redirect(url_for("deposit"))
        try:
            req = Request("https://open.er-api.com/v6/latest/USD",
                          headers={"User-Agent": "SpaceXPlatform/1.0"})
            with urlopen(req, timeout=8) as r:
                data = json.loads(r.read().decode())
            rate = float(data["rates"]["UGX"])
            if data.get("result") != "success" or rate <= 0:
                raise ValueError("Rate unavailable")
        except Exception:
            flash("Exchange rate unavailable. Try again.", "error")
            return redirect(url_for("deposit"))
        with db() as c:
            cur = c.execute("""
                INSERT INTO deposit_requests
                (user_id,network,sender_phone,requested_ugx,exchange_rate,
                 requested_usd,status,created_at)
                VALUES (?,?,?,?,?,?,'pending',?)
            """, (session["uid"],network,phone,amount,rate,round(amount/rate,2),time.time()))
            did = cur.lastrowid
        return redirect(url_for("deposit_instructions", deposit_id=did))
    return render_template("deposit.html")


@app.route("/deposit/<int:deposit_id>", methods=["GET", "POST"])
def deposit_instructions(deposit_id):
    import time
    if "uid" not in session:
        return redirect(url_for("login"))
    with db() as c:
        row = c.execute(
            "SELECT * FROM deposit_requests WHERE id=? AND user_id=?",
            (deposit_id,session["uid"])).fetchone()
    if not row:
        flash("Deposit request not found.", "error")
        return redirect(url_for("deposit"))
    now = time.time()
    can_submit = row["created_at"]+60 <= now <= row["created_at"]+1800
    if request.method == "POST":
        if row["status"] != "pending" or row["transaction_id"]:
            flash("This request has already been submitted.", "error")
            return redirect(url_for("deposit_instructions",deposit_id=deposit_id))
        if not can_submit:
            flash("Submission window is closed.", "error")
            return redirect(url_for("deposit_instructions",deposit_id=deposit_id))
        tx = request.form.get("transaction_id","").strip()
        phone = request.form.get("paid_phone","").strip()
        try:
            paid = float(request.form.get("paid_ugx",""))
        except (ValueError,TypeError):
            paid = 0
        if not tx or len(tx)>100 or not phone or len(phone)<9 or len(phone)>16 or not 1000<=paid<=10000000:
            flash("Check the transaction ID, amount and paying number.", "error")
            return redirect(url_for("deposit_instructions",deposit_id=deposit_id))
        try:
            with db() as c:
                result = c.execute("""
                    UPDATE deposit_requests SET transaction_id=?,paid_ugx=?,
                    paid_phone=?,submitted_at=?
                    WHERE id=? AND user_id=? AND transaction_id IS NULL
                    AND status='pending'
                """,(tx,paid,phone,now,deposit_id,session["uid"]))
                if result.rowcount != 1:
                    raise ValueError("Request already submitted")
        except sqlite3.IntegrityError:
            flash("That transaction ID has already been used.", "error")
            return redirect(url_for("deposit_instructions",deposit_id=deposit_id))
        except ValueError:
            flash("This request has already been submitted.", "error")
            return redirect(url_for("deposit_instructions",deposit_id=deposit_id))
        flash("Payment details submitted and pending verification.", "success")
        return redirect(url_for("transactions"))
    return render_template("deposit_instructions.html",
        deposit=dict(row), can_submit=can_submit)

'''

if marker not in s:
    raise SystemExit("Logout route not found; app.py unchanged.")
p.write_text(s.replace(marker, routes + marker, 1))
print("Deposit routes installed.")
