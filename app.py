import os
from functools import wraps
from pathlib import Path

import google.generativeai as genai
from dotenv import load_dotenv
from flask import Flask, flash, jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from database import get_db, init_app

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent


def create_app():
    app = Flask(__name__)
    app.config["SECRET_KEY"] = "accesslearn-dev-secret-change-before-deploy"
    init_app(app)

    def current_user():
        user_id = session.get("user_id")
        if not user_id:
            return None
        return get_db().execute(
            "SELECT * FROM users WHERE id = ?", (user_id,)
        ).fetchone()

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

    def ai_answer(message):
        message = message.strip()
        if not message:
            return "Please ask a clear question."

        api_key = os.getenv("GEMINI_API_KEY")

        if api_key:
            try:
                genai.configure(api_key=api_key)
                model = genai.GenerativeModel("gemini-2.0-flash")

                prompt = f"""
You are AccessLearn AI Assistant.
Answer the user's question in simple student-friendly language.
If the question is educational, explain with examples.
If it is general, answer politely and helpfully.

Question:
{message}
"""
                response = model.generate_content(prompt)
                return response.text

            except Exception:
                pass

        return f"""AccessLearn AI Assistant:

Here is a simple student-friendly explanation of: {message}

This topic can be understood by:
1. Learning the basic definition.
2. Breaking it into small points.
3. Studying one simple example.
4. Revising key terms.
5. Testing yourself with a short quiz.

Note: Live AI response is temporarily unavailable, so this fallback learning response is shown."""

    def summarize_text(text):
        text = " ".join(text.split())
        if not text:
            return "Please enter notes to summarize."

        sentences = [
            s.strip()
            for s in text.replace("!", ".").replace("?", ".").split(".")
            if s.strip()
        ]

        if not sentences:
            return text[:350] + ("..." if len(text) > 350 else "")

        summary_points = sentences[:4]
        return "\n".join([f"• {point}." for point in summary_points])

    def generate_questions(topic):
        topic = topic.strip() or "General Learning"
        return [
            {
                "question": f"What is the first step to understand {topic}?",
                "options": ["Read the basics", "Ignore examples", "Skip revision", "Avoid practice"],
                "answer_index": 0,
                "explanation": "Understanding basics is the first step before solving advanced problems."
            },
            {
                "question": "Which method improves long-term retention?",
                "options": ["One-time reading", "Spaced revision", "No testing", "Multitasking"],
                "answer_index": 1,
                "explanation": "Spaced revision helps the brain remember concepts for a longer time."
            },
            {
                "question": f"How can a student check understanding of {topic}?",
                "options": ["Explain in own words", "Only copy notes", "Avoid questions", "Memorize blindly"],
                "answer_index": 0,
                "explanation": "Explaining in your own words confirms real understanding."
            },
            {
                "question": "Why are quizzes useful in learning?",
                "options": ["They identify weak areas", "They waste time", "They replace learning", "They remove revision"],
                "answer_index": 0,
                "explanation": "Quizzes help students identify strengths and weaknesses."
            },
            {
                "question": "What does AccessLearn aim to support?",
                "options": ["Inclusive digital learning", "Only entertainment", "Offline games", "Shopping"],
                "answer_index": 0,
                "explanation": "AccessLearn focuses on education technology and digital inclusion."
            }
        ]

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
                cursor = db.execute(
                    "INSERT INTO users (name, email, password_hash, role) VALUES (?, ?, ?, ?)",
                    (name, email, generate_password_hash(password), role),
                )
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

            user = get_db().execute(
                "SELECT * FROM users WHERE email = ?", (email,)
            ).fetchone()

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

        total_quizzes = db.execute(
            "SELECT COUNT(*) AS c FROM quiz_results WHERE student_id = ?",
            (user["id"],),
        ).fetchone()["c"]

        avg_score_row = db.execute(
            "SELECT AVG(CAST(score AS FLOAT)/total_questions) AS avg FROM quiz_results WHERE student_id = ?",
            (user["id"],),
        ).fetchone()

        avg_score = round((avg_score_row["avg"] or 0) * 100, 1)

        recent_notes = db.execute(
            """
            SELECT n.*, u.name AS teacher_name
            FROM notes n
            LEFT JOIN users u ON n.teacher_id = u.id
            ORDER BY n.created_at DESC
            LIMIT 5
            """
        ).fetchall()

        recent_results = db.execute(
            "SELECT * FROM quiz_results WHERE student_id = ? ORDER BY created_at DESC LIMIT 5",
            (user["id"],),
        ).fetchall()

        if user["role"] == "teacher":
            teacher_notes = db.execute(
                "SELECT COUNT(*) AS c FROM notes WHERE teacher_id = ?",
                (user["id"],),
            ).fetchone()["c"]

            return render_template(
                "teacher_dashboard.html",
                total_notes=total_notes,
                teacher_notes=teacher_notes,
                recent_notes=recent_notes,
            )

        return render_template(
            "student_dashboard.html",
            total_notes=total_notes,
            total_quizzes=total_quizzes,
            avg_score=avg_score,
            recent_notes=recent_notes,
            recent_results=recent_results,
        )

    @app.route("/notes")
    @login_required
    def notes():
        rows = get_db().execute(
            """
            SELECT n.*, u.name AS teacher_name
            FROM notes n
            LEFT JOIN users u ON n.teacher_id = u.id
            ORDER BY n.created_at DESC
            """
        ).fetchall()
        return render_template("notes.html", notes=rows)

    @app.route("/teacher/upload", methods=["GET", "POST"])
    @login_required
    @role_required("teacher")
    def upload_notes():
        if request.method == "POST":
            title = request.form.get("title", "").strip()
            subject = request.form.get("subject", "").strip()
            description = request.form.get("description", "").strip()
            content = request.form.get("content", "").strip()

            if not title or not subject or not content:
                flash("Title, subject, and content are required.", "danger")
                return render_template("upload_notes.html")

            db = get_db()
            db.execute(
                "INSERT INTO notes (teacher_id, title, subject, description, content) VALUES (?, ?, ?, ?, ?)",
                (session["user_id"], title, subject, description, content),
            )
            db.commit()

            flash("Notes uploaded successfully.", "success")
            return redirect(url_for("notes"))

        return render_template("upload_notes.html")
        @app.route("/teacher/delete-note/<int:note_id>")
