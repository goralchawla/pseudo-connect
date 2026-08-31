from __future__ import annotations

import os
import re
import sqlite3
import uuid
from datetime import datetime
from functools import wraps
from pathlib import Path

from flask import (
    Flask,
    abort,
    flash,
    g,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
DB_PATH = DATA_DIR / "pseudo_connect.db"

DATA_DIR.mkdir(exist_ok=True)
UPLOAD_DIR.mkdir(exist_ok=True)

SUBJECTS = [
    {"id": "java", "label": "Java", "blurb": "OOP, collections, and exam-ready patterns.", "tone": "copper"},
    {"id": "webdev", "label": "Web Dev", "blurb": "HTML, CSS, JS, and how pages actually work.", "tone": "teal"},
    {"id": "maths", "label": "Maths", "blurb": "Calculus, algebra, and the step you missed.", "tone": "ink"},
    {"id": "physics", "label": "Physics", "blurb": "Mechanics, waves, and intuition for formulas.", "tone": "gold"},
]
SUBJECT_IDS = {s["id"] for s in SUBJECTS}

ALLOWED_EXTENSIONS = {
    "png",
    "jpg",
    "jpeg",
    "gif",
    "webp",
    "pdf",
    "txt",
    "doc",
    "docx",
    "zip",
    "py",
    "java",
    "html",
    "css",
    "js",
    "c",
    "cpp",
}

IMAGE_EXTS = {"png", "jpg", "jpeg", "gif", "webp"}

FOUL_WORDS = {
    "idiot",
    "stupid",
    "dumb",
    "hate",
    "kill",
    "shut up",
    "useless",
    "fool",
    "moron",
    "crap",
    "damn",
    "hell",
}

ALIAS_WORDS = [
    ("Quiet", "Maple", "Silver", "Hidden", "Soft", "Bright", "Night", "Paper"),
    ("Kite", "Comet", "Fox", "Harbor", "Nettle", "Lantern", "Drift", "Quill"),
]

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "pseudo-connect-dev-key")
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(_exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def make_alias(seed: str) -> str:
    n = abs(hash(seed))
    a = ALIAS_WORDS[0][n % len(ALIAS_WORDS[0])]
    b = ALIAS_WORDS[1][(n // 8) % len(ALIAS_WORDS[1])]
    return f"{a} {b}"


def scan_language(text: str) -> str | None:
    lowered = text.lower()
    hits = [w for w in FOUL_WORDS if w in lowered]
    if not hits:
        return None
    return "Possible foul language: " + ", ".join(sorted(set(hits)))


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def is_image_file(filename: str | None) -> bool:
    if not filename or "." not in filename:
        return False
    return filename.rsplit(".", 1)[1].lower() in IMAGE_EXTS
def save_upload(file_storage):
    if not file_storage or not file_storage.filename:
        return None, None
    if not allowed_file(file_storage.filename):
        raise ValueError("That file type is not allowed. Try an image, PDF, zip, or code file.")
    original = secure_filename(file_storage.filename)
    ext = original.rsplit(".", 1)[1].lower()
    filename = f"{uuid.uuid4().hex}.{ext}"
    file_storage.save(UPLOAD_DIR / filename)
    return filename, original
def ensure_answer_file_columns(db: sqlite3.Connection):
    cols = {row[1] for row in db.execute("PRAGMA table_info(answers)").fetchall()}
    if "filename" not in cols:
        db.execute("ALTER TABLE answers ADD COLUMN filename TEXT")
    if "original_filename" not in cols:
        db.execute("ALTER TABLE answers ADD COLUMN original_filename TEXT")
    db.commit()

def init_db():
    db = sqlite3.connect(DB_PATH)
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL,
            subjects TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS doubts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            subject TEXT NOT NULL,
            title TEXT NOT NULL,
            body TEXT NOT NULL,
            anonymous INTEGER NOT NULL DEFAULT 1,
            alias TEXT NOT NULL,
            filename TEXT,
            original_filename TEXT,
            status TEXT NOT NULL DEFAULT 'open',
            flagged INTEGER NOT NULL DEFAULT 0,
            flag_reason TEXT,
            hidden INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            FOREIGN KEY(student_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS answers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            doubt_id INTEGER NOT NULL,
            teacher_id INTEGER NOT NULL,
            body TEXT NOT NULL,
            filename TEXT,
            original_filename TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(doubt_id) REFERENCES doubts(id),
            FOREIGN KEY(teacher_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS availability (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            teacher_id INTEGER NOT NULL,
            weekday TEXT NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,
            mode TEXT NOT NULL,
            FOREIGN KEY(teacher_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS meetings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            doubt_id INTEGER NOT NULL,
            student_id INTEGER NOT NULL,
            teacher_id INTEGER,
            kind TEXT NOT NULL,
            status TEXT NOT NULL,
            slot TEXT,
            meet_link TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(doubt_id) REFERENCES doubts(id),
            FOREIGN KEY(student_id) REFERENCES users(id),
            FOREIGN KEY(teacher_id) REFERENCES users(id)
        );
        """
    )

    existing = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    if existing == 0:
        users = [
            ("Campus Admin", "admin@college.edu", "admin123", "admin", ""),
            ("Prof. Vikram Rao", "java.faculty@college.edu", "teacher123", "teacher", "java"),
            ("Prof. Meera Iyer", "web.faculty@college.edu", "teacher123", "teacher", "webdev"),
            ("Prof. Arun Desai", "maths.faculty@college.edu", "teacher123", "teacher", "maths"),
            ("Prof. Kavita Joshi", "physics.faculty@college.edu", "teacher123", "teacher", "physics"),
            ("Rahul Mehta", "rahul@college.edu", "student123", "student", ""),
            ("Ananya Sharma", "ananya@college.edu", "student123", "student", ""),
            ("Priya Nair", "priya@college.edu", "student123", "student", ""),
        ]
        db.executemany(
            "INSERT INTO users (name, email, password_hash, role, subjects) VALUES (?, ?, ?, ?, ?)",
            [
                (name, email, generate_password_hash(password, method="pbkdf2:sha256"), role, subjects)
                for name, email, password, role, subjects in users
            ],
        )
        student = db.execute("SELECT id FROM users WHERE email = 'rahul@college.edu'").fetchone()[0]
        alias = make_alias("seed-java")
        db.execute(
            """
            INSERT INTO doubts (student_id, subject, title, body, anonymous, alias, status, flagged, created_at)
            VALUES (?, 'java', 'Why does ArrayList grow by 1.5x?',
                    'I keep mixing up capacity vs size. Can someone walk through what happens when we add the 11th element to a default ArrayList?',
                    1, ?, 'open', 0, ?)
            """,
            (student, alias, now_iso()),
        )
        db.execute(
            """
            INSERT INTO availability (teacher_id, weekday, start_time, end_time, mode)
            SELECT id, 'Tuesday', '14:00', '16:00', 'both' FROM users WHERE email = 'java.faculty@college.edu'
            """
        )
        db.execute(
            """
            INSERT INTO availability (teacher_id, weekday, start_time, end_time, mode)
            SELECT id, 'Friday', '11:00', '13:00', 'campus' FROM users WHERE email = 'maths.faculty@college.edu'
            """
        )
        db.commit()
    ensure_answer_file_columns(db)    
    db.close()


def current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None
    return get_db().execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()


def login_required(role=None):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            user = current_user()
            if not user:
                flash("Please sign in with your college email.", "warn")
                return redirect(url_for("login"))
            if role and user["role"] != role:
                abort(403)
            return fn(*args, **kwargs)

        return wrapper

    return decorator


@app.context_processor
def inject_globals():
    return {
        "user": current_user(),
        "subjects": SUBJECTS,
        "subject_map": {s["id"]: s for s in SUBJECTS},
        "is_image_file": is_image_file,
    }


def display_name_for_teacher(doubt) -> str:
    if doubt["anonymous"]:
        return doubt["alias"]
    student = get_db().execute("SELECT name FROM users WHERE id = ?", (doubt["student_id"],)).fetchone()
    return student["name"] if student else doubt["alias"]


def teacher_for_subject(subject: str):
    return get_db().execute(
        "SELECT * FROM users WHERE role = 'teacher' AND subjects = ?", (subject,)
    ).fetchone()


@app.route("/")
def index():
    if current_user():
        return redirect(url_for(f"{current_user()['role']}_home"))
    return render_template("index.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user():
        return redirect(url_for(f"{current_user()['role']}_home"))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        if not re.fullmatch(r"[^@]+@college\.edu", email):
            flash("Use your registered college email (it must end with @college.edu).", "warn")
            return render_template("login.html")
        row = get_db().execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if not row or not check_password_hash(row["password_hash"], password):
            flash("That email is not registered on the portal, or the password is wrong.", "warn")
            return render_template("login.html")
        session["user_id"] = row["id"]
        flash(f"Welcome back, {row['name'].split()[0]}.", "ok")
        return redirect(url_for(f"{row['role']}_home"))
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("Signed out. Your doubts stay on the portal.", "ok")
    return redirect(url_for("index"))


@app.route("/student")
@login_required("student")
def student_home():
    user = current_user()
    doubts = get_db().execute(
        "SELECT * FROM doubts WHERE student_id = ? ORDER BY id DESC", (user["id"],)
    ).fetchall()
    return render_template("student/home.html", doubts=doubts)


@app.route("/student/ask", methods=["GET", "POST"])
@login_required("student")
def student_ask():
    user = current_user()
    if request.method == "POST":
        subject = request.form.get("subject", "")
        title = request.form.get("title", "").strip()
        body = request.form.get("body", "").strip()
        anonymous = 1 if request.form.get("anonymous") == "on" else 0
        if subject not in SUBJECT_IDS or not title or not body:
            flash("Pick a subject and write both a title and the doubt itself.", "warn")
            return render_template("student/ask.html")

        
        file = request.files.get("attachment")

        try:
            filename, original = save_upload(file)
        except ValueError as exc:
            flash(str(exc), "warn")
            return render_template("student/ask.html")

        flag_reason = scan_language(f"{title} {body}")
        alias = make_alias(f"{user['id']}-{title}-{now_iso()}")
        db = get_db()
        db.execute(
            """
            INSERT INTO doubts (student_id, subject, title, body, anonymous, alias, filename, original_filename,
                                status, flagged, flag_reason, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'open', ?, ?, ?)
            """,
            (
                user["id"],
                subject,
                title,
                body,
                anonymous,
                alias,
                filename,
                original,
                1 if flag_reason else 0,
                flag_reason,
                now_iso(),
            ),
        )
        db.commit()
        flash("Doubt sent. Your teacher sees it without campus gossip attached.", "ok")
        return redirect(url_for("student_home"))
    return render_template("student/ask.html")


@app.route("/student/doubt/<int:doubt_id>", methods=["GET", "POST"])
@login_required("student")
def student_doubt(doubt_id: int):
    user = current_user()
    db = get_db()
    doubt = db.execute(
        "SELECT * FROM doubts WHERE id = ? AND student_id = ?", (doubt_id, user["id"])
    ).fetchone()
    if not doubt:
        abort(404)
    if request.method == "POST":
        extra = request.form.get("followup", "").strip()
        if extra:
            flag_reason = scan_language(extra)
            new_body = doubt["body"] + "\n\n— Follow-up —\n" + extra
            flagged = 1 if (doubt["flagged"] or flag_reason) else 0
            reason = doubt["flag_reason"] or flag_reason
            db.execute(
                "UPDATE doubts SET body = ?, status = 'open', flagged = ?, flag_reason = ? WHERE id = ?",
                (new_body, flagged, reason, doubt_id),
            )
            db.commit()
            flash("Follow-up added. The teacher will see the extra question.", "ok")
            return redirect(url_for("student_doubt", doubt_id=doubt_id))
    answers = db.execute(
        """
        SELECT a.*, u.name AS teacher_name
        FROM answers a JOIN users u ON u.id = a.teacher_id
        WHERE a.doubt_id = ? ORDER BY a.id
        """,
        (doubt_id,),
    ).fetchall()
    meetings = db.execute(
        "SELECT * FROM meetings WHERE doubt_id = ? ORDER BY id DESC", (doubt_id,)
    ).fetchall()
    teacher = teacher_for_subject(doubt["subject"])
    slots = []
    if teacher:
        slots = db.execute(
            "SELECT * FROM availability WHERE teacher_id = ? ORDER BY weekday", (teacher["id"],)
        ).fetchall()
    return render_template(
        "student/doubt.html",
        doubt=doubt,
        answers=answers,
        meetings=meetings,
        slots=slots,
        teacher=teacher,
    )


@app.route("/student/doubt/<int:doubt_id>/meet", methods=["POST"])
@login_required("student")
def student_meet(doubt_id: int):
    user = current_user()
    db = get_db()
    doubt = db.execute(
        "SELECT * FROM doubts WHERE id = ? AND student_id = ?", (doubt_id, user["id"])
    ).fetchone()
    if not doubt:
        abort(404)
    kind = request.form.get("kind")
    slot = request.form.get("slot") or None
    if kind not in {"google", "campus"}:
        flash("Choose Google Meet or a campus sit-down.", "warn")
        return redirect(url_for("student_doubt", doubt_id=doubt_id))
    teacher = teacher_for_subject(doubt["subject"])
    db.execute(
        """
        INSERT INTO meetings (doubt_id, student_id, teacher_id, kind, status, slot, created_at)
        VALUES (?, ?, ?, ?, 'requested', ?, ?)
        """,
        (doubt_id, user["id"], teacher["id"] if teacher else None, kind, slot, now_iso()),
    )
    db.commit()
    flash("Meeting requested. You stay behind your alias until you choose otherwise.", "ok")
    return redirect(url_for("student_doubt", doubt_id=doubt_id))


@app.route("/teacher")
@login_required("teacher")
def teacher_home():
    user = current_user()
    subject = user["subjects"]
    doubts = get_db().execute(
        """
        SELECT d.*, u.name AS student_name
        FROM doubts d JOIN users u ON u.id = d.student_id
        WHERE d.subject = ? AND d.hidden = 0
        ORDER BY d.id DESC
        """,
        (subject,),
    ).fetchall()
    meetings = get_db().execute(
        """
        SELECT m.*, d.title, d.alias, d.anonymous, u.name AS student_name
        FROM meetings m
        JOIN doubts d ON d.id = m.doubt_id
        JOIN users u ON u.id = m.student_id
        WHERE m.teacher_id = ?
        ORDER BY m.id DESC
        """,
        (user["id"],),
    ).fetchall()
    slots = get_db().execute(
        "SELECT * FROM availability WHERE teacher_id = ? ORDER BY id", (user["id"],)
    ).fetchall()
    return render_template("teacher/home.html", doubts=doubts, meetings=meetings, slots=slots)


@app.route("/teacher/availability", methods=["POST"])
@login_required("teacher")
def teacher_availability():
    user = current_user()
    weekday = request.form.get("weekday", "").strip()
    start_time = request.form.get("start_time", "").strip()
    end_time = request.form.get("end_time", "").strip()
    mode = request.form.get("mode", "both")
    if weekday and start_time and end_time:
        db = get_db()
        db.execute(
            "INSERT INTO availability (teacher_id, weekday, start_time, end_time, mode) VALUES (?, ?, ?, ?, ?)",
            (user["id"], weekday, start_time, end_time, mode),
        )
        db.commit()
        flash("Availability published for students.", "ok")
    return redirect(url_for("teacher_home"))


@app.route("/teacher/doubt/<int:doubt_id>", methods=["GET", "POST"])
@login_required("teacher")
def teacher_doubt(doubt_id: int):
    user = current_user()
    db = get_db()
    doubt = db.execute(
        """
        SELECT d.*, u.name AS student_name
        FROM doubts d JOIN users u ON u.id = d.student_id
        WHERE d.id = ? AND d.hidden = 0
        """,
        (doubt_id,),
    ).fetchone()
    if not doubt or doubt["subject"] != user["subjects"]:
        abort(404)
    if request.method == "POST":
        body = request.form.get("answer", "").strip()

        snippet = request.files.get("snippet")
        try:
            filename, original = save_upload(snippet)
        except ValueError as exc:
            flash(str(exc), "warn")

            return redirect(url_for("teacher_doubt", doubt_id=doubt_id))

        if not body and not filename:
            flash("Write an answer or attach a page snippet.", "warn")
            return redirect(url_for("teacher_doubt", doubt_id=doubt_id))
        db.execute(
            """
            INSERT INTO answers (doubt_id, teacher_id, body, filename, original_filename, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (doubt_id, user["id"], body, filename, original, now_iso()),
        )
        db.execute("UPDATE doubts SET status = 'answered' WHERE id = ?", (doubt_id,))
        db.commit()
        flash("Answer posted. It now appears on the student's portal.", "ok")
        return redirect(url_for("teacher_doubt", doubt_id=doubt_id))
    
    answers = db.execute(
        "SELECT * FROM answers WHERE doubt_id = ? ORDER BY id", (doubt_id,)
    ).fetchall()
    shown = display_name_for_teacher(doubt)
    return render_template("teacher/doubt.html", doubt=doubt, answers=answers, shown=shown)


@app.route("/teacher/meet/<int:meet_id>", methods=["POST"])
@login_required("teacher")
def teacher_meet(meet_id: int):
    user = current_user()
    db = get_db()
    meeting = db.execute(
        "SELECT * FROM meetings WHERE id = ? AND teacher_id = ?", (meet_id, user["id"])
    ).fetchone()
    if not meeting:
        abort(404)
    action = request.form.get("action")
    if action == "accept":
        link = None
        if meeting["kind"] == "google":
            token = uuid.uuid4().hex[:3] + "-" + uuid.uuid4().hex[:4] + "-" + uuid.uuid4().hex[:3]
            link = f"https://meet.google.com/{token}"
        db.execute(
            "UPDATE meetings SET status = 'accepted', meet_link = ? WHERE id = ?",
            (link, meet_id),
        )
        flash("Meeting accepted. The student stays listed as their alias.", "ok")
    else:
        db.execute("UPDATE meetings SET status = 'declined' WHERE id = ?", (meet_id,))
        flash("Meeting declined. You can add more availability instead.", "ok")
    db.commit()
    return redirect(url_for("teacher_home"))


@app.route("/admin")
@login_required("admin")
def admin_home():
    db = get_db()
    doubts = db.execute(
        """
        SELECT d.*, u.name AS student_name, u.email AS student_email
        FROM doubts d JOIN users u ON u.id = d.student_id
        ORDER BY d.flagged DESC, d.id DESC
        """
    ).fetchall()
    meetings = db.execute(
        """
        SELECT m.*, d.title, u.name AS student_name
        FROM meetings m
        JOIN doubts d ON d.id = m.doubt_id
        JOIN users u ON u.id = m.student_id
        ORDER BY m.id DESC
        """
    ).fetchall()
    users = db.execute("SELECT id, name, email, role, subjects FROM users ORDER BY role, name").fetchall()
    stats = {
        "students": db.execute("SELECT COUNT(*) FROM users WHERE role = 'student'").fetchone()[0],
        "teachers": db.execute("SELECT COUNT(*) FROM users WHERE role = 'teacher'").fetchone()[0],
        "doubts": db.execute("SELECT COUNT(*) FROM doubts").fetchone()[0],
        "flagged": db.execute("SELECT COUNT(*) FROM doubts WHERE flagged = 1").fetchone()[0],
    }
    return render_template(
        "admin/home.html", doubts=doubts, meetings=meetings, users=users, stats=stats
    )


@app.route("/admin/doubt/<int:doubt_id>", methods=["GET", "POST"])
@login_required("admin")
def admin_doubt(doubt_id: int):
    db = get_db()
    doubt = db.execute(
        """
        SELECT d.*, u.name AS student_name, u.email AS student_email
        FROM doubts d JOIN users u ON u.id = d.student_id
        WHERE d.id = ?
        """,
        (doubt_id,),
    ).fetchone()
    if not doubt:
        abort(404)
    if request.method == "POST":
        action = request.form.get("action")
        if action == "hide":
            db.execute("UPDATE doubts SET hidden = 1 WHERE id = ?", (doubt_id,))
            flash("Doubt hidden from teachers after review.", "ok")
        elif action == "clear":
            db.execute("UPDATE doubts SET flagged = 0, flag_reason = NULL, hidden = 0 WHERE id = ?", (doubt_id,))
            flash("Flag cleared. Teachers can see it again.", "ok")
        elif action == "flag":
            db.execute(
                "UPDATE doubts SET flagged = 1, flag_reason = ? WHERE id = ?",
                ("Manually flagged by admin", doubt_id),
            )
            flash("Marked for review.", "ok")
        db.commit()
        return redirect(url_for("admin_doubt", doubt_id=doubt_id))
    answers = db.execute(
        "SELECT a.*, u.name AS teacher_name FROM answers a JOIN users u ON u.id = a.teacher_id WHERE a.doubt_id = ?",
        (doubt_id,),
    ).fetchall()
    return render_template("admin/doubt.html", doubt=doubt, answers=answers)


@app.route("/uploads/<path:filename>")
@login_required()
def uploaded_file(filename: str):
    return send_from_directory(UPLOAD_DIR, filename)


@app.errorhandler(403)
def forbidden(_e):
    return render_template("error.html", code=403, message="This desk is for another role."), 403


@app.errorhandler(404)
def not_found(_e):
    return render_template("error.html", code=404, message="That page is not on the portal."), 404


init_db()

if __name__ == "__main__":
    app.run(debug=True, port=5050)
