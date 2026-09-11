import os
from functools import wraps
from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

ADMIN_PIN = os.environ.get('ADMIN_PIN', '1234')

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get(
    'DATABASE_URL', f"sqlite:///{os.path.join(BASE_DIR, 'tasks.db')}"
)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

class Task(db.Model):
    __tablename__ = 'tasks'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    assignee = db.Column(db.String(100), nullable=False)
    department = db.Column(db.String(50), nullable=False)
    status = db.Column(db.String(20), nullable=False, default='Pending')

    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'assignee': self.assignee,
            'department': self.department,
            'status': self.status
        }

with app.app_context():
    db.create_all()

def require_pin(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        pin = request.headers.get('X-Admin-PIN')
        if not pin or pin != ADMIN_PIN:
            return jsonify({'error': 'Unauthorized: Invalid or missing PIN'}), 401
        return f(*args, **kwargs)
    return decorated

@app.route('/tasks', methods=['GET'])
def get_tasks():
    dept = request.args.get('department')
    pin = request.headers.get('X-Admin-PIN')

    if not dept:
        if pin != ADMIN_PIN:
            return jsonify({'error': 'Unauthorized'}), 401
        tasks = Task.query.order_by(Task.id.desc()).all()
        return jsonify([task.to_dict() for task in tasks]), 200

    tasks = Task.query.filter_by(department=dept).order_by(Task.id.desc()).all()
    return jsonify([task.to_dict() for task in tasks]), 200

@app.route('/tasks', methods=['POST'])
@require_pin
def create_task():
    data = request.get_json() or {}
    title = data.get('title', '').strip()
    assignee = data.get('assignee', '').strip()
    department = data.get('department', '').strip()

    if not title or not assignee or not department:
        return jsonify({'error': 'Title, assignee, and department are required.'}), 400

    task = Task(title=title, assignee=assignee, department=department, status='Pending')
    db.session.add(task)
    db.session.commit()
    return jsonify(task.to_dict()), 201

@app.route('/tasks/<int:task_id>', methods=['PATCH'])
def update_task_status(task_id):
    task = Task.query.get_or_404(task_id)
    data = request.get_json() or {}
    new_status = data.get('status')
    user_name = data.get('user_name', '').strip()
    pin = request.headers.get('X-Admin-PIN')

    valid_statuses = {'Pending', 'In Progress', 'Done'}
    if new_status not in valid_statuses:
        return jsonify({'error': f'Invalid status. Allowed: {valid_statuses}'}), 400

    is_president = (pin == ADMIN_PIN)
    is_assignee = (user_name.lower() == task.assignee.lower())

    if not is_president and not is_assignee:
        return jsonify({'error': 'Forbidden: You can only update tasks assigned to you.'}), 403

    task.status = new_status
    db.session.commit()
    return jsonify(task.to_dict()), 200

@app.route('/health', methods=['GET'])
def health_check():
    return "OK", 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)
