from flask import Flask, render_template, request, redirect, url_for, session, flash
import sqlite3, os, secrets
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps

app = Flask(__name__)
app.secret_key = os.environ.get("TESLA_SECRET", secrets.token_hex(32))
DB = os.path.join(os.path.dirname(__file__), "tesla.db")

def connect():
    db = sqlite3.connect(DB)
    db.row_factory = sqlite3.Row
    return db

def init_db():
    with connect() as db:
        db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phone TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            invite_code TEXT UNIQUE NOT NULL,
            balance REAL NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_blocked INTEGER NOT NULL DEFAULT 0
        )""")

        columns = {
            row["name"] for row in db.execute("PRAGMA table_info(users)")
        }
        if "is_blocked" not in columns:
            db.execute(
                "ALTER TABLE users ADD COLUMN is_blocked INTEGER NOT NULL DEFAULT 0"
            )

def login_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        uid = session.get("user_id")
        if not uid:
            return redirect(url_for("login"))
        with connect() as db:
            user = db.execute(
                "SELECT is_blocked FROM users WHERE id=?", (uid,)
            ).fetchone()
        if not user or user["is_blocked"]:
            session.clear()
            flash("Your account is unavailable. Please contact support.")
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapped

@app.route("/")
def index():
    if session.get("user_id"):
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        phone = request.form.get("phone", "").strip()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm", "")
        invitation = request.form.get("invitation", "").strip()

        if not phone or not password:
            flash("Enter your phone number and password.")
        elif len(password) < 8:
            flash("Use a password of at least 8 characters.")
        elif password != confirm:
            flash("The passwords do not match.")
        else:
            with connect() as db:
                inviter = None
                if invitation:
                    inviter = db.execute(
                        "SELECT id FROM users WHERE invite_code=?",
                        (invitation,)
                    ).fetchone()
                    if not inviter:
                        flash("Invitation code not found.")
                        return render_template("register.html")

                code = secrets.token_urlsafe(6)[:8]
                try:
                    cur = db.execute(
                        "INSERT INTO users(phone,password,invite_code,balance,invited_by) VALUES(?,?,?,?,?)",
                        (phone, generate_password_hash(password), code, 8000,
                         inviter["id"] if inviter else None)
                    )
                    session["user_id"] = cur.lastrowid
                    flash("Welcome to TESLA! UGX 8,000 welcome bonus credited to your account.")
                    return redirect(url_for("dashboard"))
                except sqlite3.IntegrityError:
                    flash("That phone number is already registered.")
    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        phone = request.form.get("phone", "").strip()
        password = request.form.get("password", "")
        with connect() as db:
            user = db.execute(
                "SELECT * FROM users WHERE phone=?", (phone,)
            ).fetchone()
        if user and check_password_hash(user["password"], password):
            if user["is_blocked"]:
                flash("Your account is blocked. Please contact support.")
                return render_template("login.html")
            session.clear()
            session["user_id"] = user["id"]
            return redirect(url_for("dashboard"))
        flash("Incorrect phone number or password.")
    return render_template("login.html")

@app.route("/dashboard")
@login_required
def dashboard():
    with connect() as db:
        user = db.execute(
            "SELECT * FROM users WHERE id=?", (session["user_id"],)
        ).fetchone()
    if not user:
        session.clear()
        return redirect(url_for("login"))
    return render_template("dashboard.html", user=user)




@app.route("/team")
@login_required
def team():
    with connect() as db:
        user = db.execute(
            "SELECT * FROM users WHERE id=?", (session["user_id"],)
        ).fetchone()

        members = db.execute("""
            SELECT phone, created_at, id
            FROM users WHERE invited_by=?
            ORDER BY id DESC
        """, (session["user_id"],)).fetchall()

        level2_count = 0
        level3_count = 0

        for member in members:
            level2_count += db.execute(
                "SELECT COUNT(*) FROM users WHERE invited_by=?",
                (member["id"],)
            ).fetchone()[0]

        for member in members:
            children = db.execute(
                "SELECT id FROM users WHERE invited_by=?",
                (member["id"],)
            ).fetchall()
            for child in children:
                level3_count += db.execute(
                    "SELECT COUNT(*) FROM users WHERE invited_by=?",
                    (child["id"],)
                ).fetchone()[0]

    return render_template(
        "team.html", user=user, members=members,
        level2_count=level2_count, level3_count=level3_count
    )


@app.route("/invite")
@login_required
def invite():
    with connect() as db:
        user = db.execute(
            "SELECT * FROM users WHERE id=?", (session["user_id"],)
        ).fetchone()
        if not user:
            session.clear()
            return redirect(url_for("login"))

        team_count = db.execute(
            "SELECT COUNT(*) FROM users WHERE invited_by=?",
            (user["id"],)
        ).fetchone()[0]

    referral_code = user["invite_code"]
    referral_link = request.url_root.rstrip("/") + url_for(
        "register"
    ) + "?invitation=" + referral_code

    return render_template(
        "invite.html",
        referral_code=referral_code,
        referral_link=referral_link,
        team_count=team_count
    )


@app.route("/my-team")
@login_required
def my_team():
    return redirect(url_for("team"))


@app.route("/about")
@login_required
def about_us():
    return render_template("about.html")

@app.route("/profile")
@login_required
def profile():
    with connect() as db:
        user = db.execute(
            "SELECT * FROM users WHERE id=?", (session["user_id"],)
        ).fetchone()
        if not user:
            session.clear()
            return redirect(url_for("login"))
        invite_count = db.execute(
            "SELECT COUNT(*) FROM users WHERE invited_by=?",
            (user["id"],)
        ).fetchone()[0]
    return render_template(
        "profile.html",
        user=user,
        balance=user["balance"] if "balance" in user.keys() else 0,
        wallet=user["balance"] if "balance" in user.keys() else 0,
        invite_count=invite_count,
        team_count=invite_count,
        deposit_total=0,
        withdrawal_total=0,
        ai_income=0,
        today_income=0,
        team_income=0,
        last_salary=0,
        this_salary=0,
        invited_last=0,
        invited_this=0
    )

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

init_db()

# Keep referral relationships for existing and new users.
with connect() as db:
    user_columns = [row["name"] for row in db.execute("PRAGMA table_info(users)")]
    if "invited_by" not in user_columns:
        db.execute("ALTER TABLE users ADD COLUMN invited_by INTEGER")


def init_transactions_db():
    with connect() as db:
        db.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            kind TEXT NOT NULL CHECK(kind IN ('deposit','withdrawal')),
            amount REAL NOT NULL CHECK(amount > 0),
            method TEXT NOT NULL,
            reference TEXT DEFAULT '',
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )""")

