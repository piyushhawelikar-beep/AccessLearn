import os
from functools import wraps
from pathlib import Path
from datetime import datetime

try:
    import google.generativeai as genai
except Exception:
    genai = None

from dotenv import load_dotenv
from flask import Flask, flash, jsonify, redirect, render_template, request, session, url_for, send_from_directory
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

from database import get_db, init_app

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "static" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_EXTENSIONS = {"pdf", "doc", "docx", "ppt", "pptx", "txt", "mp4", "webm", "mov", "png", "jpg", "jpeg"}


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def create_app():
    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "accesslearn-dev-secret-change-before-deploy")
    app.config["UPLOAD_FOLDER"] = str(UPLOAD_DIR)
    app.config["MAX_CONTENT_LENGTH"] = 60 * 1024 * 1024  # 60 MB
    init_app(app)

    def ensure_runtime_schema():
        """Create/upgrade tables without deleting existing data."""
        db = get_db()
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL CHECK (role IN ('student', 'teacher')),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                teacher_id INTEGER,
                title TEXT NOT NULL,
                subject TEXT NOT NULL,
                description TEXT,
                content TEXT,
                file_filename TEXT,
                file_original_name TEXT,
                file_type TEXT,
                resource_link TEXT,
                video_link TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (teacher_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS quiz_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER,
                username TEXT,
                topic TEXT NOT NULL,
                score INTEGER NOT NULL,
                total_questions INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (student_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS chat_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                message TEXT NOT NULL,
                response TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS summaries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                original_text TEXT NOT NULL,
                summary TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS study_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER NOT NULL,
                note_id INTEGER NOT NULL,
                time_spent INTEGER NOT NULL DEFAULT 0,
                viewed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (student_id) REFERENCES users(id),
                FOREIGN KEY (note_id) REFERENCES notes(id)
            );

            CREATE TABLE IF NOT EXISTS meetings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                teacher_id INTEGER,
                title TEXT NOT NULL,
                meeting_date TEXT,
                meeting_time TEXT,
                meeting_link TEXT NOT NULL,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (teacher_id) REFERENCES users(id)
            );
            """
        )
        # Safe migrations for old DBs
        for column_sql in [
            "ALTER TABLE notes ADD COLUMN file_filename TEXT",
            "ALTER TABLE notes ADD COLUMN file_original_name TEXT",
            "ALTER TABLE notes ADD COLUMN file_type TEXT",
            "ALTER TABLE notes ADD COLUMN resource_link TEXT",
            "ALTER TABLE notes ADD COLUMN video_link TEXT",
        ]:
            try:
                db.execute(column_sql)
            except Exception:
                pass
        db.commit()

    with app.app_context():
        ensure_runtime_schema()

    def current_user():
        user_id = session.get("user_id")
        if not user_id:
            return None
        return get_db().execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()

    @app.context_processor
    def inject_user():
        return {"current_user": current_user()}

    def login_required(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not session.get("user_id"):
                flash("Please login to continue.", "warning")
                return redirect(url_for("login"))
            return view(*args, **kwargs)
        return wrapped

    def role_required(role):
        def decorator(view):
            @wraps(view)
            def wrapped(*args, **kwargs):
                user = current_user()
                if not user:
                    return redirect(url_for("login"))
                if user["role"] != role:
                    flash("You do not have permission to access this page.", "danger")
                    return redirect(url_for("dashboard"))
                return view(*args, **kwargs)
            return wrapped
        return decorator

    def fallback_answer(message: str) -> str:
        msg = message.lower().strip()
        if "ohm" in msg:
            return """Ohm's Law states that voltage is directly proportional to current when resistance is constant.\n\nFormula: V = I × R\n\nWhere:\n• V = Voltage\n• I = Current\n• R = Resistance\n\nExample: If current is 2A and resistance is 5Ω, then voltage = 2 × 5 = 10V."""
        if "dbms" in msg or "database" in msg:
            return """A DBMS (Database Management System) is software used to store, organize, manage, and retrieve data.\n\nExamples: SQLite, MySQL, PostgreSQL and Oracle.\n\nIn AccessLearn, the database stores users, teacher notes, summaries, chat logs, study time and quiz results."""
        if "python" in msg:
            return """Python is a high-level programming language known for simple syntax and readability.\n\nIt is used in web development, AI/ML, data science, automation and scripting."""
        if "artificial intelligence" in msg or " ai" in f" {msg}":
            return """Artificial Intelligence is a branch of computer science that enables machines to perform tasks that usually require human intelligence.\n\nExamples include chatbots, recommendation systems, voice assistants and self-driving vehicles."""
        return f"""AccessLearn AI Assistant:\n\nHere is a simple student-friendly explanation of: {message}\n\nTo learn this topic effectively:\n1. Understand the basic definition.\n2. Break the topic into smaller concepts.\n3. Study one simple example.\n4. Revise important keywords.\n5. Test yourself with a short quiz.\n\nNote: Live AI may be temporarily unavailable due to API limits, so this reliable educational fallback is shown."""

    def ai_answer(message):
        message = message.strip()
        if not message:
            return "Please ask a clear question."
        api_key = os.getenv("GEMINI_API_KEY")
        if api_key and genai is not None:
            try:
                genai.configure(api_key=api_key)
                model = genai.GenerativeModel("gemini-2.0-flash")
                prompt = f"""
You are AccessLearn AI Assistant. Answer in simple student-friendly language.
For educational questions, include a definition, key points and one example.
Keep the answer clear and useful.

Question: {message}
"""
                response = model.generate_content(prompt)
                if getattr(response, "text", None):
                    return response.text
            except Exception:
                pass
        return fallback_answer(message)

    def summarize_text(text):
        clean_text = " ".join(text.split())
        if not clean_text:
            return "Please enter notes to summarize."
        sentences = [s.strip() for s in clean_text.replace("!", ".").replace("?", ".").split(".") if s.strip()]
        if not sentences:
            short = clean_text[:500] + ("..." if len(clean_text) > 500 else "")
            return f"Key Points:\n• {short}\n\nQuick Revision Notes:\n• Read the topic carefully.\n• Mark important terms.\n• Practice questions after revision."
        key_points = sentences[:5]
        important_terms = []
        for word in clean_text.replace(',', ' ').replace('.', ' ').split():
            w = word.strip(':-()[]{}').title()
            if len(w) > 5 and w not in important_terms:
                important_terms.append(w)
            if len(important_terms) >= 6:
                break
        important_lines = [f"• {term}" for term in important_terms] if important_terms else ["• Main definitions and examples"]
        output_lines = ["Key Points:"]
        output_lines.extend([f"• {point}." for point in key_points])
        output_lines.extend([
            "",
            "Important Concepts:",
        ])
        output_lines.extend(important_lines)
        output_lines.extend([
            "",
            "Quick Revision Notes:",
            "• Revise the definition first.",
            "• Focus on examples and applications.",
            "• Attempt a short quiz after studying.",
            "",
            "Final Summary:",
            f"• This content mainly explains {key_points[0][:120]}..." if key_points else "• Summary generated successfully."
        ])
        return "\n".join(output_lines)

    def generate_questions(topic):
        topic = topic.strip() or "General Learning"
        return [
            {"question": f"What is the best first step to understand {topic}?", "options": ["Read the basics", "Ignore examples", "Skip revision", "Avoid practice"], "answer_index": 0, "explanation": "Understanding basics is the first step before advanced learning."},
            {"question": "Which method improves long-term retention?", "options": ["One-time reading", "Spaced revision", "No testing", "Multitasking"], "answer_index": 1, "explanation": "Spaced revision helps students remember concepts longer."},
            {"question": f"How can a student check understanding of {topic}?", "options": ["Explain in own words", "Only copy notes", "Avoid questions", "Memorize blindly"], "answer_index": 0, "explanation": "Explaining in your own words confirms real understanding."},
            {"question": "Why are quizzes useful?", "options": ["They identify weak areas", "They waste time", "They replace learning", "They remove revision"], "answer_index": 0, "explanation": "Quizzes help identify strengths and weaknesses."},
            {"question": "What does AccessLearn support?", "options": ["Inclusive digital learning", "Only entertainment", "Offline games", "Shopping"], "answer_index": 0, "explanation": "AccessLearn focuses on education technology and digital inclusion."}
        ]

    def generate_notes_text(topic):
        topic = topic.strip() or "General Topic"
        return f"""# {topic}\n\n## Introduction\n{topic} is an important educational topic that helps learners understand concepts in a structured way.\n\n## Key Concepts\n• Definition and meaning of {topic}\n• Important terms and principles\n• Real-life examples\n• Applications in academics and projects\n• Revision and practice methods\n\n## Detailed Explanation\nTo study {topic}, students should first understand the basic definition, then learn important subtopics and finally apply the concept through examples and practice questions.\n\n## Example\nA student can improve understanding of {topic} by reading notes, summarizing important points, asking doubts through the chatbot and attempting quizzes.\n\n## Applications\n{topic} is useful for exam preparation, skill development, classroom learning, assignments and project-based learning.\n\n## Quick Revision\n• Learn definition\n• Revise key points\n• Practice questions\n• Discuss doubts\n• Track progress\n\n## Summary\n{topic} should be learned step by step through notes, summaries, examples and quizzes."""

    @app.route("/")
    def index():
        if session.get("user_id"):
            return redirect(url_for("dashboard"))
        return render_template("index.html")

    @app.route("/register", methods=["GET", "POST"])
    def register():
        if request.method == "POST":
            name = request.form.get("name", "").strip()
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "").strip()
            role = request.form.get("role", "student")
            if not name or not email or not password or role not in ("student", "teacher"):
                flash("Please fill all fields correctly.", "danger")
                return render_template("register.html")
            db = get_db()
            try:
                cursor = db.execute("INSERT INTO users (name, email, password_hash, role) VALUES (?, ?, ?, ?)", (name, email, generate_password_hash(password), role))
                db.commit()
            except Exception:
                flash("Email already exists or registration failed.", "danger")
                return render_template("register.html")
            session["user_id"] = cursor.lastrowid
            session["role"] = role
            flash("Registration successful.", "success")
            return redirect(url_for("dashboard"))
        return render_template("register.html")

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "").strip()
            user = get_db().execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
            if user and check_password_hash(user["password_hash"], password):
                session["user_id"] = user["id"]
                session["role"] = user["role"]
                flash("Login successful.", "success")
                return redirect(url_for("dashboard"))
            flash("Invalid email or password.", "danger")
        return render_template("login.html")

    @app.route("/logout")
    def logout():
        session.clear()
        flash("Logged out successfully.", "success")
        return redirect(url_for("index"))

    @app.route("/dashboard")
    @login_required
    def dashboard():
        user = current_user()
        db = get_db()
        total_notes = db.execute("SELECT COUNT(*) AS c FROM notes").fetchone()["c"]
        recent_notes = db.execute("SELECT n.*, u.name AS teacher_name FROM notes n LEFT JOIN users u ON n.teacher_id = u.id ORDER BY n.created_at DESC LIMIT 5").fetchall()
        meetings = db.execute("SELECT m.*, u.name AS teacher_name FROM meetings m LEFT JOIN users u ON m.teacher_id=u.id ORDER BY m.meeting_date DESC, m.meeting_time DESC LIMIT 5").fetchall()
        if user["role"] == "teacher":
            teacher_notes = db.execute("SELECT COUNT(*) AS c FROM notes WHERE teacher_id = ?", (user["id"],)).fetchone()["c"]
            total_students = db.execute("SELECT COUNT(*) AS c FROM users WHERE role='student'").fetchone()["c"]
            total_study_seconds = db.execute("SELECT COALESCE(SUM(time_spent),0) AS s FROM study_logs sl JOIN notes n ON sl.note_id=n.id WHERE n.teacher_id=?", (user["id"],)).fetchone()["s"]
            return render_template("teacher_dashboard.html", total_notes=total_notes, teacher_notes=teacher_notes, recent_notes=recent_notes, total_students=total_students, total_study_minutes=round(total_study_seconds/60, 1), meetings=meetings)
        total_quizzes = db.execute("SELECT COUNT(*) AS c FROM quiz_results WHERE student_id = ?", (user["id"],)).fetchone()["c"]
        avg_score_row = db.execute("SELECT AVG(CAST(score AS FLOAT)/total_questions) AS avg FROM quiz_results WHERE student_id = ?", (user["id"],)).fetchone()
        avg_score = round((avg_score_row["avg"] or 0) * 100, 1)
        recent_results = db.execute("SELECT * FROM quiz_results WHERE student_id = ? ORDER BY created_at DESC LIMIT 5", (user["id"],)).fetchall()
        return render_template("student_dashboard.html", total_notes=total_notes, total_quizzes=total_quizzes, avg_score=avg_score, recent_notes=recent_notes, recent_results=recent_results, meetings=meetings)

    @app.route("/notes")
    @login_required
    def notes():
        rows = get_db().execute("SELECT n.*, u.name AS teacher_name FROM notes n LEFT JOIN users u ON n.teacher_id = u.id ORDER BY n.created_at DESC").fetchall()
        return render_template("notes.html", notes=rows)

    @app.route("/notes/<int:note_id>")
    @login_required
    def note_detail(note_id):
        note = get_db().execute("SELECT n.*, u.name AS teacher_name FROM notes n LEFT JOIN users u ON n.teacher_id=u.id WHERE n.id=?", (note_id,)).fetchone()
        if not note:
            flash("Note not found.", "danger")
            return redirect(url_for("notes"))
        return render_template("note_detail.html", note=note)

    @app.route("/teacher/upload", methods=["GET", "POST"])
    @login_required
    @role_required("teacher")
    def upload_notes():
        if request.method == "POST":
            title = request.form.get("title", "").strip()
            subject = request.form.get("subject", "").strip()
            description = request.form.get("description", "").strip()
            content = request.form.get("content", "").strip()
            resource_link = request.form.get("resource_link", "").strip()
            video_link = request.form.get("video_link", "").strip()
            uploaded = request.files.get("resource_file")
            file_filename = file_original_name = file_type = None
            if uploaded and uploaded.filename:
                if not allowed_file(uploaded.filename):
                    flash("Unsupported file type.", "danger")
                    return render_template("upload_notes.html")
                file_original_name = uploaded.filename
                ext = uploaded.filename.rsplit('.', 1)[1].lower()
                file_type = ext
                file_filename = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{secure_filename(uploaded.filename)}"
                uploaded.save(UPLOAD_DIR / file_filename)
            if not title or not subject or not (content or file_filename or resource_link or video_link):
                flash("Title, subject, and at least one resource (notes/file/link/video) are required.", "danger")
                return render_template("upload_notes.html")
            db = get_db()
            db.execute("INSERT INTO notes (teacher_id, title, subject, description, content, file_filename, file_original_name, file_type, resource_link, video_link) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (session["user_id"], title, subject, description, content, file_filename, file_original_name, file_type, resource_link, video_link))
            db.commit()
            flash("Learning resource uploaded successfully.", "success")
            return redirect(url_for("notes"))
        return render_template("upload_notes.html")

    @app.route("/uploads/<path:filename>")
    @login_required
    def uploaded_file(filename):
        return send_from_directory(app.config["UPLOAD_FOLDER"], filename)

    @app.route("/teacher/delete/<int:note_id>")
    @login_required
    @role_required("teacher")
    def delete_note(note_id):
        db = get_db()
        db.execute("DELETE FROM notes WHERE id = ? AND teacher_id = ?", (note_id, session["user_id"]))
        db.commit()
        flash("Note deleted successfully.", "success")
        return redirect(url_for("notes"))

    @app.route("/teacher/edit/<int:note_id>", methods=["GET", "POST"])
    @login_required
    @role_required("teacher")
    def edit_note(note_id):
        db = get_db()
        note = db.execute("SELECT * FROM notes WHERE id = ? AND teacher_id = ?", (note_id, session["user_id"])).fetchone()
        if not note:
            flash("Note not found.", "danger")
            return redirect(url_for("notes"))
        if request.method == "POST":
            title = request.form.get("title", "").strip()
            subject = request.form.get("subject", "").strip()
            description = request.form.get("description", "").strip()
            content = request.form.get("content", "").strip()
            resource_link = request.form.get("resource_link", "").strip()
            video_link = request.form.get("video_link", "").strip()
            db.execute("UPDATE notes SET title=?, subject=?, description=?, content=?, resource_link=?, video_link=? WHERE id=? AND teacher_id=?", (title, subject, description, content, resource_link, video_link, note_id, session["user_id"]))
            db.commit()
            flash("Note updated successfully.", "success")
            return redirect(url_for("notes"))
        return render_template("edit_note.html", note=note)

    @app.route("/teacher/reports")
    @login_required
    @role_required("teacher")
    def teacher_reports():
        rows = get_db().execute("""
            SELECT sl.*, u.name AS student_name, n.title AS note_title, n.subject AS note_subject
            FROM study_logs sl
            JOIN users u ON sl.student_id = u.id
            JOIN notes n ON sl.note_id = n.id
            WHERE n.teacher_id = ?
            ORDER BY sl.viewed_at DESC
        """, (session["user_id"],)).fetchall()
        return render_template("teacher_reports.html", logs=rows)

    @app.route("/meetings", methods=["GET", "POST"])
    @login_required
    def meetings():
        db = get_db()
        user = current_user()
        if request.method == "POST":
            if user["role"] != "teacher":
                flash("Only teachers can create meetings.", "danger")
                return redirect(url_for("meetings"))
            title = request.form.get("title", "").strip()
            meeting_date = request.form.get("meeting_date", "").strip()
            meeting_time = request.form.get("meeting_time", "").strip()
            meeting_link = request.form.get("meeting_link", "").strip()
            description = request.form.get("description", "").strip()
            if not title or not meeting_link:
                flash("Meeting title and link are required.", "danger")
                return redirect(url_for("meetings"))
            db.execute("INSERT INTO meetings (teacher_id, title, meeting_date, meeting_time, meeting_link, description) VALUES (?, ?, ?, ?, ?, ?)", (user["id"], title, meeting_date, meeting_time, meeting_link, description))
            db.commit()
            flash("Meeting created successfully.", "success")
            return redirect(url_for("meetings"))
        rows = db.execute("SELECT m.*, u.name AS teacher_name FROM meetings m LEFT JOIN users u ON m.teacher_id=u.id ORDER BY m.meeting_date DESC, m.meeting_time DESC").fetchall()
        return render_template("meetings.html", meetings=rows)

    @app.post("/api/study-log")
    @login_required
    def api_study_log():
        data = request.get_json(silent=True) or request.form or {}
        note_id = int(data.get("note_id", 0) or 0)
        time_spent = int(data.get("time_spent", 0) or 0)
        if note_id > 0 and time_spent > 0:
            get_db().execute("INSERT INTO study_logs (student_id, note_id, time_spent) VALUES (?, ?, ?)", (session["user_id"], note_id, time_spent))
            get_db().commit()
        return jsonify({"success": True})

    @app.post("/api/generate_notes")
    @login_required
    def generate_notes():
        data = request.get_json(force=True) or {}
        topic = data.get("topic", "").strip()
        if not topic:
            return jsonify({"notes": "Please enter a topic."})
        return jsonify({"notes": generate_notes_text(topic)})

    @app.route("/chatbot")
    @login_required
    def chatbot_page():
        return render_template("chatbot.html")

    @app.route("/summarizer")
    @login_required
    def summarizer_page():
        return render_template("summarizer.html")

    @app.route("/quiz")
    @login_required
    def quiz_page():
        return render_template("quiz.html")

    @app.post("/api/chat")
    @login_required
    def api_chat():
        data = request.get_json(force=True) or {}
        message = data.get("message", "")
        reply = ai_answer(message)
        db = get_db()
        db.execute("INSERT INTO chat_logs (user_id, message, response) VALUES (?, ?, ?)", (session["user_id"], message, reply))
        db.commit()
        return jsonify({"reply": reply})

    @app.post("/api/summarize")
    @login_required
    def api_summarize():
        data = request.get_json(force=True) or {}
        text = data.get("text", "")
        summary = summarize_text(text)
        db = get_db()
        db.execute("INSERT INTO summaries (user_id, original_text, summary) VALUES (?, ?, ?)", (session["user_id"], text, summary))
        db.commit()
        return jsonify({"summary": summary})

    @app.post("/api/generate_quiz")
    @login_required
    def api_generate_quiz():
        data = request.get_json(force=True) or {}
        topic = data.get("topic", "General Learning")
        return jsonify({"questions": generate_questions(topic)})

    @app.post("/api/submit_quiz")
    @login_required
    def api_submit_quiz():
        data = request.get_json(force=True) or {}
        topic = data.get("topic", "General Learning")
        score = int(data.get("score", 0))
        total_questions = int(data.get("total_questions", 0))
        user = current_user()
        db = get_db()
        db.execute("INSERT INTO quiz_results (student_id, username, topic, score, total_questions) VALUES (?, ?, ?, ?, ?)", (user["id"], user["name"], topic, score, total_questions))
        db.commit()
        return jsonify({"success": True})

    return app


app = create_app()

if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=True)
