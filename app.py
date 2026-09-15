import os
import sqlite3
import smtplib
from email.mime.text import MIMEText
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

DATABASE = "tasks.db"
PRESIDENT_PIN = os.environ.get("PRESIDENT_PIN", "1234")
GMAIL_ADDRESS = os.environ.get("GMAIL_ADDRESS")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD")

# Map exact or case-insensitive assignee names to their target emails
EXEC_ROSTER = {
    "Mahir": "mahirasif2704@gmail.com",
    "1": "mahirasif2704@gmail.com",
    "test": "mahirasif2704@gmail.com",
    # Add additional executive members here:
    # "Name": "user@domain.com",
}

def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            assignee TEXT NOT NULL,
            department TEXT NOT NULL,
            status TEXT DEFAULT 'Pending',
            deadline TEXT
        )
    """)
    conn.commit()
    conn.close()

# Initialize database tables on worker startup
init_db()

def send_task_notification(assignee_name, task_title, department, deadline=None):
    if not GMAIL_ADDRESS or not GMAIL_APP_PASSWORD:
        print("Skipping email: GMAIL_ADDRESS or GMAIL_APP_PASSWORD not set in environment.", flush=True)
        return

    # Find recipient email with case-insensitive fallback[cite: 4]
    recipient_email = EXEC_ROSTER.get(assignee_name.strip())
    if not recipient_email:
        for name, email in EXEC_ROSTER.items():
            if name.lower() == assignee_name.strip().lower():
                recipient_email = email
                break

    if not recipient_email:
        print(f"Skipping email: No registered email address found for '{assignee_name}'.", flush=True)
        return

    deadline_text = f"Due Date: {deadline}\n" if deadline else ""
    email_body = f"""Hi {assignee_name},

You have been assigned a new task on the BSA Task Tracker:

📌 Task: {task_title}
🏢 Department: {department}
{deadline_text}
You can view and update your tasks here:
https://mahirc27.github.io/bsa-task-tracker/

— BSA Executive Board
"""

    msg = MIMEText(email_body)
    msg["Subject"] = f"📌 New Task Assigned: {task_title}"
    msg["From"] = f"BSA Tasks <{GMAIL_ADDRESS}>"
    msg["To"] = recipient_email

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=10) as server:
            server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
            server.send_message(msg)
        print(f"Email sent successfully to {recipient_email} via Gmail SMTP.", flush=True)
    except Exception as e:
        print(f"Gmail SMTP error: {e}", flush=True)

@app.route("/", methods=["GET"])
def health():
    return jsonify({"status": "ok", "message": "BSA Tasks API is online"}), 200

@app.route("/tasks", methods=["GET"])
def get_tasks():
    incoming_pin = request.args.get("pin")
    department = request.args.get("department")

    # If a PIN was provided in the query string, validate it
    if incoming_pin is not None:
        if incoming_pin.strip() != PRESIDENT_PIN:
            return jsonify({"error": "Unauthorized"}), 401

    # Restrict unrestricted all-task queries to authenticated President PIN requests
    if not department or department == "All":
        if not incoming_pin or incoming_pin.strip() != PRESIDENT_PIN:
            return jsonify({"error": "Unauthorized"}), 401

    conn = get_db_connection()
    cursor = conn.cursor()

    if department and department != "All":
        cursor.execute("SELECT * FROM tasks WHERE department = ?", (department,))
    else:
        cursor.execute("SELECT * FROM tasks")

    rows = cursor.fetchall()
    conn.close()

    tasks = [
        {
            "id": row["id"],
            "title": row["title"],
            "assignee": row["assignee"],
            "department": row["department"],
            "status": row["status"],
            "deadline": row["deadline"],
        }
        for row in rows
    ]
    return jsonify(tasks), 200

@app.route("/tasks", methods=["POST"])
def create_task():
    data = request.get_json() or {}
    incoming_pin = data.get("pin")

    if not incoming_pin or incoming_pin.strip() != PRESIDENT_PIN:
        return jsonify({"error": "Unauthorized"}), 401

    title = data.get("title")
    assignee = data.get("assignee")
    department = data.get("department")
    deadline = data.get("deadline")

    if not title or not assignee or not department:
        return jsonify({"error": "Missing required fields"}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO tasks (title, assignee, department, status, deadline) VALUES (?, ?, ?, ?, ?)",
        (title.strip(), assignee.strip(), department.strip(), "Pending", deadline.strip() if deadline else None),
    )
    conn.commit()
    new_id = cursor.lastrowid
    conn.close()

    send_task_notification(assignee, title, department, deadline)
    return jsonify({"message": "Task created", "id": new_id}), 201

@app.route("/tasks/<int:task_id>", methods=["PATCH"])
def update_task_status(task_id):
    data = request.get_json() or {}
    status = data.get("status")

    if not status:
        return jsonify({"error": "Status is required"}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM tasks WHERE id = ?", (task_id,))
    if not cursor.fetchone():
        conn.close()
        return jsonify({"error": "Task not found"}), 404

    cursor.execute("UPDATE tasks SET status = ? WHERE id = ?", (status, task_id))
    conn.commit()
    conn.close()

    return jsonify({"message": "Status updated successfully"}), 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)