init_transactions_db()


def init_task_rewards_db():
    with connect() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS task_rewards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                task_code TEXT NOT NULL,
                amount REAL NOT NULL CHECK(amount > 0),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, task_code),
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
        """)

init_task_rewards_db()

@app.route("/vip-tasks")
@login_required
def vip_tasks():
    user_id = session["user_id"]

    with connect() as db:
        user = db.execute(
            "SELECT id, invite_code FROM users WHERE id=?", (user_id,)
        ).fetchone()

        if not user:
            session.clear()
            return redirect(url_for("login"))

        qualified_count = db.execute("""
            SELECT COUNT(*)
            FROM users invited
            WHERE invited.invited_by=?
              AND EXISTS (
                  SELECT 1 FROM transactions t
                  WHERE t.user_id=invited.id
                    AND t.kind='deposit'
                    AND t.status='approved'
                    AND t.amount >= 20000
              )
        """, (user_id,)).fetchone()[0]

        reward_total = db.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM task_rewards WHERE user_id=?",
            (user_id,)
        ).fetchone()[0]

        claimed_codes = {
            row["task_code"] for row in db.execute(
                "SELECT task_code FROM task_rewards WHERE user_id=?",
                (user_id,)
            ).fetchall()
        }

    referral_code = user["invite_code"]
    referral_link = request.url_root.rstrip("/") + url_for(
        "register"
    ) + "?invitation=" + referral_code

    return render_template(
        "vip_tasks.html",
        qualified_count=qualified_count,
        reward_total=reward_total,
        reward_rate=0,
        referral_code=referral_code,
        referral_link=referral_link,
        target=3,
        reward_amount=5000,
        reward_claimed="LV1_INVITE_3" in claimed_codes,
        claimed_codes=claimed_codes
    )

@app.route("/transactions")
@login_required
def transactions():
    with connect() as db:
        rows = db.execute("""
            SELECT kind, amount, method, reference, status, created_at
            FROM transactions
            WHERE user_id=?
            ORDER BY id DESC
        """, (session["user_id"],)).fetchall()
    return render_template("transactions.html", transactions=rows)

@app.route("/deposit", methods=["GET", "POST"])
@login_required
def deposit():
    if request.method == "POST":
        try:
            amount = float(request.form.get("amount", "0"))
        except (TypeError, ValueError):
            amount = 0

        method = request.form.get("method", "").strip()
        reference = request.form.get("reference", "").strip()

        if not 20000 <= amount <= 5000000:
            flash("Minimum deposit is UGX 20,000. Maximum deposit is UGX 5,000,000.")
        elif method not in ("MTN Mobile Money", "Airtel Money"):
            flash("Select MTN Mobile Money or Airtel Money.")
        elif not reference or len(reference) > 100:
            flash("Enter a valid payment reference.")
        else:
            with connect() as db:
                cursor = db.execute("""
                    INSERT INTO transactions
                    (user_id, kind, amount, method, reference, status)
                    VALUES (?, 'deposit', ?, ?, ?, 'pending')
                """, (session["user_id"], amount, method, reference))
                deposit_id = cursor.lastrowid
            return redirect(url_for(
                "deposit_instructions", transaction_id=deposit_id
            ))

    return render_template("deposit.html")


@app.route("/deposit/instructions/<int:transaction_id>")
@login_required
def deposit_instructions(transaction_id):
    with connect() as db:
        deposit = db.execute("""
            SELECT id, amount, method, reference, status
            FROM transactions
            WHERE id=? AND user_id=? AND kind='deposit'
        """, (transaction_id, session["user_id"])).fetchone()

    if deposit is None:
        flash("Deposit request not found.")
        return redirect(url_for("deposit"))

    return render_template("deposit_instructions.html", deposit=deposit)

@app.route("/withdraw", methods=["GET", "POST"])
@login_required
def withdraw():
    if request.method == "POST":
        try:
            amount = float(request.form.get("amount", "0"))
        except ValueError:
            amount = 0

        method = request.form.get("method", "").strip()
        reference = request.form.get("reference", "").strip()

        if not 1000 <= amount <= 5000000:
            flash("Enter a withdrawal amount between UGX 1,000 and UGX 5,000,000.")
        elif method not in ("MTN Mobile Money", "Airtel Money", "Bank"):
            flash("Select a valid payout method.")
        else:
            with connect() as db:
                user = db.execute(
                    "SELECT balance FROM users WHERE id=?",
                    (session["user_id"],)
                ).fetchone()
                pending = db.execute("""
                    SELECT COALESCE(SUM(amount), 0) AS total
                    FROM transactions
                    WHERE user_id=? AND kind='withdrawal' AND status='pending'
                """, (session["user_id"],)).fetchone()["total"]

                if not user or amount > user["balance"] - pending:
                    flash("Insufficient available balance for this request.")
                else:
                    db.execute("""
                        INSERT INTO transactions
                        (user_id, kind, amount, method, reference)
                        VALUES (?, 'withdrawal', ?, ?, ?)
                    """, (session["user_id"], amount, method, reference))
                    flash("Withdrawal request submitted for review.")
                    return redirect(url_for("dashboard"))

    return render_template("transaction.html", kind="withdrawal")


PRODUCTS = [
    {"id": 1, "name": "TESLA VIP1 Virtuix Omni VR", "price": 20000, "term": 360, "daily_income": 5000, "total_income": 1800000},
    {"id": 2, "name": "TESLA VIP2 Virtuix Omni VR", "price": 50000, "term": 360, "daily_income": 13000, "total_income": 4680000},
    {"id": 3, "name": "TESLA VIP3 Virtuix Omni VR", "price": 120000, "term": 360, "daily_income": 32400, "total_income": 11664000},
    {"id": 4, "name": "TESLA VIP4 Virtuix Omni VR", "price": 250000, "term": 360, "daily_income": 70000, "total_income": 25200000},
    {"id": 5, "name": "TESLA VIP5 Virtuix Omni VR", "price": 500000, "term": 360, "daily_income": 145000, "total_income": 52200000},
    {"id": 6, "name": "TESLA VIP6 Virtuix Omni VR", "price": 1000000, "term": 360, "daily_income": 300000, "total_income": 108000000},
    {"id": 7, "name": "TESLA VIP7 Virtuix Omni VR", "price": 2500000, "term": 360, "daily_income": 775000, "total_income": 279000000},
    {"id": 8, "name": "TESLA VIP8 Virtuix Omni VR", "price": 5000000, "term": 360, "daily_income": 2000000, "total_income": 720000000},
]

def init_product_tables():
    with connect() as db:
        db.execute("""
        CREATE TABLE IF NOT EXISTS purchases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            product_name TEXT NOT NULL,
            amount REAL NOT NULL,
            term_days INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            purchased_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )""")

init_product_tables()


def award_team_milestones(db, purchaser_id):
    """Update each ancestor's team investment milestones once per reward."""
    current = purchaser_id
    visited = set()
    while current and current not in visited:
        visited.add(current)
        row = db.execute(
            "SELECT invited_by FROM users WHERE id=?", (current,)
        ).fetchone()
        if not row or not row["invited_by"]:
            break
        inviter_id = row["invited_by"]

        total = db.execute("""
            WITH RECURSIVE downline(id) AS (
                SELECT id FROM users WHERE invited_by=?
                UNION
                SELECT u.id FROM users u JOIN downline d ON u.invited_by=d.id
            )
            SELECT COALESCE(SUM(p.amount), 0)
            FROM purchases p JOIN downline d ON d.id=p.user_id
            WHERE p.status='active'
        """, (inviter_id,)).fetchone()[0]

        for target, code, amount in [
            (2000000, "LV1_TEAM_2000000", 20000),
            (7000000, "LV1_TEAM_7000000", 70000),
            (15000000, "LV1_TEAM_15000000", 150000),
            (40000000, "LV1_TEAM_40000000", 400000),
        ]:
            if total >= target:
                cur = db.execute("""
                    INSERT OR IGNORE INTO task_rewards(user_id, task_code, amount)
                    VALUES (?, ?, ?)
                """, (inviter_id, code, amount))
                if cur.rowcount == 1:
                    db.execute(
                        "UPDATE users SET balance=balance+? WHERE id=?",
                        (amount, inviter_id)
                    )
        current = inviter_id

