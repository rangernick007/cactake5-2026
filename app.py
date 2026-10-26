import logging
import os
import secrets
import sqlite3
from datetime import date, datetime, timedelta
from functools import wraps
from urllib.parse import quote
from flask import (Flask, Response, abort, flash, g, redirect, render_template,
                   request, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

from init_db import DB_PATH, init_db
import recommender
from events import init_events

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)


def load_secret_key():
    """Use SECRET_KEY from the environment, else a random key saved next to the app."""
    if os.environ.get("SECRET_KEY"):
        return os.environ["SECRET_KEY"]
    path = os.path.join(os.path.dirname(DB_PATH), ".secret_key")
    if not os.path.exists(path):
        with open(os.open(path, os.O_WRONLY | os.O_CREAT, 0o600), "w") as f:
            f.write(secrets.token_hex(32))
    with open(path) as f:
        return f.read().strip()


app.secret_key = load_secret_key()
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax")

MAX_ACTIVITIES = 10
CATEGORIES = ["Academic", "Athletics", "Community Service", "Leadership", "Work Experience", "Arts"]

# Helper function to connect to SQLite whenever a route needs data
def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # Returns query results as dictionary-like objects
    return conn

init_db()


# ---------- Auth ----------

@app.before_request
def load_user_and_check_csrf():
    g.user = None
    if "user_id" in session:
        with get_db_connection() as conn:
            g.user = conn.execute("SELECT * FROM users WHERE id = ?", (session["user_id"],)).fetchone()
        if g.user is None:
            session.clear()
    if request.method == "POST":
        token = session.get("csrf_token")
        if not token or not secrets.compare_digest(token, request.form.get("csrf_token", "")):
            abort(400, "Invalid or missing form token. Reload the page and try again.")


@app.context_processor
def inject_csrf():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_hex(16)
    return {"csrf_token": session["csrf_token"], "current_user": g.get("user")}


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.user is None:
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


def role_required(role):
    """Use under @login_required. Sends people with the other role back to the dashboard."""
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if g.user["role"] != role:
                flash(f"That page is only available to {role}s. Switch your role on the dashboard to use it.", "error")
                return redirect(url_for("home"))
            return view(*args, **kwargs)
        return wrapped
    return decorator


def after_login_url():
    """Where to go after logging in: back to a pending QR check-in, else the dashboard."""
    token = session.get("pending_checkin")
    return url_for("checkin", token=token) if token else url_for("home")


def start_session(user_id):
    pending = session.get("pending_checkin")
    session.clear()  # new session on login prevents fixation
    if pending:
        session["pending_checkin"] = pending
    session["user_id"] = user_id
    session["csrf_token"] = secrets.token_hex(16)


@app.route("/register", methods=["GET", "POST"])
def register():
    if g.user:
        return redirect(url_for("home"))
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        role = request.form.get("role", "")
        if role not in ("student", "organizer"):
            flash("Please choose whether you're a student or an organizer.", "error")
        elif not name or "@" not in email or "." not in email.split("@")[-1]:
            flash("Please enter your name and a valid email address.", "error")
        elif len(password) < 8:
            flash("Password must be at least 8 characters.", "error")
        elif password != request.form.get("confirm", ""):
            flash("Passwords do not match.", "error")
        else:
            try:
                with get_db_connection() as conn:
                    first_user = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0
                    cur = conn.execute(
                        "INSERT INTO users (name, email, password_hash, feed_token, role) VALUES (?, ?, ?, ?, ?)",
                        (name, email, generate_password_hash(password), secrets.token_urlsafe(24), role))
                    if first_user:  # the first account adopts data saved before accounts existed
                        for table in ("activities", "deadlines"):
                            conn.execute(f"UPDATE {table} SET user_id = ? WHERE user_id IS NULL", (cur.lastrowid,))
                start_session(cur.lastrowid)
                return redirect(after_login_url())
            except sqlite3.IntegrityError:
                flash("An account with that email already exists. Try logging in.", "error")
    # People arriving from an event QR code are almost certainly students
    chosen = request.form.get("role") or ("student" if session.get("pending_checkin") else "")
    return render_template("register.html", chosen_role=chosen)


@app.route("/login", methods=["GET", "POST"])
def login():
    if g.user:
        return redirect(url_for("home"))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        with get_db_connection() as conn:
            user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if user and check_password_hash(user["password_hash"], request.form.get("password", "")):
            start_session(user["id"])
            return redirect(after_login_url())
        flash("Incorrect email or password.", "error")
    return render_template("login.html")


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("login"))