@login_required
@role_required("teacher")
def delete_note(note_id):
    db = get_db()

    db.execute(
        "DELETE FROM notes WHERE id = ? AND teacher_id = ?",
        (note_id, session["user_id"])
    )

    db.commit()

    flash("Note deleted successfully.", "success")

    return redirect(url_for("notes"))

    @app.post("/api/generate_notes")
    @login_required
    def generate_notes():
        data = request.get_json(force=True) or {}
        topic = data.get("topic", "").strip()

        if not topic:
            return jsonify({"notes": "Please enter a topic."})

        notes = f"""# {topic}

## Introduction
{topic} is an important educational topic that helps students understand core concepts clearly.

## Key Concepts
- Basic definition of {topic}
- Important terms and principles
- Examples for better understanding
- Applications in real life
- Revision points for exams

## Example
A student can understand {topic} better by reading definitions, practicing examples, and testing knowledge through quizzes.

## Applications
{topic} can be applied in academic learning, exam preparation, practical projects, and skill development.

## Summary
In short, {topic} should be learned step by step by understanding concepts, revising key points, and practicing related questions.
"""

        return jsonify({"notes": notes})

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
        db.execute(
            "INSERT INTO chat_logs (user_id, message, response) VALUES (?, ?, ?)",
            (session["user_id"], message, reply),
        )
        db.commit()

        return jsonify({"reply": reply})

    @app.post("/api/summarize")
    @login_required
    def api_summarize():
        data = request.get_json(force=True) or {}
        text = data.get("text", "")
        summary = summarize_text(text)

        db = get_db()
        db.execute(
            "INSERT INTO summaries (user_id, original_text, summary) VALUES (?, ?, ?)",
            (session["user_id"], text, summary),
        )
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
        db.execute(
            "INSERT INTO quiz_results (student_id, username, topic, score, total_questions) VALUES (?, ?, ?, ?, ?)",
            (user["id"], user["name"], topic, score, total_questions),
        )
        db.commit()

        return jsonify({"success": True})

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
