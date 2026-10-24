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
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")

def login_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
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

@app.route("/profile")
@login_required
def profile():
    return redirect(url_for("dashboard"))

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

@app.route("/deposit", methods=["GET", "POST"])
@login_required
def deposit():
    if request.method == "POST":
        try:
            amount = float(request.form.get("amount", "0"))
        except ValueError:
            amount = 0

        method = request.form.get("method", "").strip()
        reference = request.form.get("reference", "").strip()

        if not 1000 <= amount <= 5000000:
            flash("Enter a deposit amount between UGX 1,000 and UGX 5,000,000.")
        elif method not in ("MTN Mobile Money", "Airtel Money", "Bank"):
            flash("Select a valid payment method.")
        else:
            with connect() as db:
                db.execute("""
                    INSERT INTO transactions
                    (user_id, kind, amount, method, reference)
                    VALUES (?, 'deposit', ?, ?, ?)
                """, (session["user_id"], amount, method, reference))
            flash("Deposit request submitted. It will remain pending until verified.")
            return redirect(url_for("dashboard"))

    return render_template("transaction.html", kind="deposit")

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

@app.route("/admin")
@login_required
def admin_home():
    with connect() as db:
        user = db.execute(
            "SELECT phone FROM users WHERE id=?",
            (session["user_id"],)
        ).fetchone()

    if not user or user["phone"] != ADMIN_PHONE:
        flash("You are not authorized to access the admin panel.")
        return redirect(url_for("dashboard"))

    return render_template("admin_home.html")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