def fetch_activities():
    with get_db_connection() as conn:
        return conn.execute("SELECT * FROM activities WHERE user_id = ? ORDER BY id DESC", (g.user["id"],)).fetchall()


def fetch_deadlines():
    with get_db_connection() as conn:
        rows = conn.execute("SELECT * FROM deadlines WHERE user_id = ? ORDER BY due_date, id", (g.user["id"],)).fetchall()
    today = date.today()
    deadlines = []
    for r in rows:
        due = date.fromisoformat(r["due_date"])
        deadlines.append(dict(r, date=due, days_left=(due - today).days))
    return deadlines


@app.route("/")
@login_required
def home():
    deadlines = fetch_deadlines()
    upcoming = [d for d in deadlines if d["days_left"] >= 0]
    if g.user["role"] == "organizer":
        with get_db_connection() as conn:
            events_count = conn.execute("SELECT COUNT(*) FROM events WHERE organizer_id = ?",
                                        (g.user["id"],)).fetchone()[0]
            checkins = conn.execute(
                "SELECT COUNT(*) FROM event_checkins c JOIN events e ON e.id = c.event_id "
                "WHERE e.organizer_id = ?", (g.user["id"],)).fetchone()[0]
        return render_template("index.html", upcoming=upcoming, events_count=events_count, checkins=checkins)
    activities = fetch_activities()
    service_hours = sum((a["hours_per_week"] or 0) * (a["weeks_per_year"] or 0)
                        for a in activities if a["category"] == "Community Service")
    return render_template("index.html", activities=activities, upcoming=upcoming,
                           service_hours=service_hours, max_activities=MAX_ACTIVITIES)


@app.route("/role", methods=["POST"])
@login_required
def set_role():
    role = request.form.get("role", "")
    if role not in ("student", "organizer"):
        abort(400)
    with get_db_connection() as conn:
        conn.execute("UPDATE users SET role = ? WHERE id = ?", (role, g.user["id"]))
    flash(f"You're now using Collegia as {'an organizer' if role == 'organizer' else 'a student'}.", "success")
    return redirect(url_for("home"))


# ---------- Activities ----------

@app.route("/activities")
@login_required
@role_required("student")
def activities():
    return render_template("activities.html", activities=fetch_activities(),
                           categories=CATEGORIES, max_activities=MAX_ACTIVITIES)


@app.route("/activities/add", methods=["POST"])
@login_required
@role_required("student")
def add_activity():
    f = request.form
    category = f.get("activity-type", "").strip()
    title = f.get("activity-title", "").strip()
    org = f.get("organization-name", "").strip()
    desc = f.get("activity-description", "").strip()
    try:
        hours = int(f.get("hours-per-week", ""))
        weeks = int(f.get("weeks-per-year", ""))
    except ValueError:
        hours = weeks = 0

    if category not in CATEGORIES or not title or not org:
        flash("Please choose a category and fill in the title and organization.", "error")
    elif not (1 <= hours <= 168) or not (1 <= weeks <= 52):
        flash("Hours per week must be 1-168 and weeks per year 1-52.", "error")
    elif len(desc) > 150:
        flash("Description must be 150 characters or fewer.", "error")
    elif len(fetch_activities()) >= MAX_ACTIVITIES:
        flash(f"You can record at most {MAX_ACTIVITIES} activities. Delete one first.", "error")
    else:
        with get_db_connection() as conn:
            conn.execute(
                "INSERT INTO activities (title, organization, category, hours_per_week, weeks_per_year, description, user_id) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)", (title, org, category, hours, weeks, desc, g.user["id"]))
        flash("Activity saved.", "success")
    return redirect(url_for("activities"))


@app.route("/activities/<int:activity_id>/delete", methods=["POST"])
@login_required
@role_required("student")
def delete_activity(activity_id):
    with get_db_connection() as conn:
        conn.execute("DELETE FROM activities WHERE id = ? AND user_id = ?", (activity_id, g.user["id"]))
    flash("Activity deleted.", "success")
    return redirect(url_for("activities"))


@app.route("/activities/summary")
@login_required
@role_required("student")
def activities_summary():
    return render_template("activities_summary.html", activities=fetch_activities())


# ---------- Calendar ----------

def google_add_url(d):
    start = d["date"].strftime("%Y%m%d")
    end = (d["date"] + timedelta(days=1)).strftime("%Y%m%d")
    return ("https://calendar.google.com/calendar/render?action=TEMPLATE"
            f"&text={quote(d['title'])}&dates={start}/{end}&details={quote(d['details'] or '')}")


