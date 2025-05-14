import requests
from flask import Flask, request, jsonify, render_template, redirect, url_for, session, flash, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import json
import os
from functools import wraps

app = Flask(__name__)
app.secret_key = os.urandom(24)
app.config['PERMANENT_SESSION_LIFETIME'] = 1800  # 30-minute session timeout

# Database configuration
DATABASE = 'users.sqlite'
TOGETHER_API_KEY = "tgp_v1_UfhsuuRFetNAKzszRlFNLSSUqjpfv_U4-gDTE86QKqk"


def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_db_connection() as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                role TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()


init_db()


# Authentication decorators
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page', 'warning')
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)

    return decorated_function


def teacher_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'role' not in session or session['role'] != 'teacher':
            flash('Teacher access required', 'danger')
            return redirect(url_for('index'))
        return f(*args, **kwargs)

    return decorated_function


SERP_API_KEY = "9d4361ee2cc22491aaef7fd18b3c319ef9cfd3e242d28d19c69af4710641293b"
SERP_ENDPOINT = "https://serpapi.com/search.json"


@app.before_request
def before_request():
    session.permanent = True


@app.route('/')
def home():
    if 'user_id' in session:
        return redirect(url_for('index'))
    return redirect(url_for('login'))

@app.route('/favicon.ico')
def favicon():
    return send_from_directory(
        os.path.join(app.root_path),
        'favicon.ico',
        mimetype='image/vnd.microsoft.icon'
    )
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']
        role = request.form['role']
        secret_code = request.form['secret_code']

        valid_codes = {
            'teacher': '3000',
            'student': '0000'
        }

        if secret_code != valid_codes.get(role, ''):
            flash('Invalid registration code', 'danger')
            return redirect(url_for('register'))

        if not username or len(username) < 4:
            flash('Username must be at least 4 characters', 'danger')
            return redirect(url_for('register'))

        if len(password) < 6:
            flash('Password must be at least 6 characters', 'danger')
            return redirect(url_for('register'))

        hashed_password = generate_password_hash(password)

        try:
            with get_db_connection() as conn:
                conn.execute(
                    "INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
                    (username, hashed_password, role)
                )
                conn.commit()
            flash('Registration successful! Please log in.', 'success')
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash('Username already exists', 'danger')
        except Exception as e:
            flash(f'Registration error: {str(e)}', 'danger')

    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']

        try:
            with get_db_connection() as conn:
                user = conn.execute(
                    "SELECT * FROM users WHERE username = ?",
                    (username,)
                ).fetchone()

            if user and check_password_hash(user['password'], password):
                session['user_id'] = user['id']
                session['username'] = user['username']
                session['role'] = user['role']

                next_page = request.args.get('next')
                flash('Logged in successfully!', 'success')
                return redirect(next_page or url_for('index'))
            else:
                flash('Invalid username or password', 'danger')
        except Exception as e:
            flash(f'Login error: {str(e)}', 'danger')

    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    session.clear()
    flash('You have been logged out', 'info')
    return redirect(url_for('login'))


@app.route("/index")
@login_required
def index():
    with open("topics.json", "r") as f:
        allowed_topics = json.load(f)
    return render_template("index.html",
                           allowed_topics=allowed_topics,
                           user={'username': session.get('username'),
                                 'role': session.get('role')})


@app.route("/get_keywords")
@login_required
def get_keywords():
    grade = request.args.get("grade")
    subject = request.args.get("subject")
    with open("topics.json", "r") as f:
        allowed_topics = json.load(f)
    keywords = allowed_topics.get(grade, {}).get(subject, [])
    return jsonify({"keywords": keywords})


