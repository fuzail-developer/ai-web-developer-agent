from dotenv import load_dotenv
from openai import OpenAI
import logging
import os
import sys
import time
from typing import Any
# ---------------- LOGGING CONFIG ----------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("agent.log", encoding="utf-8")
    ]
)

logger = logging.getLogger(__name__)
EXIT_COMMANDS = {"exit", "quit", "stop"}
MARKDOWN_MARKERS = ("```python", "```javascript", "```html", "```css", "```js", "```")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

load_dotenv()
client = OpenAI()

def save_file(filename: str, code: str) -> bool:
    """Save file with proper directory creation"""
    try:
        filename = filename.strip().lstrip("/\\")
        if not filename:
            logger.error("Empty filename received")
            return False
        
        directory = os.path.dirname(os.path.normpath(filename))
        if directory and directory not in (".", ""):
            try:
                os.makedirs(directory, exist_ok=True)
                logger.debug(f"Directory ensured: {directory}")
            except OSError as e:
                logger.error(f"Error creating directory {directory}: {e}")
                return False

        try:
            with open(filename, "w", encoding="utf-8") as f:
                f.write(code.strip())
        except IOError as e:
            logger.error(f"Error writing file {filename}: {e}")
            return False

        logger.info(f"Saved file successfully: {filename}")
        return True

    except Exception as e:
        logger.exception(f"Unexpected error saving {filename}: {e}")
        return False

if not os.getenv("OPENAI_API_KEY"):
    logger.error("OPENAI_API_KEY not found in environment")
    sys.exit(1)


def call_openai(messages: list[dict[str, str]], retries: int = 3) -> Any:
    """Call OpenAI with basic retry handling."""
    for attempt in range(retries):
        try:
            return client.chat.completions.create(
                model="gpt-4o",
                messages=messages,
                temperature=0.3
            )
        except Exception as e:
            logger.warning(f"Retry {attempt + 1} failed: {e}")
            time.sleep(2)

    raise Exception("OpenAI failed after retries")



def parse_and_save_actions(response_text: str) -> None:
    """Parse ACTION commands and save files"""
    if "ACTION:save_file:" not in response_text:
        logger.info("No save actions detected. Printing model response.")
        logger.info(response_text)
        return

    actions = response_text.split("ACTION:save_file:")[1:]
    logger.info(f"Detected {len(actions)} file actions")

    for action in actions:
        try:
            split_index = action.find(":")
            if split_index == -1:
                logger.warning("Malformed ACTION block detected")
                continue

            filename = action[:split_index].strip()
            code = action[split_index + 1:].strip()

            if "ACTION:" in code:
                code = code.split("ACTION:")[0].strip()

            for marker in MARKDOWN_MARKERS:
                code = code.replace(marker, "")
            
            code = code.strip()
            if not code:
                logger.warning(f"Empty code block for {filename}")
                continue

            success = save_file(filename, code)
            if not success:
                logger.warning(f"Failed to save {filename}")

        except Exception as e:
            logger.exception(f"Error parsing action block: {e}")