@app.route("/calendar")
@login_required
def calendar():
    events = [dict(d, google_url=google_add_url(d)) for d in fetch_deadlines()]
    feed_http = request.url_root.rstrip("/") + url_for("calendar_ics", token=g.user["feed_token"])
    feed_webcal = feed_http.replace("https://", "webcal://").replace("http://", "webcal://")
    google_subscribe = "https://calendar.google.com/calendar/r?cid=" + quote(feed_webcal, safe="")
    return render_template("calendar.html", events=events, feed_webcal=feed_webcal,
                           google_subscribe=google_subscribe)


@app.route("/calendar/deadlines/add", methods=["POST"])
@login_required
def add_deadline():
    title = request.form.get("deadline-title", "").strip()
    details = request.form.get("deadline-details", "").strip()
    try:
        due = date.fromisoformat(request.form.get("deadline-date", ""))
    except ValueError:
        due = None
    if not title or due is None:
        flash("A deadline needs a title and a valid date.", "error")
    else:
        with get_db_connection() as conn:
            conn.execute("INSERT INTO deadlines (title, due_date, details, user_id) VALUES (?, ?, ?, ?)",
                         (title, due.isoformat(), details, g.user["id"]))
        flash("Deadline added.", "success")
    return redirect(url_for("calendar"))


@app.route("/calendar/deadlines/<int:deadline_id>/delete", methods=["POST"])
@login_required
def delete_deadline(deadline_id):
    with get_db_connection() as conn:
        conn.execute("DELETE FROM deadlines WHERE id = ? AND user_id = ?", (deadline_id, g.user["id"]))
    flash("Deadline deleted.", "success")
    return redirect(url_for("calendar"))


@app.route("/calendar/<token>.ics")
def calendar_ics(token):
    with get_db_connection() as conn:
        user = conn.execute("SELECT id FROM users WHERE feed_token = ?", (token,)).fetchone()
    if user is None:
        abort(404)
    g.user = user  # calendar apps cannot log in, so the secret token identifies the owner
    stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Collegia//EN",
             "CALSCALE:GREGORIAN", "X-WR-CALNAME:Collegia Deadlines"]
    for d in fetch_deadlines():
        details = (d["details"] or "").replace("\n", " ")
        lines += ["BEGIN:VEVENT", f"UID:deadline-{d['id']}@college-planner", f"DTSTAMP:{stamp}",
                  f"DTSTART;VALUE=DATE:{d['date'].strftime('%Y%m%d')}",
                  f"DTEND;VALUE=DATE:{(d['date'] + timedelta(days=1)).strftime('%Y%m%d')}",
                  f"SUMMARY:{d['title']}", f"DESCRIPTION:{details}", "END:VEVENT"]
    lines.append("END:VCALENDAR")
    return Response("\r\n".join(lines) + "\r\n", mimetype="text/calendar",
                    headers={"Content-Disposition": "inline; filename=deadlines.ics"})


# ---------- Resume ----------

@app.route("/resume")
@login_required
@role_required("student")
def resume():
    draft = request.args.get("draft") == "1"
    grouped = {}
    for a in reversed(fetch_activities()):
        grouped.setdefault(a["category"], []).append(a)
    return render_template("resume.html", draft=draft, grouped=grouped)


# ---------- Opportunities ----------

OPP_CATEGORIES = ["CS & Engineering", "Math & Science", "Business & Civics",
                  "Arts & Humanities", "Service & Leadership", "Athletics", "Other"]
OPP_FORMATS = ["virtual", "in-person", "hybrid"]


def search_opportunities(q="", category="", fmt="", location="", limit=100):
    """Built-in listings (user_id NULL) plus the current user's own listings."""
    sql = "SELECT * FROM opportunities WHERE (user_id IS NULL OR user_id = ?)"
    params = [g.user["id"]]
    if q:
        like = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        sql += " AND (title LIKE ? ESCAPE '\\' OR organization LIKE ? ESCAPE '\\' OR description LIKE ? ESCAPE '\\')"
        params += [like] * 3
    if category in OPP_CATEGORIES:
        sql += " AND category = ?"
        params.append(category)
    if fmt in OPP_FORMATS:
        sql += " AND format = ?"
        params.append(fmt)
    if location:
        like = "%" + location.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        # nationwide and virtual listings are reachable from anywhere
        sql += " AND (location LIKE ? ESCAPE '\\' OR location = 'Nationwide' OR format = 'virtual')"
        params.append(like)
    sql += " ORDER BY (user_id IS NULL), title LIMIT ?"
    params.append(limit)
    with get_db_connection() as conn:
        return conn.execute(sql, params).fetchall()


