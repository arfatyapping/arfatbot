import os, sqlite3, secrets, time
from datetime import datetime, timezone
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, abort
from werkzeug.security import generate_password_hash, check_password_hash

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.environ.get("DATABASE_PATH", os.path.join(BASE_DIR, "instance", "app.db"))
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE", "0") == "1",
    PERMANENT_SESSION_LIFETIME=60 * 60 * 8,
    MAX_CONTENT_LENGTH=1 * 1024 * 1024,
)

DEFAULT_CONFIG = {
    "instagram_username": "",
    "welcome_message": "Hey {username} 👋 Welcome to {group_name}! ✨",
    "group_id": "",
    "mention_username": 1,
    "message_delay": 3,
    "check_interval": 30,
    "welcome_enabled": 1,
    "demo_mode": 1,
    "default_template": "Welcome",
}

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with db() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS config (
            user_id INTEGER PRIMARY KEY,
            instagram_username TEXT NOT NULL DEFAULT '',
            welcome_message TEXT NOT NULL,
            group_id TEXT NOT NULL DEFAULT '',
            mention_username INTEGER NOT NULL DEFAULT 1,
            message_delay INTEGER NOT NULL DEFAULT 3,
            check_interval INTEGER NOT NULL DEFAULT 30,
            welcome_enabled INTEGER NOT NULL DEFAULT 1,
            demo_mode INTEGER NOT NULL DEFAULT 1,
            default_template TEXT NOT NULL DEFAULT 'Welcome',
            FOREIGN KEY(user_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            message TEXT NOT NULL,
            is_default INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            UNIQUE(user_id, name)
        );
        CREATE TABLE IF NOT EXISTS activity (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            kind TEXT NOT NULL,
            message TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'info',
            created_at TEXT NOT NULL
        );
        """)
        # First-run admin is configured via environment variables; never use a built-in password.
        username = os.environ.get("ADMIN_USERNAME", "").strip()
        password = os.environ.get("ADMIN_PASSWORD", "")
        if username and password and len(password) >= 12:
            existing = con.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()
            if not existing:
                cur = con.execute("INSERT INTO users(username,password_hash,created_at) VALUES(?,?,?)",
                    (username, generate_password_hash(password), now()))
                uid = cur.lastrowid
                con.execute("""INSERT INTO config(user_id,instagram_username,welcome_message,group_id,
                    mention_username,message_delay,check_interval,welcome_enabled,demo_mode,default_template)
                    VALUES(?,?,?,?,?,?,?,?,?,?)""",
                    (uid, DEFAULT_CONFIG["instagram_username"], DEFAULT_CONFIG["welcome_message"], "",
                     1, 3, 30, 1, 1, "Welcome"))
                con.execute("INSERT INTO templates(user_id,name,message,is_default,created_at) VALUES(?,?,?,?,?)",
                    (uid, "Welcome", DEFAULT_CONFIG["welcome_message"], 1, now()))
                log_event(con, uid, "system", "Workspace initialized in demonstration mode.", "info")
        con.commit()

def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

def log_event(con, user_id, kind, message, status="info"):
    con.execute("INSERT INTO activity(user_id,kind,message,status,created_at) VALUES(?,?,?,?,?)",
                (user_id, kind, message[:500], status, now()))

def current_user():
    if "user_id" not in session:
        return None
    with db() as con:
        return con.execute("SELECT id,username FROM users WHERE id=?", (session["user_id"],)).fetchone()

def login_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if not current_user():
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapped

def csrf_token():
    if "_csrf" not in session:
        session["_csrf"] = secrets.token_urlsafe(24)
    return session["_csrf"]
app.jinja_env.globals["csrf_token"] = csrf_token

@app.before_request
def security_checks():
    if request.method == "POST":
        supplied = request.form.get("_csrf") or request.headers.get("X-CSRF-Token")
        expected = session.get("_csrf")
        if not supplied or not expected or not secrets.compare_digest(supplied, expected):
            abort(400, description="Security check failed. Refresh the page and try again.")

@app.after_request
def headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Content-Security-Policy"] = "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'"
    return response

def get_config(uid):
    with db() as con:
        row = con.execute("SELECT * FROM config WHERE user_id=?", (uid,)).fetchone()
    return dict(row) if row else dict(DEFAULT_CONFIG)

def page_data(uid):
    with db() as con:
        counts = con.execute("""SELECT
            COUNT(*) total,
            SUM(CASE WHEN status='success' THEN 1 ELSE 0 END) successful,
            SUM(CASE WHEN status='error' THEN 1 ELSE 0 END) failed
            FROM activity WHERE user_id=? AND kind='delivery'""", (uid,)).fetchone()
        logs = con.execute("SELECT * FROM activity WHERE user_id=? ORDER BY id DESC LIMIT 8", (uid,)).fetchall()
        template_count = con.execute("SELECT COUNT(*) n FROM templates WHERE user_id=?", (uid,)).fetchone()["n"]
    return {"total": counts["total"] or 0, "successful": counts["successful"] or 0,
            "failed": counts["failed"] or 0, "logs": logs, "template_count": template_count}

@app.route("/")
def index():
    if not current_user():
        return redirect(url_for("login"))
    return redirect(url_for("dashboard"))

@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user():
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        with db() as con:
            user = con.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            session.permanent = True
            session["_csrf"] = secrets.token_urlsafe(24)
            with db() as con:
                log_event(con, user["id"], "auth", "Successful sign-in.", "success")
            return redirect(url_for("dashboard"))
        flash("Sign-in failed. Check your username and password.", "error")
    return render_template("login.html", title="Sign in")

@app.post("/logout")
@login_required
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/dashboard")
@login_required
def dashboard():
    user = current_user()
    cfg = get_config(user["id"])
    data = page_data(user["id"])
    return render_template("dashboard.html", title="Dashboard", user=user, cfg=cfg, data=data)

@app.route("/configuration", methods=["GET", "POST"])
@login_required
def configuration():
    user = current_user()
    cfg = get_config(user["id"])
    if request.method == "POST":
        message = request.form.get("welcome_message", "").strip()
        group_id = request.form.get("group_id", "").strip()
        instagram_username = request.form.get("instagram_username", "").strip().lstrip("@")
        try:
            delay = int(request.form.get("message_delay", "3"))
            interval = int(request.form.get("check_interval", "30"))
        except ValueError:
            flash("Delay and check interval must be whole numbers.", "error")
            return redirect(url_for("configuration"))
        if not message or len(message) > 1000:
            flash("Welcome message is required and must be 1,000 characters or fewer.", "error")
        elif len(group_id) > 120 or len(instagram_username) > 30:
            flash("Please check the username and chat identifier lengths.", "error")
        elif not (0 <= delay <= 300 and 5 <= interval <= 3600):
            flash("Delay must be 0–300 seconds; check interval must be 5–3600 seconds.", "error")
        else:
            enabled = int(request.form.get("welcome_enabled") == "on")
            mention = int(request.form.get("mention_username") == "on")
            with db() as con:
                con.execute("""UPDATE config SET instagram_username=?,welcome_message=?,group_id=?,
                    mention_username=?,message_delay=?,check_interval=?,welcome_enabled=? WHERE user_id=?""",
                    (instagram_username, message, group_id, mention, delay, interval, enabled, user["id"]))
                log_event(con, user["id"], "config", "Configuration saved.", "success")
                con.commit()
            flash("Configuration saved securely.", "success")
            return redirect(url_for("configuration"))
    return render_template("configuration.html", title="Configuration", user=user, cfg=cfg)

@app.route("/templates", methods=["GET", "POST"])
@login_required
def templates_page():
    user = current_user()
    if request.method == "POST":
        action = request.form.get("action")
        name = request.form.get("name", "").strip()
        message = request.form.get("message", "").strip()
        with db() as con:
            if action == "save":
                if not name or len(name) > 40 or not message or len(message) > 1000:
                    flash("Add a template name (max 40 characters) and message (max 1,000).", "error")
                else:
                    try:
                        con.execute("INSERT INTO templates(user_id,name,message,is_default,created_at) VALUES(?,?,?,?,?)",
                                    (user["id"], name, message, 0, now()))
                        log_event(con, user["id"], "template", f'Template "{name}" created.', "success")
                        con.commit()
                        flash("Template saved.", "success")
                    except sqlite3.IntegrityError:
                        flash("A template with that name already exists.", "error")
            elif action == "default":
                try:
                    tid = int(request.form.get("template_id", "0"))
                except ValueError:
                    tid = 0
                row = con.execute("SELECT * FROM templates WHERE id=? AND user_id=?", (tid, user["id"])).fetchone()
                if row:
                    con.execute("UPDATE templates SET is_default=0 WHERE user_id=?", (user["id"],))
                    con.execute("UPDATE templates SET is_default=1 WHERE id=?", (tid,))
                    con.execute("UPDATE config SET welcome_message=?,default_template=? WHERE user_id=?",
                                (row["message"], row["name"], user["id"]))
                    log_event(con, user["id"], "template", f'"{row["name"]}" set as default.', "success")
                    con.commit()
                    flash("Default template updated.", "success")
            elif action == "delete":
                try:
                    tid = int(request.form.get("template_id", "0"))
                except ValueError:
                    tid = 0
                row = con.execute("SELECT * FROM templates WHERE id=? AND user_id=?", (tid, user["id"])).fetchone()
                if row:
                    con.execute("DELETE FROM templates WHERE id=? AND user_id=?", (tid, user["id"]))
                    log_event(con, user["id"], "template", f'Template "{row["name"]}" deleted.', "info")
                    con.commit()
                    flash("Template deleted.", "success")
            con.commit()
    with db() as con:
        templates = con.execute("SELECT * FROM templates WHERE user_id=? ORDER BY is_default DESC,id DESC", (user["id"],)).fetchall()
    cfg = get_config(user["id"])
    return render_template("templates.html", title="Message templates", user=user, templates=templates, cfg=cfg)

@app.route("/connection")
@login_required
def connection():
    user = current_user()
    # This app deliberately does not collect passwords, cookies, or session IDs.
    return render_template("connection.html", title="Account connection", user=user,
                           meta_app_id=bool(os.environ.get("META_APP_ID")))

@app.post("/connection/demo")
@login_required
def demo_connection():
    user = current_user()
    with db() as con:
        log_event(con, user["id"], "connection", "Demo connection preview opened; no Instagram account was connected.", "info")
        con.commit()
    flash("Demo mode only — no Instagram account was connected.", "info")
    return redirect(url_for("connection"))

@app.route("/statistics")
@login_required
def statistics():
    user = current_user()
    cfg = get_config(user["id"])
    data = page_data(user["id"])
    return render_template("statistics.html", title="Statistics & logs", user=user, cfg=cfg, data=data)

@app.post("/demo/send")
@login_required
def demo_send():
    user = current_user()
    cfg = get_config(user["id"])
    if not cfg["demo_mode"]:
        flash("Live delivery is not implemented. This workspace can only demonstrate delivery safely.", "error")
        return redirect(url_for("dashboard"))
    if not cfg["welcome_enabled"]:
        flash("Welcome messaging is disabled in configuration.", "error")
        return redirect(url_for("dashboard"))
    sample = cfg["welcome_message"].replace("{username}", "new_member").replace("{group_name}", "Demo Space")
    with db() as con:
        log_event(con, user["id"], "delivery", "DEMO: Preview delivery simulated — " + sample, "success")
        con.commit()
    flash("Demo delivery simulated. No Instagram message was sent.", "success")
    return redirect(url_for("dashboard"))

@app.errorhandler(400)
def bad_request(error):
    return render_template("error.html", title="Request blocked", code=400,
                           message=getattr(error, "description", "The request could not be processed.")), 400

@app.errorhandler(404)
def not_found(error):
    return render_template("error.html", title="Not found", code=404,
                           message="This page does not exist."), 404

init_db()

if __name__ == "__main__":
    # Use a production WSGI server for deployment; debug mode is intentionally disabled.
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", "5000")), debug=False)
