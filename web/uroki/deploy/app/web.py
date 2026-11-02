import calendar
import os
from datetime import datetime, timezone

from flask import (
    Flask,
    Response,
    abort,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)

from . import db, ops, storage

UPLOAD_DIR = "/data/uploads"

app = Flask(__name__, template_folder="../templates", static_folder="../static")
app.debug = False


def _fmt(ts):
    return datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%d.%m.%Y %H:%M")


app.jinja_env.filters["fmt"] = _fmt


def _isodate(ts):
    return _as_local(ts).strftime("%Y-%m-%d")


def _isotime(ts):
    return _as_local(ts).strftime("%H:%M")


app.jinja_env.filters["isodate"] = _isodate
app.jinja_env.filters["isotime"] = _isotime


def _parse_scheduled(date_s, time_s):
    dt = datetime.strptime(f"{date_s} {time_s}", "%Y-%m-%d %H:%M")
    return calendar.timegm(dt.timetuple())


def _as_local(ts):
    return datetime.fromtimestamp(int(ts), tz=timezone.utc)


def _ics_escape(text):
    return (
        str(text or "")
        .replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r", "")
        .replace("\n", "\\n")
    )


def _ics_datetime(ts):
    return _as_local(ts).strftime("%Y%m%dT%H%M%SZ")


@app.get("/")
def index():
    q = request.args.get("q", "").strip()
    status = request.args.get("status", "").strip()
    subject = request.args.get("subject", "").strip()
    lessons = db.list_lessons(q=q, status=status, subject=subject)
    return render_template(
        "index.html",
        lessons=lessons,
        q=q,
        status=status,
        subject=subject,
        subjects=[r["subject"] for r in db.subject_directory()],
        counts=db.status_counts(),
    )


@app.get("/teachers")
def teachers():
    return render_template("teachers.html", rows=db.teacher_directory())


@app.get("/subjects")
def subjects():
    return render_template("subjects.html", rows=db.subject_directory())


@app.get("/archive")
def archive():
    return render_template("archive.html", lessons=db.list_lessons())


@app.get("/lesson/new")
def new_lesson():
    return render_template("new.html")


@app.post("/lesson")
def create_lesson():
    title = request.form.get("title", "").strip()
    subject = request.form.get("subject", "").strip()
    teacher = request.form.get("teacher", "").strip()
    if not title or not subject or not teacher:
        abort(400)
    try:
        scheduled_at = _parse_scheduled(request.form.get("date", ""), request.form.get("time", ""))
    except ValueError:
        abort(400)
    lid = db.create_lesson(title, subject, teacher, scheduled_at)
    ops.apply_schedule_changes()
    return redirect(url_for("lesson_card", id=lid), 303)


@app.get("/lesson/<int:id>")
def lesson_card(id):
    lesson = db.get_lesson(id)
    if lesson is None:
        abort(404)
    return render_template("lesson.html", lesson=lesson, comments=db.list_comments(id))


@app.get("/lesson/<int:id>/edit")
def edit_lesson_form(id):
    lesson = db.get_lesson(id)
    if lesson is None:
        abort(404)
    return render_template("edit.html", lesson=lesson)


@app.post("/lesson/<int:id>/edit")
def edit_lesson(id):
    lesson = db.get_lesson(id)
    if lesson is None:
        abort(404)
    title = request.form.get("title", "").strip()
    subject = request.form.get("subject", "").strip()
    teacher = request.form.get("teacher", "").strip()
    if not title or not subject or not teacher:
        abort(400)
    try:
        scheduled_at = _parse_scheduled(request.form.get("date", ""), request.form.get("time", ""))
    except ValueError:
        abort(400)
    db.update_lesson(id, title, subject, teacher, scheduled_at)
    if scheduled_at != lesson["scheduled_at"] or lesson["status"] != "planned":
        db.set_status(id, "planned")
        ops.apply_schedule_changes()
    return redirect(url_for("lesson_card", id=id), 303)


@app.post("/lesson/<int:id>/homework")
def set_homework(id):
    lesson = db.get_lesson(id)
    if lesson is None:
        abort(404)
    homework = request.form.get("homework", "").strip()
    db.set_homework(id, homework)
    return redirect(url_for("lesson_card", id=id), 303)


@app.post("/lesson/<int:id>/cancel")
def cancel_lesson(id):
    lesson = db.get_lesson(id)
    if lesson is None:
        abort(404)
    if lesson["status"] == "planned":
        db.set_status(id, "cancelled")
        ops.apply_schedule_changes()
    return redirect(url_for("lesson_card", id=id), 303)


@app.post("/lesson/<int:id>/comment")
def add_comment(id):
    lesson = db.get_lesson(id)
    if lesson is None:
        abort(404)
    author = request.form.get("author", "").strip()
    body = request.form.get("body", "").strip()
    if not author or not body:
        abort(400)
    db.add_comment(id, author, body)
    return redirect(url_for("lesson_card", id=id), 303)


@app.post("/comment/<int:id>/delete")
def delete_comment(id):
    db.delete_comment(id)
    return redirect(request.referrer or url_for("index"))


@app.post("/lesson/<int:id>/delete")
def delete_lesson(id):
    row = db.get_lesson_for_delete(id)
    if row is None:
        abort(404)
    file_path = row["file_path"]
    db.delete_lesson(id)
    if file_path and file_path.startswith(UPLOAD_DIR) and os.path.isfile(file_path):
        os.unlink(file_path)
    return redirect(url_for("index"))


@app.get("/lesson/<int:id>/ics")
def lesson_ics(id):
    lesson = db.get_lesson(id)
    if lesson is None:
        abort(404)
    start = _ics_datetime(lesson["scheduled_at"])
    end = _ics_datetime(lesson["scheduled_at"] + 45 * 60)
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//uroki//journal//RU",
        "BEGIN:VEVENT",
        "UID:lesson-%d@uroki" % lesson["id"],
        "DTSTAMP:" + _ics_datetime(lesson["created_at"]),
        "DTSTART:" + start,
        "DTEND:" + end,
        "SUMMARY:" + _ics_escape(lesson["title"]),
        "DESCRIPTION:" + _ics_escape(lesson["homework"]),
        "LOCATION:" + _ics_escape(lesson["subject"]),
        "CATEGORIES:" + _ics_escape(lesson["teacher"]),
        "END:VEVENT",
        "END:VCALENDAR",
    ]
    body = "\r\n".join(lines) + "\r\n"
    return Response(
        body,
        mimetype="text/calendar",
        headers={"Content-Disposition": "attachment; filename=lesson-%d.ics" % id},
    )


@app.get("/api/lessons.json")
def api_lessons():
    return jsonify(db.list_lessons())


@app.post("/lesson/<int:id>/upload")
def upload_attachment(id):
    lesson = db.get_lesson(id)
    if lesson is None:
        abort(404)
    f = request.files["file"]
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    path = storage.save_attachment(UPLOAD_DIR, f)
    db.set_attachment(id, f.filename, path)
    return redirect(url_for("lesson_card", id=id), 303)


@app.get("/lesson/<int:id>/file")
def download_attachment(id):
    lesson = db.get_lesson(id)
    if lesson is None or not lesson["file_path"]:
        abort(404)
    return send_file(lesson["file_path"], as_attachment=True, download_name=lesson["file_name"])
