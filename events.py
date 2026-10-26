"""Event organizer tools: create an event, get a QR code, and let attendees check in.

Scanning the QR opens /checkin/<token>, where a logged-in student can add the event
to their Activity Log with one click.
"""
import io
import os
import re
import secrets
import sqlite3
from datetime import date

import qrcode
import qrcode.image.svg
from flask import Response, abort, flash, g, redirect, render_template, request, session, url_for

MAX_EVENTS_PER_USER = 50
TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{16,64}$")


def init_events(app, get_db_connection, login_required, role_required, categories, max_activities):

    def checkin_url(token):
        base = os.environ.get("PUBLIC_BASE_URL", "").rstrip("/") or request.url_root.rstrip("/")
        return f"{base}/checkin/{token}"

    def own_event(event_id):
        with get_db_connection() as conn:
            row = conn.execute("SELECT * FROM events WHERE id = ? AND organizer_id = ?",
                               (event_id, g.user["id"])).fetchone()
        if row is None:
            abort(404)
        return row

    @app.route("/events")
    @login_required
    @role_required("organizer")
    def events():
        with get_db_connection() as conn:
            rows = conn.execute(
                "SELECT e.*, (SELECT COUNT(*) FROM event_checkins c WHERE c.event_id = e.id) AS checkins "
                "FROM events e WHERE organizer_id = ? ORDER BY e.id DESC", (g.user["id"],)).fetchall()
        return render_template("events.html", rows=rows, categories=categories)

    @app.route("/events/add", methods=["POST"])
    @login_required
    @role_required("organizer")
    def add_event():
        f = request.form
        title, org = f.get("title", "").strip()[:100], f.get("organization", "").strip()[:100]
        category = f.get("category", "")
        desc = f.get("description", "").strip()[:150]
        when = f.get("event-date", "").strip()
        try:
            hours = int(f.get("hours", ""))
            when = date.fromisoformat(when).isoformat() if when else None
        except ValueError:
            hours, when = 0, None
            if f.get("event-date", "").strip():
                flash("That date isn't valid.", "error")
                return redirect(url_for("events"))
        if not title or not org or category not in categories:
            flash("Event name, organization and category are required.", "error")
        elif not 1 <= hours <= 200:
            flash("Hours credited must be between 1 and 200.", "error")
        else:
            with get_db_connection() as conn:
                count = conn.execute("SELECT COUNT(*) FROM events WHERE organizer_id = ?",
                                     (g.user["id"],)).fetchone()[0]
                if count >= MAX_EVENTS_PER_USER:
                    flash(f"You can have at most {MAX_EVENTS_PER_USER} events. Delete one first.", "error")
                    return redirect(url_for("events"))
                cur = conn.execute(
                    "INSERT INTO events (organizer_id, token, title, organization, category, event_date, hours, description) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (g.user["id"], secrets.token_urlsafe(16), title, org, category, when, hours, desc))
            flash("Event created. Your QR code is ready.", "success")
            return redirect(url_for("event_qr", event_id=cur.lastrowid))
        return redirect(url_for("events"))

    @app.route("/events/<int:event_id>")
    @login_required
    @role_required("organizer")
    def event_qr(event_id):
        ev = own_event(event_id)
        with get_db_connection() as conn:
            checkins = conn.execute("SELECT COUNT(*) FROM event_checkins WHERE event_id = ?",
                                    (event_id,)).fetchone()[0]
        return render_template("event_qr.html", ev=ev, checkins=checkins, url=checkin_url(ev["token"]))

    @app.route("/events/<int:event_id>/qr.svg")
    @login_required
    @role_required("organizer")
    def event_qr_svg(event_id):
        ev = own_event(event_id)
        img = qrcode.make(checkin_url(ev["token"]), image_factory=qrcode.image.svg.SvgPathImage,
                          error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=12, border=4)
        buf = io.BytesIO()
        img.save(buf)
        headers = {"Content-Disposition": f'inline; filename="event-{event_id}-qr.svg"'}
        return Response(buf.getvalue(), mimetype="image/svg+xml", headers=headers)

    @app.route("/events/<int:event_id>/delete", methods=["POST"])
    @login_required
    @role_required("organizer")
    def delete_event(event_id):
        own_event(event_id)
        with get_db_connection() as conn:
            conn.execute("DELETE FROM event_checkins WHERE event_id = ?", (event_id,))
            conn.execute("DELETE FROM events WHERE id = ? AND organizer_id = ?", (event_id, g.user["id"]))
        flash("Event deleted. Its QR code no longer works.", "success")
        return redirect(url_for("events"))

    @app.route("/checkin/<token>", methods=["GET", "POST"])
    def checkin(token):
        if not TOKEN_RE.match(token):
            abort(404)
        if g.user is None:  # send them to log in, then straight back here
            session["pending_checkin"] = token
            flash("Log in or create an account to add this event to your Activity Log.", "success")
            return redirect(url_for("login"))
        session.pop("pending_checkin", None)
        if g.user["role"] != "student":
            flash("Event check-in is for students. Switch your role to Student on the dashboard to scan this code.", "error")
            return redirect(url_for("home"))
        with get_db_connection() as conn:
            ev = conn.execute("SELECT * FROM events WHERE token = ?", (token,)).fetchone()
            if ev is None:
                abort(404)
            done = conn.execute("SELECT 1 FROM event_checkins WHERE event_id = ? AND user_id = ?",
                                (ev["id"], g.user["id"])).fetchone() is not None
            if request.method == "POST" and not done:
                n = conn.execute("SELECT COUNT(*) FROM activities WHERE user_id = ?", (g.user["id"],)).fetchone()[0]
                if n >= max_activities:
                    flash(f"Your Activity Log is full ({max_activities}). Delete one first.", "error")
                    return redirect(url_for("checkin", token=token))
                try:
                    conn.execute("INSERT INTO event_checkins (event_id, user_id) VALUES (?, ?)",
                                 (ev["id"], g.user["id"]))
                except sqlite3.IntegrityError:
                    return redirect(url_for("checkin", token=token))
                conn.execute(
                    "INSERT INTO activities (title, organization, category, hours_per_week, weeks_per_year, description, user_id) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (ev["title"], ev["organization"], ev["category"], ev["hours"], 1,
                     (ev["description"] or "") + (f" ({ev['event_date']})" if ev["event_date"] else ""),
                     g.user["id"]))
                flash("Added to your Activity Log.", "success")
                return redirect(url_for("activities"))
        return render_template("checkin.html", ev=ev, done=done)
