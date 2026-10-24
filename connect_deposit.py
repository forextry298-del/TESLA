from pathlib import Path

app_path = Path("app.py")
dash_path = Path("templates/dashboard.html")
app = app_path.read_text()
dash = dash_path.read_text()

if 'def deposit_instructions(' not in app:
    raise SystemExit("Deposit routes missing. No changes made.")

old_link = '<a href="#deposit-details" class="sx-deposit">Deposit</a>'
new_link = '<a href="{{ url_for(\'deposit\') }}" class="sx-deposit">Deposit</a>'

if old_link in dash:
    dash = dash.replace(old_link, new_link, 1)
elif new_link not in dash:
    raise SystemExit("Dashboard Deposit button not found. No changes made.")

marker = '    records = sorted('
if 'FROM deposit_requests' not in app:
    query = '''        deposits = c.execute(
            """SELECT 'Mobile Money Deposit' AS title,
                      requested_usd AS amount, status,
                      datetime(created_at, 'unixepoch') AS created_at,
                      network AS details
               FROM deposit_requests
               WHERE user_id = ?""",
            (session["uid"],)
        ).fetchall()

'''
    if marker not in app:
        raise SystemExit("Transaction history insertion point not found. No changes made.")
    app = app.replace(marker, query + marker, 1)
    old_records = '[dict(r) for r in purchases] + [dict(r) for r in claims]'
    new_records = '[dict(r) for r in purchases] + [dict(r) for r in claims] + [dict(r) for r in deposits]'
    if old_records not in app:
        raise SystemExit("Transaction list expression not found. No changes made.")
    app = app.replace(old_records, new_records, 1)

app_path.write_text(app)
dash_path.write_text(dash)
print("Dashboard link and transaction history connected.")
