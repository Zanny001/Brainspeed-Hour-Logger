import os
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS  # <--- 1. ADD THIS IMPORT
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
CORS(app) 

# Fetch the DB URL from the environment (Render or .env)
DB_URL = os.environ.get("DATABASE_URL")

def get_db():
    if not DB_URL:
        raise ValueError("DATABASE_URL environment variable is missing. Check your .env file or Render settings.")
    return psycopg2.connect(DB_URL)

def init_db():
    if not DB_URL:
        return
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username TEXT UNIQUE,
            password TEXT,
            role TEXT,
            class_level TEXT DEFAULT '',
            subjects TEXT DEFAULT '',
            bio TEXT DEFAULT ''
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sessions (
            id SERIAL PRIMARY KEY,
            teacher_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
            student_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
            subject TEXT,
            session_date TEXT DEFAULT '',
            check_in_time TEXT,
            check_out_time TEXT,
            hours REAL,
            status TEXT DEFAULT 'Pending',
            payment_status TEXT DEFAULT 'Unpaid',
            lat REAL DEFAULT 0.0,
            lng REAL DEFAULT 0.0
        )
    ''')

    # Insert default admin safely
    cursor.execute('''
        INSERT INTO users (username, password, role)
        VALUES ('admin', 'admin123', 'admin')
        ON CONFLICT (username) DO NOTHING
    ''')

    conn.commit()
    cursor.close()
    conn.close()

# --- Secured Database Initialization Route ---
@app.route('/initdb')
def initialize_database():
    secret_key = request.args.get('key')
    if secret_key != "brainspeed_admin_2026":
        return jsonify({"status": "error", "message": "Unauthorized. Invalid setup key."}), 403
    
    init_db()
    return jsonify({"status": "success", "message": "Production Database Setup Complete! Tables verified."})

# --- Page Routes ---
@app.route('/')
def index(): return send_file('login.html')
@app.route('/signup')
def signup_page(): return send_file('signup.html')
@app.route('/reset')
def reset_page(): return send_file('reset.html')
@app.route('/teacher')
def teacher_page(): return send_file('teacher.html')
@app.route('/admin')
def admin_page(): return send_file('admin.html')
@app.route('/student')
def student_page(): return send_file('student.html')

# --- User & Auth APIs ---
@app.route('/api/signup', methods=['POST'])
def signup():
    data = request.json
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO users (username, password, role) VALUES (%s, %s, %s)",
                       (data['username'].lower().strip(), data['password'], data['role']))
        conn.commit()
        return jsonify({"status": "success"})
    except psycopg2.IntegrityError:
        conn.rollback()
        return jsonify({"status": "error", "message": "Username exists"}), 400
    finally:
        cursor.close()
        conn.close()

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    conn = get_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("SELECT * FROM users WHERE username=%s AND password=%s",
                   (data['username'].lower().strip(), data['password']))
    user = cursor.fetchone()
    cursor.close()
    conn.close()
    if user:
        return jsonify({"status": "success", "role": user['role'], "user_id": user['id'], "username": user['username']})
    return jsonify({"status": "error", "message": "Invalid credentials"}), 401

@app.route('/api/profile/<int:user_id>', methods=['GET', 'PUT'])
def handle_profile(user_id):
    conn = get_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    if request.method == 'PUT':
        data = request.json
        cursor.execute("UPDATE users SET class_level=%s, subjects=%s, bio=%s WHERE id=%s",
                       (data.get('class_level', ''), data.get('subjects', ''), data.get('bio', ''), user_id))
        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({"status": "success"})

    cursor.execute("SELECT id, username, role, class_level, subjects, bio FROM users WHERE id=%s", (user_id,))
    user = cursor.fetchone()
    cursor.close()
    conn.close()
    return jsonify(dict(user)) if user else (jsonify({"error": "Not found"}), 404)

@app.route('/api/users', methods=['GET'])
def get_all_users():
    conn = get_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("SELECT id, username, role, class_level, subjects, bio FROM users WHERE role != 'admin' ORDER BY role, username")
    users = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify([dict(u) for u in users])

@app.route('/api/users/<role>', methods=['GET'])
def get_users_by_role(role):
    conn = get_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("SELECT id, username FROM users WHERE role=%s ORDER BY username", (role,))
    users = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify([dict(u) for u in users])

@app.route('/api/users/<int:user_id>', methods=['DELETE'])
def delete_user(user_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM users WHERE id=%s", (user_id,))
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({"status": "success"})

# --- Session & Finance APIs ---
@app.route('/api/sessions', methods=['GET', 'POST'])
def handle_sessions():
    conn = get_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    if request.method == 'POST':
        data = request.json
        cursor.execute('''INSERT INTO sessions
            (teacher_id, student_id, subject, session_date, check_in_time, check_out_time, hours, status, lat, lng)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 'Pending', %s, %s)''',
            (data['teacher_id'], data['student_id'], data['subject'], data.get('session_date', ''),
             data['check_in_time'], data['check_out_time'], data['hours'], data.get('lat', 0.0), data.get('lng', 0.0)))
        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({"status": "success"})

    query = '''SELECT s.*, t.username as teacher_name, st.username as student_name
               FROM sessions s
               JOIN users t ON s.teacher_id = t.id
               JOIN users st ON s.student_id = st.id
               ORDER BY s.id DESC'''
    cursor.execute(query)
    sessions = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify([dict(row) for row in sessions])

@app.route('/api/sessions/student/<int:student_id>', methods=['GET'])
def get_student_sessions(student_id):
    conn = get_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute('''SELECT s.*, t.username as teacher_name FROM sessions s
                      JOIN users t ON s.teacher_id = t.id
                      WHERE s.student_id = %s ORDER BY s.id DESC''', (student_id,))
    sessions = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify([dict(s) for s in sessions])

@app.route('/api/sessions/teacher/<int:teacher_id>', methods=['GET'])
def get_teacher_sessions(teacher_id):
    conn = get_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute('''SELECT s.*, st.username as student_name FROM sessions s
                      JOIN users st ON s.student_id = st.id
                      WHERE s.teacher_id = %s ORDER BY s.id DESC''', (teacher_id,))
    sessions = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify([dict(s) for s in sessions])

@app.route('/api/sessions/auto-checkout', methods=['POST'])
def auto_checkout_session():
    data = request.json
    teacher_id = data.get('teacher_id')
    if not teacher_id:
        return jsonify({"status": "error", "message": "Missing teacher_id"}), 400
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''UPDATE sessions SET status='Completed' 
                      WHERE teacher_id=%s AND status='Pending' ''', (teacher_id,))
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({"status": "success", "message": "Active sessions stopped automatically."})

@app.route('/api/sessions/<int:session_id>/confirm', methods=['PUT'])
def confirm_session(session_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE sessions SET status='Confirmed' WHERE id=%s", (session_id,))
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({"status": "success"})

@app.route('/api/sessions/<int:session_id>/pay', methods=['PUT'])
def pay_session(session_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE sessions SET payment_status='Paid' WHERE id=%s", (session_id,))
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({"status": "success"})

@app.route('/api/sessions/<int:session_id>', methods=['DELETE'])
def delete_session(session_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM sessions WHERE id=%s", (session_id,))
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({"status": "success"})

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000)
