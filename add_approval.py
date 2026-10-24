from pathlib import Path
p = Path("app.py")
s = p.read_text()

if "def admin_deposits():" in s:
    print("Approval route already exists.")
    raise SystemExit

marker = '@app.route("/invite")'
assert marker in s, "Could not find insertion point"

code = '''
@app.route("/admin/deposits", methods=["GET", "POST"])
def admin_deposits():
    import time
    if not session.get("space_x_admin"):
        return redirect(url_for("admin_login"))

    if request.method == "POST":
        try:
            did = int(request.form.get("deposit_id", ""))
        except ValueError:
            flash("Invalid deposit ID.", "error")
            return redirect(url_for("admin_deposits"))

        action = request.form.get("action")
        with db() as c:
            d = c.execute("""SELECT * FROM deposit_requests
                WHERE id=? AND status='pending'
                AND transaction_id IS NOT NULL AND paid_ugx IS NOT NULL""",
                (did,)).fetchone()
            if not d:
                flash("Deposit missing or already reviewed.", "error")
                return redirect(url_for("admin_deposits"))

            if action == "reject":
                c.execute("""UPDATE deposit_requests
                    SET status='rejected', reviewed_at=?
                    WHERE id=? AND status='pending'""", (time.time(), did))
                flash("Deposit rejected.", "success")
                return redirect(url_for("admin_deposits"))

            if action != "approve" or d["paid_ugx"] <= 0 or d["exchange_rate"] <= 0:
                flash("Invalid action or amount.", "error")
                return redirect(url_for("admin_deposits"))

            changed = c.execute("""UPDATE deposit_requests
                SET status='approved', reviewed_at=?
                WHERE id=? AND status='pending'""",
                (time.time(), did)).rowcount
            if changed != 1:
                flash("Deposit already reviewed.", "error")
                return redirect(url_for("admin_deposits"))

            usd = round(d["paid_ugx"] / d["exchange_rate"], 3)
            row = c.execute("SELECT referred_by FROM users WHERE id=?",
                            (d["user_id"],)).fetchone()
            uid = row["referred_by"] if row else None

            for level, rate in ((1, .10), (2, .05), (3, .01)):
                if not uid:
                    break
                amount = round(usd * rate, 3)
                if amount > 0:
                    ins = c.execute("""INSERT OR IGNORE INTO referral_commissions
                        (deposit_id, beneficiary_user_id, referral_level,
                         amount_usd, created_at) VALUES (?, ?, ?, ?, ?)""",
                        (did, uid, level, amount, time.time()))
                    if ins.rowcount == 1:
                        c.execute("""UPDATE users SET balance=
                            ROUND(COALESCE(balance,0)+?,3) WHERE id=?""",
                            (amount, uid))
                parent = c.execute("SELECT referred_by FROM users WHERE id=?",
                                    (uid,)).fetchone()
                uid = parent["referred_by"] if parent else None

        flash("Deposit approved; eligible commissions credited automatically.", "success")
        return redirect(url_for("admin_deposits"))

    with db() as c:
        rows = c.execute("""SELECT d.*, u.phone AS user_phone
            FROM deposit_requests d JOIN users u ON u.id=d.user_id
            WHERE d.status='pending' AND d.transaction_id IS NOT NULL
            ORDER BY d.created_at""").fetchall()

    return render_template_string("""
    <h2>Deposit approvals</h2>
    <p>Verify each transaction with the mobile-money provider first.</p>
    {% for d in rows %}
      <hr><p>#{{ d.id }} | {{ d.user_phone }} | {{ d.network }}</p>
      <p>Transaction: {{ d.transaction_id }} | UGX {{ d.paid_ugx }}</p>
      <form method="post">
        <input type="hidden" name="deposit_id" value="{{ d.id }}">
        <button name="action" value="approve">Approve and credit commissions</button>
        <button name="action" value="reject">Reject</button>
      </form>
    {% else %}<p>No submitted deposits awaiting review.</p>{% endfor %}
    """, rows=rows)


@app.route("/admin/logout")
def admin_logout():
    session.pop("space_x_admin", None)
    return redirect(url_for("admin_login"))


'''

if "render_template_string" not in s:
    s = s.replace("render_template, request, redirect",
                  "render_template, render_template_string, request, redirect", 1)

p.write_text(s.replace(marker, code + marker, 1))
print("Approval route added.")
