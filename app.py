import os
import sqlite3
import json
import threading
import urllib.request
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

DATABASE = "tasks.db"
PRESIDENT_PIN = os.environ.get("PRESIDENT_PIN", "1234")
EMAIL_RELAY_URL = os.environ.get("EMAIL_RELAY_URL")

# Executive member email lookup registry
EXEC_ROSTER = {
    "Mahir": "mahirasif2704@gmail.com",
    "1": "mahirasif2704@gmail.com",
    "test": "mahirasif2704@gmail.com",
    "Amani": "amanichowdhury08@gmail.com",
    "mahir's wife": "amanichowdhury08@gmail.com"
    # "Name": "user@example.com",
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

init_db()

def _dispatch_relay_email(assignee_name, task_title, department, deadline=None):
    """Sends clean ASCII/Latin-1 compatible task emails via Google Apps Script without emoji corruption."""
    if not EMAIL_RELAY_URL:
        print("Skipping email: EMAIL_RELAY_URL is not set in Render environment.", flush=True)
        return

    recipient_email = EXEC_ROSTER.get(assignee_name.strip())
    if not recipient_email:
        for name, email in EXEC_ROSTER.items():
            if name.lower() == assignee_name.strip().lower():
                recipient_email = email
                break

    if not recipient_email:
        print(f"Skipping email: '{assignee_name}' is not registered in EXEC_ROSTER.", flush=True)
        return

    deadline_text = f"• Due Date: {deadline}\n" if deadline else ""
    email_body = f"""Hi {assignee_name},

You have been assigned a new task on the BSA Task Tracker:

• Task: {task_title}
• Department: {department}
{deadline_text}
Review and update your tasks here:
https://mahirc27.github.io/bsa-task-tracker/

— BSA Executive Board
"""

    payload = json.dumps({
        "to": recipient_email,
        "subject": f"[BSA Task] New Task Assigned: {task_title}",
        "body": email_body,
    }).encode("utf-8")

    try:
        req = urllib.request.Request(
            EMAIL_RELAY_URL.strip(),
            data=payload,
            headers={
                "Content-Type": "application/json; charset=utf-8",
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            body = response.read().decode("utf-8")
            print(f"Email relay response ({response.status}): {body}", flush=True)
    except Exception as e:
        print(f"Apps Script relay error: {e}", flush=True)

def send_task_notification(assignee_name, task_title, department, deadline=None):
    # Runs on a daemon background thread so the HTTP request completes instantaneously
    threading.Thread(
        target=_dispatch_relay_email,
        args=(assignee_name, task_title, department, deadline),
        daemon=True,
    ).start()

# --- Health Check Endpoints ---
@app.route("/", methods=["GET"])
@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "message": "BSA Tasks API is online"}), 200

# --- Task Endpoints ---
@app.route("/tasks", methods=["GET"])
def get_tasks():
    incoming_pin = request.args.get("pin")
    department = request.args.get("department")

    if incoming_pin is not None and incoming_pin.strip() != PRESIDENT_PIN.strip():
        return jsonify({"error": "Unauthorized"}), 401

    if not department or department == "All":
        if not incoming_pin or incoming_pin.strip() != PRESIDENT_PIN.strip():
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

    if not incoming_pin or incoming_pin.strip() != PRESIDENT_PIN.strip():
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