@app.route("/products")
@login_required
def products():
    with connect() as db:
        user = db.execute(
            "SELECT * FROM users WHERE id=?", (session["user_id"],)
        ).fetchone()
        counts = db.execute("""
            SELECT product_id, COUNT(*) AS total
            FROM purchases WHERE user_id=?
            GROUP BY product_id
        """, (session["user_id"],)).fetchall()
    owned = {r["product_id"]: r["total"] for r in counts}
    return render_template("products.html", products=PRODUCTS,
                           user=user, owned=owned)

@app.route("/invest/<int:product_id>", methods=["GET", "POST"])
@login_required
def invest(product_id):
    product = next((x for x in PRODUCTS if x["id"] == product_id), None)
    if product is None:
        flash("Product not found.")
        return redirect(url_for("products"))

    if request.method == "POST":
        if request.form.get("confirm") != "yes":
            return redirect(url_for("products"))

        db = connect()
        try:
            db.execute("BEGIN IMMEDIATE")
            user = db.execute(
                "SELECT balance FROM users WHERE id=?",
                (session["user_id"],)
            ).fetchone()

            if user is None:
                db.rollback()
                flash("Account not found. Please log in again.")
                return redirect(url_for("login"))

            if user["balance"] < product["price"]:
                db.rollback()
                flash("Insufficient funds. Please deposit enough UGX first.")
                return redirect(url_for("deposit"))

            db.execute(
                "UPDATE users SET balance=balance-? WHERE id=?",
                (product["price"], session["user_id"])
            )
            db.execute("""
                INSERT INTO purchases
                (user_id, product_id, product_name, amount, term_days)
                VALUES (?, ?, ?, ?, ?)
            """, (session["user_id"], product["id"], product["name"],
                  product["price"], product["term"]))

            purchase_rewards = {
                4: 2500, 5: 5000, 6: 10000,
                7: 25000, 8: 50000
            }
            reward = purchase_rewards.get(product["id"])
            if reward:
                code = "LV1_BUY_VIP" + str(product["id"])
                cur = db.execute("""
                    INSERT OR IGNORE INTO task_rewards
                    (user_id, task_code, amount)
                    VALUES (?, ?, ?)
                """, (session["user_id"], code, reward))
                if cur.rowcount == 1:
                    db.execute(
                        "UPDATE users SET balance=balance+? WHERE id=?",
                        (reward, session["user_id"])
                    )
            award_team_milestones(db, session["user_id"])
            db.commit()
            flash("Purchase recorded successfully.")
            return redirect(url_for("my_products"))
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    with connect() as db:
        user = db.execute(
            "SELECT * FROM users WHERE id=?", (session["user_id"],)
        ).fetchone()
    return render_template("invest_confirm.html", product=product, user=user)