@app.route("/opportunities", methods=["GET", "POST"])
@login_required
@role_required("student")
def opportunities():
    f = {k: request.args.get(k, "").strip()[:100] for k in ("q", "category", "format", "location")}
    ai = {"location_mode": "local", "location": "", "interests": "", "summary": "", "recs": None}
    if request.method == "POST":
        ai.update(run_ai_picks())
    rows = search_opportunities(f["q"], f["category"], f["format"], f["location"])
    return render_template("opportunities.html", rows=rows, f=f, categories=OPP_CATEGORIES,
                           formats=OPP_FORMATS, ai=ai, activity_count=len(fetch_activities()),
                           ai_provider=recommender.provider())


@app.route("/opportunities/add", methods=["POST"])
@login_required
@role_required("student")
def add_opportunity():
    f = request.form
    title, org = f.get("title", "").strip()[:150], f.get("organization", "").strip()[:150]
    category, fmt = f.get("category", ""), f.get("format", "")
    location = f.get("location", "").strip()[:100]
    desc = f.get("description", "").strip()[:400]
    url = f.get("url", "").strip()[:300]
    deadline = f.get("deadline", "").strip()
    if deadline:
        try:
            deadline = date.fromisoformat(deadline).isoformat()
        except ValueError:
            deadline = None
    if not title or not org or not location or category not in OPP_CATEGORIES or fmt not in OPP_FORMATS:
        flash("Title, organization, category, format and location are required.", "error")
    elif url and not url.lower().startswith(("http://", "https://")):
        flash("The link must start with http:// or https://", "error")
    elif deadline is None:
        flash("That deadline date isn't valid.", "error")
    else:
        with get_db_connection() as conn:
            conn.execute(
                "INSERT INTO opportunities (user_id, title, organization, category, format, location, description, url, deadline) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (g.user["id"], title, org, category, fmt, location, desc, url, deadline or None))
        flash("Listing added.", "success")
    return redirect(url_for("opportunities"))


@app.route("/opportunities/<int:opp_id>/delete", methods=["POST"])
@login_required
@role_required("student")
def delete_opportunity(opp_id):
    with get_db_connection() as conn:
        conn.execute("DELETE FROM opportunities WHERE id = ? AND user_id = ?", (opp_id, g.user["id"]))
    flash("Listing deleted.", "success")
    return redirect(url_for("opportunities"))


# ---------- AI picks (shown on the Opportunities page) ----------

RECOMMEND_COOLDOWN_SECONDS = 15


def run_ai_picks():
    """Handle the AI Picks form; returns the values the template needs."""
    mode = request.form.get("location-mode", "local")
    location = request.form.get("location", "").strip()[:100]
    interests = request.form.get("interests", "").strip()[:500]
    result = {"location_mode": mode, "location": location, "interests": interests,
              "summary": "", "recs": None}
    now = datetime.utcnow().timestamp()
    if mode == "local" and not location:
        flash("Enter your city or ZIP code, or choose anywhere in the U.S.", "error")
    elif now - session.get("last_recommend", 0) < RECOMMEND_COOLDOWN_SECONDS:
        flash("Please wait a few seconds between requests.", "error")
    else:
        session["last_recommend"] = now
        place = ("anywhere in the U.S. (national and online options welcome)" if mode == "anywhere"
                 else f"near {location}, but include some nationwide/online options too" if mode == "both"
                 else f"near {location}")
        try:
            result["summary"], result["recs"] = recommender.recommend(
                fetch_activities(), place, interests,
                listings=search_opportunities(location=location if mode != "anywhere" else ""))
        except RuntimeError as e:
            flash(str(e), "error")
    return result


@app.route("/recommendations")
@login_required
@role_required("student")
def recommendations():
    return redirect(url_for("opportunities"))


init_events(app, get_db_connection, login_required, role_required, CATEGORIES, MAX_ACTIVITIES)


if __name__ == "__main__":
    # Debug mode is off unless FLASK_DEBUG=1; never combine it with a public address,
    # because the debugger lets anyone who can reach the server run code.
    debug = os.environ.get("FLASK_DEBUG") == "1"
    app.run(host=os.environ.get("HOST", "127.0.0.1"), port=int(os.environ.get("PORT", "5000")), debug=debug)