def main() -> None:
    logger.info("=" * 70)
    logger.info("AI Web Developer Agent - Production Ready")
    logger.info("=" * 70)
    logger.info("Commands: 'exit', 'quit', 'stop' to end")

    while True:
        try:
            user_query = input("👨‍💻 You: ")
            
            if user_query.lower() in EXIT_COMMANDS:
                logger.info("Goodbye!")
                break

            if not user_query.strip():
                continue

            system_prompt = """
You are a SENIOR Full-Stack Web Developer.
You create COMPLETE, WORKING applications that run immediately.

CRITICAL RULES:
✅ app.py MUST have ALL imports (Flask, JWT, SQLAlchemy, etc.)
✅ templates/index.html MUST have COMPLETE UI (forms, buttons, content - NOT just a header)
✅ JavaScript MUST be functional with event listeners
✅ App MUST run with: python app.py (no errors)
✅ Beautiful dark theme with Tailwind CSS

--------------------------------------------------
app.py TEMPLATE (ALWAYS use this):

from flask import Flask, render_template, jsonify, request
from flask_cors import CORS
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import timedelta
from config import Config
from models import db, User

app = Flask(__name__)
app.config.from_object(Config)

CORS(app)
jwt = JWTManager(app)
db.init_app(app)


@app.route('/')
def index():
    return render_template('index.html')


# ---------------- REGISTER ----------------
@app.route('/api/register', methods=['POST'])
def register():
    data = request.json

    if not data.get("username") or not data.get("password") or not data.get("email"):
        return jsonify({"msg": "Missing fields"}), 400

    if User.query.filter_by(username=data["username"]).first():
        return jsonify({"msg": "User already exists"}), 400

    user = User(
        username=data["username"],
        email=data["email"]
    )
    user.set_password(data["password"])

    db.session.add(user)
    db.session.commit()

    return jsonify({"msg": "User registered successfully"}), 201


# ---------------- LOGIN ----------------
@app.route('/api/login', methods=['POST'])
def login():
    data = request.json

    user = User.query.filter_by(username=data.get("username")).first()

    if not user or not user.check_password(data.get("password")):
        return jsonify({"msg": "Invalid credentials"}), 401

    token = create_access_token(identity=user.id)

    return jsonify({"token": token}), 200


# ---------------- PROTECTED ----------------
@app.route('/api/protected', methods=['GET'])
@jwt_required()
def protected():
    user_id = get_jwt_identity()
    return jsonify({"msg": f"Protected data for user {user_id}"}), 200


if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True, port=5000)


--------------------------------------------------
HTML TEMPLATE (ALWAYS complete):

<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>App Title</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap" rel="stylesheet">
</head>
<body class="bg-gradient-to-br from-slate-900 to-slate-800 min-h-screen font-['Inter']">
    <div class="container mx-auto p-8">
        <h1 class="text-4xl font-bold text-white mb-8">🚀 App Title</h1>
        
        <!-- Login Form -->
        <div class="backdrop-blur-md bg-white/10 rounded-xl p-8 max-w-md border border-white/20">
            <h2 class="text-2xl text-white mb-6">Login</h2>
            <form id="loginForm">
                <input type="text" id="username" placeholder="Username" 
                       class="w-full bg-slate-800/50 text-white p-3 rounded-lg mb-4 border border-slate-700 focus:border-blue-500">
                <input type="password" id="password" placeholder="Password" 
                       class="w-full bg-slate-800/50 text-white p-3 rounded-lg mb-4 border border-slate-700 focus:border-blue-500">
                <button type="submit" 
                        class="w-full bg-gradient-to-r from-blue-500 to-purple-600 text-white font-semibold py-3 rounded-lg hover:scale-105 transition-all">
                    Login
                </button>
            </form>
        </div>
        
        <!-- Results Area -->
        <div id="results" class="mt-8"></div>
    </div>
    
    <script src="{{ url_for('static', filename='js/script.js') }}"></script>
</body>
</html>

--------------------------------------------------
JAVASCRIPT TEMPLATE (ALWAYS functional):

document.addEventListener('DOMContentLoaded', function() {
    const loginForm = document.getElementById('loginForm');
    
    if (loginForm) {
        loginForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            
            const username = document.getElementById('username').value;
            const password = document.getElementById('password').value;
            
            try {
                const response = await fetch('/api/login', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({username, password})
                });
                
                const data = await response.json();
                console.log('Success:', data);
                
            } catch (error) {
                console.error('Error:', error);
            }
        });
    }
});

--------------------------------------------------
FILES TO CREATE:

1. requirements.txt:
flask==3.0.0
flask-sqlalchemy==3.1.1
flask-jwt-extended==4.6.0
flask-cors==4.0.0
werkzeug==3.0.1
python-dotenv==1.0.0

2. config.py:
import os
from datetime import timedelta

class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key')
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL', 'sqlite:///app.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY', 'jwt-secret-key')
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=1)

3. models.py:
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

db = SQLAlchemy()

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

4. app.py (use template above)
5. templates/index.html (use template above)
6. static/js/script.js (use template above)
7. static/css/style.css (custom styles if needed)

--------------------------------------------------
DESIGN REQUIREMENTS:

✅ Dark gradient background: from-slate-900 to-slate-800
✅ Glassmorphism cards: backdrop-blur-md bg-white/10
✅ Modern buttons: gradient from-blue-500 to-purple-600
✅ Smooth transitions: hover:scale-105
✅ Professional spacing: p-8, mb-6
✅ Beautiful shadows: border border-white/20
✅ Responsive: container mx-auto

--------------------------------------------------
OUTPUT FORMAT:

ACTION:save_file:requirements.txt:flask==3.0.0
flask-sqlalchemy==3.1.1

ACTION:save_file:app.py:from flask import Flask
app = Flask(__name__)

NO MARKDOWN (```)
NO EXPLANATIONS
ONLY RAW CODE

--------------------------------------------------
VALIDATION:

Before responding, check:
✅ app.py has ALL imports (Flask, JWT, SQLAlchemy, etc.)
✅ HTML has COMPLETE forms (not just header)
✅ JavaScript has event listeners
✅ All routes implemented
✅ Beautiful dark theme
✅ NO ``` anywhere

Return ONLY ACTION:save_file lines.
"""

            logger.info("Creating beautiful app...")

            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_query}
                ],
                temperature=0.3
            )

            result = response.choices[0].message.content.strip()

            logger.info("Saving files...")
            parse_and_save_actions(result)
            
            logger.info("Beautiful project created!")
            logger.info("Run: pip install -r requirements.txt && python app.py")

        except KeyboardInterrupt:
            logger.info("Interrupted. Goodbye!")
            break
        except Exception as e:
            logger.exception(f"Fatal error: {e}")


if __name__ == "__main__":
    main()







