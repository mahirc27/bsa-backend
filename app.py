from flask import Flask, request, jsonify
from flask_cors import CORS
import sqlite3
import os
import requests

app = Flask(__name__)
CORS(app)

DATABASE = os.path.join(os.path.dirname(__file__), 'tasks.db')
PRESIDENT_PIN = os.environ.get("PRESIDENT_PIN", "1234")
RESEND_API_KEY = os.environ.get("RESEND_API_KEY")

# Map executive/team member names to their emails.
# You can add or modify names and university/club emails here:
EXEC_ROSTER = {
    "Mahir": "mahirasif2704@gmail.com",
    # "Sarah": "sarah@example.com",
}

def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            assignee TEXT NOT NULL,
            department TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'Pending',
            deadline TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    try:
        cursor.execute("ALTER TABLE tasks ADD COLUMN deadline TEXT")
    except Exception:
        pass
    conn.commit()
    conn.close()

init_db()

def send_task_notification(assignee_name, task_title, department, deadline=None):
    if not RESEND_API_KEY:
        print("Skipping email: RESEND_API_KEY not configured.")
        return

    recipient_email = EXEC_ROSTER.get(assignee_name)
    if not recipient_email:
        print(f"Skipping email: No registered email address found for '{assignee_name}'.")
        return

    deadline_text = f"Due Date: {deadline}\n" if deadline else ""

    email_body = f"""Hi {assignee_name},

You have been assigned a new task on the BSA Task Tracker:

📌 Task: {task_title}
🏢 Department: {department}
{deadline_text}
You can review and update your task status here:
https://mahirc27.github.io/bsa-task-tracker/

— BSA Executive Board
"""

    payload = {
        "from": "BSA Tasks <onboarding@resend.dev>",
        "to": [recipient_email],
        "subject": f"📌 New Task Assigned: {task_title}",
        "text": email_body,
    }

    try:
        response = requests.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {RESEND_API_KEY}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=5,
        )
        if response.status_code not in (200, 201):
            print(f"Failed to send email via Resend: {response.text}")
    except Exception as e:
        print(f"Email request failed: {e}", flush=True)

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "healthy"}), 200

@app.route('/tasks', methods=['GET'])
def get_tasks():
    dept = request.args.get('department')
    pin = request.args.get('pin')

    conn = get_db_connection()
    cursor = conn.cursor()

    if pin == PRESIDENT_PIN or not dept or dept == 'All':
        cursor.execute('SELECT * FROM tasks ORDER BY id DESC')
    else:
        cursor.execute('SELECT * FROM tasks WHERE department = ? ORDER BY id DESC', (dept,))

    rows = cursor.fetchall()
    conn.close()

    tasks = [
        {
            "id": r["id"],
            "title": r["title"],
            "assignee": r["assignee"],
            "department": r["department"],
            "status": r["status"],
            "deadline": r["deadline"] if "deadline" in r.keys() else None,
            "created_at": r["created_at"],
        }
        for r in rows
    ]
    return jsonify(tasks), 200

@app.route('/tasks', methods=['POST'])
def create_task():
    data = request.get_json() or {}
    if data.get('pin') != PRESIDENT_PIN:
        return jsonify({"error": "Unauthorized"}), 401

    title = data.get('title')
    assignee = data.get('assignee')
    department = data.get('department')
    deadline = data.get('deadline')

    if not title or not assignee or not department:
        return jsonify({"error": "Missing required fields"}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        'INSERT INTO tasks (title, assignee, department, status, deadline) VALUES (?, ?, ?, ?, ?)',
        (title, assignee, department, 'Pending', deadline),
    )
    conn.commit()
    conn.close()

    # Trigger outbound email notification
    send_task_notification(assignee, title, department, deadline)

    return jsonify({"message": "Task created successfully"}), 201

@app.route('/tasks/<int:task_id>', methods=['PATCH', 'PUT'])
def update_task_status(task_id):
    data = request.get_json() or {}
    new_status = data.get('status')

    if new_status not in ['Pending', 'In Progress', 'Done']:
        return jsonify({"error": "Invalid status"}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE tasks SET status = ? WHERE id = ?', (new_status, task_id))
    conn.commit()
    conn.close()

    return jsonify({"message": "Status updated successfully"}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
