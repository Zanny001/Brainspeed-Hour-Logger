from flask import Flask, request, jsonify, send_file
import sqlite3

app = Flask(__name__)
DB_NAME = 'tutor_agency.db'

def get_db():
    conn = sqlite3.connect(DB_NAME)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE, password TEXT, role TEXT
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            teacher_id INTEGER, student_id INTEGER,
            subject TEXT, check_in_time TEXT, check_out_time TEXT,
            hours REAL, status TEXT DEFAULT 'Pending',
            payment_status TEXT DEFAULT 'Unpaid',
            FOREIGN KEY(teacher_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY(student_id) REFERENCES users(id) ON DELETE CASCADE
        )
    ''')
    # Safely migrate existing databases to include new columns
    for col in ['payment_status', 'class_level', 'subjects', 'bio', 'lat', 'lng']:
        try:
            db_type = 'REAL' if col in ['lat', 'lng'] else 'TEXT'
            default_val = "0.0" if col in ['lat', 'lng'] else "''"
            conn.execute(f"ALTER TABLE {'sessions' if col in ['payment_status', 'lat', 'lng'] else 'users'} ADD COLUMN {col} {db_type} DEFAULT {default_val}")
        except sqlite3.OperationalError:
            pass
            
    conn.execute("INSERT OR IGNORE INTO users (username, password, role) VALUES ('admin', 'admin123', 'admin')")
    conn.commit()
    conn.close()

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
    try:
        conn.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)", (data['username'].lower().strip(), data['password'], data['role']))
        conn.commit()
        return jsonify({"status": "success"})
    except sqlite3.IntegrityError:
        return jsonify({"status": "error", "message": "Username exists"}), 400
    finally: conn.close()

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE username=? AND password=?", (data['username'].lower().strip(), data['password'])).fetchone()
    conn.close()
    if user: return jsonify({"status": "success", "role": user['role'], "user_id": user['id'], "username": user['username']})
    return jsonify({"status": "error", "message": "Invalid credentials"}), 401

@app.route('/api/profile/<int:user_id>', methods=['GET', 'PUT'])
def handle_profile(user_id):
    conn = get_db()
    if request.method == 'PUT':
        data = request.json
        conn.execute("UPDATE users SET class_level=?, subjects=?, bio=? WHERE id=?", (data.get('class_level', ''), data.get('subjects', ''), data.get('bio', ''), user_id))
        conn.commit()
        conn.close()
        return jsonify({"status": "success"})
    
    user = conn.execute("SELECT id, username, role, class_level, subjects, bio FROM users WHERE id=?", (user_id,)).fetchone()
    conn.close()
    return jsonify(dict(user)) if user else jsonify({"error": "Not found"}), 404

@app.route('/api/users', methods=['GET'])
def get_all_users():
    conn = get_db()
    users = [dict(row) for row in conn.execute("SELECT id, username, role, class_level, subjects, bio FROM users WHERE role != 'admin' ORDER BY role, username").fetchall()]
    conn.close()
    return jsonify(users)

@app.route('/api/users/<role>', methods=['GET'])
def get_users_by_role(role):
    conn = get_db()
    users = [dict(row) for row in conn.execute("SELECT id, username FROM users WHERE role=? ORDER BY username", (role,)).fetchall()]
    conn.close()
    return jsonify(users)

@app.route('/api/users/<int:user_id>', methods=['DELETE'])
def delete_user(user_id):
    conn = get_db()
    conn.execute("DELETE FROM users WHERE id=?", (user_id,))
    conn.commit()
    conn.close()
    return jsonify({"status": "success"})

# --- Session & Finance APIs ---
@app.route('/api/sessions', methods=['GET', 'POST'])
def handle_sessions():
    conn = get_db()
    if request.method == 'POST':
        data = request.json
        conn.execute("INSERT INTO sessions (teacher_id, student_id, subject, check_in_time, check_out_time, hours, status, lat, lng) VALUES (?, ?, ?, ?, ?, ?, 'Pending', ?, ?)", 
                     (data['teacher_id'], data['student_id'], data['subject'], data['check_in_time'], data['check_out_time'], data['hours'], data.get('lat', 0.0), data.get('lng', 0.0)))
        conn.commit()
        conn.close()
        return jsonify({"status": "success"})
    
    query = '''SELECT s.*, t.username as teacher_name, st.username as student_name FROM sessions s 
               JOIN users t ON s.teacher_id = t.id JOIN users st ON s.student_id = st.id ORDER BY s.id DESC'''
    sessions = [dict(row) for row in conn.execute(query).fetchall()]
    conn.close()
    return jsonify(sessions)

@app.route('/api/sessions/student/<int:student_id>', methods=['GET'])
def get_student_sessions(student_id):
    conn = get_db()
    sessions = [dict(row) for row in conn.execute("SELECT s.*, t.username as teacher_name FROM sessions s JOIN users t ON s.teacher_id = t.id WHERE s.student_id = ? ORDER BY s.id DESC", (student_id,)).fetchall()]
    conn.close()
    return jsonify(sessions)

@app.route('/api/sessions/teacher/<int:teacher_id>', methods=['GET'])
def get_teacher_sessions(teacher_id):
    conn = get_db()
    sessions = [dict(row) for row in conn.execute("SELECT s.*, st.username as student_name FROM sessions s JOIN users st ON s.student_id = st.id WHERE s.teacher_id = ? ORDER BY s.id DESC", (teacher_id,)).fetchall()]
    conn.close()
    return jsonify(sessions)

@app.route('/api/sessions/<int:session_id>/confirm', methods=['PUT'])
def confirm_session(session_id):
    conn = get_db()
    conn.execute("UPDATE sessions SET status='Confirmed' WHERE id=?", (session_id,))
    conn.commit()
    conn.close()
    return jsonify({"status": "success"})

@app.route('/api/sessions/<int:session_id>/pay', methods=['PUT'])
def pay_session(session_id):
    conn = get_db()
    conn.execute("UPDATE sessions SET payment_status='Paid' WHERE id=?", (session_id,))
    conn.commit()
    conn.close()
    return jsonify({"status": "success"})

@app.route('/api/sessions/<int:session_id>', methods=['DELETE'])
def delete_session(session_id):
    conn = get_db()
    conn.execute("DELETE FROM sessions WHERE id=?", (session_id,))
    conn.commit()
    conn.close()
    return jsonify({"status": "success"})

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000)