@app.route("/my-products")
@login_required
def my_products():
    with connect() as db:
        user = db.execute(
            "SELECT * FROM users WHERE id=?", (session["user_id"],)
        ).fetchone()
        purchases = db.execute("""
            SELECT * FROM purchases WHERE user_id=?
            ORDER BY id DESC
        """, (session["user_id"],)).fetchall()
    return render_template("my_products.html", user=user,
                           purchases=purchases)




ADMIN_PHONE = "0758878297"

def admin_required(fn):
    @wraps(fn)
    @login_required
    def wrapped(*args, **kwargs):
        with connect() as db:
            user = db.execute(
                "SELECT phone FROM users WHERE id=?",
                (session["user_id"],)
            ).fetchone()
        if not user or user["phone"] != ADMIN_PHONE:
            flash("You are not authorized to access the admin panel.")
            return redirect(url_for("dashboard"))
        return fn(*args, **kwargs)
    return wrapped

@app.route("/admin")
@admin_required
def admin_home():
    return render_template("admin_home.html")


@app.route("/admin/deposits")
@admin_required
def admin_deposits():
    with connect() as db:
        deposits = db.execute("""
            SELECT t.id, t.user_id, t.amount, t.method, t.reference,
                   t.status, t.created_at, u.phone
            FROM transactions t
            JOIN users u ON u.id=t.user_id
            WHERE t.kind='deposit'
            ORDER BY CASE WHEN t.status='pending' THEN 0 ELSE 1 END, t.id DESC
        """).fetchall()
    return render_template("admin_deposits.html", deposits=deposits)