@app.route("/get_image/")
@login_required
def get_image():
    grade = request.args.get("grade", "")
    subject = request.args.get("subject", "")
    prompt = request.args.get("prompt", "").strip().lower()

    with open("topics.json", "r") as f:
        allowed_topics = json.load(f)
    keywords = allowed_topics.get(grade, {}).get(subject, [])
    keywords_normalized = [k.lower() for k in keywords]

    if prompt not in keywords_normalized:
        return jsonify({
            "error": "❌ Sorry, not possible. Please enter a valid keyword for the selected grade and subject."
        })

    is_teacher_approved_prompt = False
    if prompt.startswith("teacher approved - "):
        is_teacher_approved_prompt = True
        cleaned_prompt = prompt.replace("teacher approved - ", "").strip()
        search_term = f"{cleaned_prompt} diagram"
    else:
        search_term = f"{grade} {subject} {prompt} diagram"

    ai_summary = None
    try:
        import together

        client = together.Together(api_key=TOGETHER_API_KEY)

        prompt_text = (
            f"Generate 2-3 sentences to describe a grade {grade} {subject} diagram on "
            f"'{prompt}'. Keep it general and from a student’s point of view. Keep it in second person and never use first person."
        )

        response = client.chat.completions.create(
            model="meta-llama/Llama-3.3-70B-Instruct-Turbo-Free",
            messages=[{"role": "user", "content": prompt_text}]
        )
        ai_summary = response.choices[0].message.content.strip()
    except Exception as e:
        ai_summary = f"❌ Could not fetch summary. ({str(e)})"

    try:
        img_params = {
            "q": search_term,
            "tbm": "isch",
            "api_key": SERP_API_KEY
        }
        img_resp = requests.get(SERP_ENDPOINT, params=img_params)
        img_resp.raise_for_status()
        img_data = img_resp.json()
        images = img_data.get("images_results", [])

        if images:
            return jsonify({
                "title": images[0].get("title", "Result"),
                "image_url": images[0].get("original"),
                "caption": ai_summary or "No description available.",
                "is_teacher": session.get('role') == 'teacher',
                "is_teacher_approved_prompt": is_teacher_approved_prompt
            })
        else:
            return jsonify({"error": "❌ No image found. Try a different valid keyword."})

    except requests.RequestException as e:
        return jsonify({"error": f"❌ API Error: {str(e)}"})


@app.route("/get_image_random/")
@login_required
def get_image_random():
    import random

    def fetch_random_image(search_term):
        try:
            params = {
                "q": search_term,
                "tbm": "isch",
                "api_key": SERP_API_KEY,
                "num": 10,
                "safe": "active"
            }
            resp = requests.get(SERP_ENDPOINT, params=params)
            resp.raise_for_status()
            data = resp.json()
            images = data.get("images_results", [])
            if not images:
                return None, None
            selected = random.choice(images)
            return selected.get("original"), selected.get("title", search_term)
        except Exception as e:
            return None, f"❌ Error: {str(e)}"

    grade = request.args.get("grade", "")
    subject = request.args.get("subject", "")
    prompt = request.args.get("prompt", "").strip().lower()

    with open("topics.json", "r") as f:
        allowed_topics = json.load(f)
    keywords = allowed_topics.get(grade, {}).get(subject, [])
    if prompt not in [k.lower() for k in keywords]:
        return jsonify({
            "error": "❌ Invalid keyword for selected grade and subject."
        })

    search_term = f"{subject} {prompt} diagram"
    image_url, title_or_error = fetch_random_image(search_term)

    if not image_url:
        return jsonify({"error": title_or_error or "❌ No image found."})

    return jsonify({
        "title": title_or_error,
        "image_url": image_url
    })


@app.route("/get_image_custom")
@teacher_required
def get_image_custom():
    query = request.args.get("query", "").strip().lower()
    if not query:
        return jsonify({"error": "❌ No search query provided."})

    search_term = f"{query} diagram"
    params = {
        "q": search_term,
        "tbm": "isch",
        "api_key": SERP_API_KEY
    }

    try:
        response = requests.get(SERP_ENDPOINT, params=params)
        response.raise_for_status()
        data = response.json()

        images = data.get("images_results", [])
        if images:
            return jsonify({
                "title": images[0].get("title", "Result"),
                "image_url": images[0].get("original")
            })
        else:
            return jsonify({"error": "❌ No image found. Try another search."})
    except requests.RequestException as e:
        return jsonify({"error": f"❌ API Error: {str(e)}"})


@app.route('/approve_prompt', methods=['POST'])
def approve_prompt():
    data = request.get_json()
    grade = data.get('grade')
    subject = data.get('subject')
    prompt = data.get('prompt')

    if not all([grade, subject, prompt]):
        return jsonify({'message': 'Missing grade, subject, or prompt'}), 400

    with open('topics.json', 'r') as f:
        topics = json.load(f)

    if prompt in topics.get(grade, {}).get(subject, []):
        return jsonify({'message': f'❌ The topic "{prompt}" already exists.'})

    topics.setdefault(grade, {}).setdefault(subject, []).append(f"Teacher Approved - {prompt}")

    with open('topics.json', 'w') as f:
        json.dump(topics, f, indent=2)

    return jsonify({'message': f'✅ "{prompt}" added successfully to Grade {grade} → {subject}.'})


@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404


@app.errorhandler(500)
def internal_server_error(e):
    return render_template('500.html'), 500


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=8000)