@app.route("/admin/deposits/<int:transaction_id>/approve", methods=["POST"])
@admin_required
def admin_approve_deposit(transaction_id):
    db = connect()
    reward_paid = False
    try:
        db.execute("BEGIN IMMEDIATE")
        txn = db.execute("""
            SELECT id, user_id, amount, status
            FROM transactions
            WHERE id=? AND kind='deposit'
        """, (transaction_id,)).fetchone()

        if txn is None:
            db.rollback()
            flash("Deposit request not found.")
        elif txn["status"] != "pending":
            db.rollback()
            flash("This deposit has already been processed.")
        else:
            changed = db.execute("""
                UPDATE transactions SET status='approved'
                WHERE id=? AND kind='deposit' AND status='pending'
            """, (transaction_id,)).rowcount

            if changed != 1:
                db.rollback()
                flash("Deposit status changed; please refresh.")
            else:
                db.execute(
                    "UPDATE users SET balance=balance+? WHERE id=?",
                    (txn["amount"], txn["user_id"])
                )

                # A qualifying invitee needs an approved deposit of UGX 20,000+.
                if txn["amount"] >= 20000:
                    invitee = db.execute(
                        "SELECT invited_by FROM users WHERE id=?",
                        (txn["user_id"],)
                    ).fetchone()

                    if invitee and invitee["invited_by"]:
                        inviter_id = invitee["invited_by"]

                        qualified = db.execute("""
                            SELECT COUNT(*)
                            FROM users u
                            WHERE u.invited_by=?
                              AND EXISTS (
                                  SELECT 1 FROM transactions t
                                  WHERE t.user_id=u.id
                                    AND t.kind='deposit'
                                    AND t.status='approved'
                                    AND t.amount >= 20000
                              )
                        """, (inviter_id,)).fetchone()[0]

                        milestones = [
                            (3, "LV1_INVITE_3", 5000),
                            (10, "LV1_INVITE_10", 15000),
                            (30, "LV1_INVITE_30", 40000),
                        ]
                        for target, code, amount in milestones:
                            if qualified >= target:
                                cur = db.execute("""
                                    INSERT OR IGNORE INTO task_rewards
                                        (user_id, task_code, amount)
                                    VALUES (?, ?, ?)
                                """, (inviter_id, code, amount))

                                if cur.rowcount == 1:
                                    db.execute(
                                        "UPDATE users SET balance=balance+? WHERE id=?",
                                        (amount, inviter_id)
                                    )
                                    reward_paid = True

                db.commit()
                flash("Deposit approved and depositor balance credited once.")
                if reward_paid:
                    flash("LV1 task completed! UGX 5,000 reward credited to inviter balance.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
    return redirect(url_for("admin_deposits"))


@app.route("/admin/deposits/<int:transaction_id>/reject", methods=["POST"])
@admin_required
def admin_reject_deposit(transaction_id):
    with connect() as db:
        changed = db.execute("""
            UPDATE transactions SET status='rejected'
            WHERE id=? AND kind='deposit' AND status='pending'
        """, (transaction_id,)).rowcount
        if changed:
            flash("Deposit request rejected. No balance was credited.")
        else:
            flash("Request not found or already processed.")
    return redirect(url_for("admin_deposits"))


@app.route("/admin/withdrawals")
@admin_required
def admin_withdrawals():
    with connect() as db:
        withdrawals = db.execute("""
            SELECT t.id, t.user_id, t.amount, t.method, t.reference,
                   t.status, t.created_at, u.phone
            FROM transactions t
            JOIN users u ON u.id=t.user_id
            WHERE t.kind='withdrawal'
            ORDER BY CASE WHEN t.status='pending' THEN 0 ELSE 1 END, t.id DESC
        """).fetchall()
    return render_template("admin_withdrawals.html", withdrawals=withdrawals)


@app.route("/admin/withdrawals/<int:transaction_id>/paid", methods=["POST"])
@admin_required
def admin_mark_withdrawal_paid(transaction_id):
    db = connect()
    try:
        db.execute("BEGIN IMMEDIATE")
        txn = db.execute("""
            SELECT id, user_id, amount, status
            FROM transactions
            WHERE id=? AND kind='withdrawal'
        """, (transaction_id,)).fetchone()

        if txn is None:
            db.rollback()
            flash("Withdrawal request not found.")
        elif txn["status"] != "pending":
            db.rollback()
            flash("This withdrawal has already been processed.")
        else:
            user = db.execute(
                "SELECT balance FROM users WHERE id=?",
                (txn["user_id"],)
            ).fetchone()

            if user is None or user["balance"] < txn["amount"]:
                db.rollback()
                flash("Insufficient balance; withdrawal was not marked paid.")
            else:
                changed = db.execute("""
                    UPDATE transactions SET status='paid'
                    WHERE id=? AND kind='withdrawal' AND status='pending'
                """, (transaction_id,)).rowcount

                if changed != 1:
                    db.rollback()
                    flash("Request status changed; refresh and try again.")
                else:
                    db.execute(
                        "UPDATE users SET balance=balance-? WHERE id=?",
                        (txn["amount"], txn["user_id"])
                    )
                    db.commit()
                    flash("Withdrawal marked paid and balance deducted once.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
    return redirect(url_for("admin_withdrawals"))


@app.route("/admin/withdrawals/<int:transaction_id>/reject", methods=["POST"])
@admin_required
def admin_reject_withdrawal(transaction_id):
    with connect() as db:
        changed = db.execute("""
            UPDATE transactions SET status='rejected'
            WHERE id=? AND kind='withdrawal' AND status='pending'
        """, (transaction_id,)).rowcount
        if changed:
            flash("Withdrawal rejected. No balance was deducted.")
        else:
            flash("Request not found or already processed.")
    return redirect(url_for("admin_withdrawals"))


@app.route("/admin/users")
@admin_required
def admin_users():
    query = request.args.get("q", "").strip()
    with connect() as db:
        if query:
            users = db.execute("""
                SELECT id, phone, balance, created_at, invite_code, is_blocked
                FROM users WHERE phone LIKE ?
                ORDER BY id DESC LIMIT 100
            """, ("%" + query + "%",)).fetchall()
        else:
            users = db.execute("""
                SELECT id, phone, balance, created_at, invite_code, is_blocked
                FROM users ORDER BY id DESC LIMIT 100
            """).fetchall()
    return render_template("admin_users.html", users=users, query=query)


@app.route("/admin/users/<int:user_id>/block", methods=["POST"])
@admin_required
def admin_block_user(user_id):
    with connect() as db:
        target = db.execute(
            "SELECT id, phone FROM users WHERE id=?", (user_id,)
        ).fetchone()
        if not target:
            flash("User not found.")
        elif target["phone"] == ADMIN_PHONE:
            flash("The administrator account cannot be blocked here.")
        else:
            db.execute("UPDATE users SET is_blocked=1 WHERE id=?", (user_id,))
            flash("User blocked.")
    return redirect(url_for("admin_users"))


@app.route("/admin/users/<int:user_id>/unblock", methods=["POST"])
@admin_required
def admin_unblock_user(user_id):
    with connect() as db:
        changed = db.execute(
            "UPDATE users SET is_blocked=0 WHERE id=?", (user_id,)
        ).rowcount
    flash("User unblocked." if changed else "User not found.")
    return redirect(url_for("admin_users"))


@app.route("/admin/users/<int:user_id>/reset-password", methods=["GET", "POST"])
@admin_required
def admin_reset_password(user_id):
    if request.method == "POST":
        password = request.form.get("password", "")
        confirm = request.form.get("confirm", "")
        if len(password) < 8:
            flash("Use a password of at least 8 characters.")
        elif password != confirm:
            flash("The passwords do not match.")
        else:
            with connect() as db:
                target = db.execute(
                    "SELECT id, phone FROM users WHERE id=?", (user_id,)
                ).fetchone()
                if not target:
                    flash("User not found.")
                    return redirect(url_for("admin_users"))
                if target["phone"] == ADMIN_PHONE:
                    flash("Use the normal account recovery process for the administrator account.")
                    return redirect(url_for("admin_users"))
                db.execute(
                    "UPDATE users SET password=? WHERE id=?",
                    (generate_password_hash(password), user_id)
                )
            flash("Password reset successfully. Give the new password directly to the verified account owner.")
            return redirect(url_for("admin_users"))

    with connect() as db:
        target = db.execute(
            "SELECT id, phone FROM users WHERE id=?", (user_id,)
        ).fetchone()
    if not target:
        flash("User not found.")
        return redirect(url_for("admin_users"))
    return render_template("admin_reset_password.html", target=target)


@app.route("/admin/users/<int:user_id>/transactions")
@admin_required
def admin_user_transactions(user_id):
    with connect() as db:
        target = db.execute(
            "SELECT id, phone, balance FROM users WHERE id=?", (user_id,)
        ).fetchone()
        rows = db.execute("""
            SELECT kind, amount, method, reference, status, created_at
            FROM transactions WHERE user_id=? ORDER BY id DESC LIMIT 200
        """, (user_id,)).fetchall()
    if not target:
        flash("User not found.")
        return redirect(url_for("admin_users"))
    return render_template(
        "admin_user_transactions.html", target=target, transactions=rows
    )

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
