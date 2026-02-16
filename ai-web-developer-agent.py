from dotenv import load_dotenv
from openai import OpenAI
import logging
import os
import sys
import time
from typing import Any, Optional
from pathlib import Path

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

# ---------------- CONSTANTS ----------------
EXIT_COMMANDS = {"exit", "quit", "stop", "bye"}
MARKDOWN_MARKERS = (
    "```python",
    "```javascript",
    "```html",
    "```css",
    "```js",
    "```",
)
SAVE_ACTION_PREFIX = "ACTION:save_file:"
MODEL_NAME = "gpt-4o"
MODEL_TEMPERATURE = 0.3
BASE_DIR = os.path.abspath(os.getcwd())
MAX_FILE_BYTES = 1_000_000

# ---------------- COLORS FOR TERMINAL ----------------
class Colors:
    HEADER = "\033[95m"
    OKBLUE = "\033[94m"
    OKCYAN = "\033[96m"
    OKGREEN = "\033[92m"
    WARNING = "\033[93m"
    FAIL = "\033[91m"
    ENDC = "\033[0m"
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"

def print_banner() -> None:
    """Print beautiful startup banner"""
    banner = f"""
{Colors.OKCYAN}{Colors.BOLD}
╔══════════════════════════════════════════════════════════════════╗
║                                                                  ║
║              🚀 AI WEB DEVELOPER AGENT v2.0 🚀                  ║
║                                                                  ║
║              Full-Stack Web Apps in Seconds!                     ║
║                                                                  ║
╚══════════════════════════════════════════════════════════════════╝
{Colors.ENDC}

{Colors.OKGREEN}✨ Features:{Colors.ENDC}
  • Flask + JWT + SQLAlchemy
  • Beautiful Tailwind CSS UI
  • Complete Authentication System
  • Ready-to-Run Projects

{Colors.WARNING}📝 Commands:{Colors.ENDC}
  • Type your app idea (e.g., "Todo app", "Blog system")
  • 'exit', 'quit', 'stop' to close
  • 'help' for examples

{Colors.OKCYAN}{'─' * 70}{Colors.ENDC}
"""
    print(banner)

def print_success(message: str) -> None:
    """Print success message in green"""
    print(f"{Colors.OKGREEN}✅ {message}{Colors.ENDC}")

def print_error(message: str) -> None:
    """Print error message in red"""
    print(f"{Colors.FAIL}❌ {message}{Colors.ENDC}")

def print_info(message: str) -> None:
    """Print info message in cyan"""
    print(f"{Colors.OKCYAN}ℹ️  {message}{Colors.ENDC}")

def print_working(message: str) -> None:
    """Print working message in yellow"""
    print(f"{Colors.WARNING}⚙️  {message}{Colors.ENDC}")

# ---------------- UTF-8 ENCODING FIX ----------------
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

load_dotenv()
client = OpenAI()

def validate_environment() -> None:
    """Fail fast if required runtime configuration is missing."""
    if not os.getenv("OPENAI_API_KEY"):
        print_error("OPENAI_API_KEY not found in environment")
        print_info("Create a .env file with: OPENAI_API_KEY=your_key_here")
        sys.exit(1)
    print_success("Environment validated")

def save_file(filename: str, code: str) -> bool:
    """Save file safely with path and size validation."""
    try:
        filename = filename.strip().replace("\x00", "")
        if not filename:
            logger.error("Empty filename received")
            return False

        normalized = os.path.normpath(filename)
        if os.path.isabs(normalized):
            logger.error(f"Absolute paths are not allowed: {filename}")
            return False

        target_path = os.path.abspath(os.path.join(BASE_DIR, normalized))
        try:
            if os.path.commonpath([BASE_DIR, target_path]) != BASE_DIR:
                logger.error(f"Path traversal blocked: {filename}")
                return False
        except ValueError:
            logger.error(f"Invalid path detected: {filename}")
            return False

        if len(code.encode("utf-8")) > MAX_FILE_BYTES:
            logger.error(f"Refusing to write oversized file: {filename}")
            return False
        
        directory = os.path.dirname(target_path)
        if directory and directory not in (".", ""):
            try:
                os.makedirs(directory, exist_ok=True)
                logger.debug(f"Directory ensured: {directory}")
            except OSError as e:
                logger.error(f"Error creating directory {directory}: {e}")
                return False

        try:
            with open(target_path, "w", encoding="utf-8") as f:
                f.write(code.strip())
        except IOError as e:
            logger.error(f"Error writing file {filename}: {e}")
            return False

        print_success(f"Saved: {filename}")
        return True

    except Exception as e:
        logger.exception(f"Unexpected error saving {filename}: {e}")
        return False

def call_openai(messages: list[dict[str, str]], retries: int = 3) -> Any:
    """Call OpenAI with basic retry handling."""
    for attempt in range(retries):
        try:
            return client.chat.completions.create(
                model=MODEL_NAME,
                messages=messages,
                temperature=MODEL_TEMPERATURE
            )
        except Exception as e:
            logger.warning(f"Retry {attempt + 1} failed: {e}")
            if attempt < retries - 1:
                print_working(f"Retrying... (attempt {attempt + 2}/{retries})")
                time.sleep(2)

    raise Exception("OpenAI failed after retries")

def parse_and_save_actions(response_text: str) -> int:
    """Parse ACTION commands and save files. Returns number of files saved."""
    if SAVE_ACTION_PREFIX not in response_text:
        print_info("No save actions detected. Printing model response.")
        print(response_text)
        return 0

    actions = response_text.split(SAVE_ACTION_PREFIX)[1:]
    print_info(f"Detected {len(actions)} files to create")

    saved_count = 0
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
            if success:
                saved_count += 1
            else:
                print_error(f"Failed to save {filename}")

        except Exception as e:
            logger.exception(f"Error parsing action block: {e}")
    
    return saved_count

def show_help() -> None:
    """Show help and examples"""
    help_text = f"""
{Colors.OKCYAN}{Colors.BOLD}💡 Example Prompts:{Colors.ENDC}

{Colors.OKGREEN}Authentication & User Management:{Colors.ENDC}
  • "User registration and login system"
  • "Blog with user authentication"
  • "Multi-user todo app"

{Colors.OKGREEN}Business Applications:{Colors.ENDC}
  • "Invoice generator for freelancers"
  • "Expense tracker"
  • "Inventory management system"
  • "Customer CRM"

{Colors.OKGREEN}Content Management:{Colors.ENDC}
  • "Blog platform"
  • "Portfolio website"
  • "News aggregator"

{Colors.OKGREEN}Productivity Tools:{Colors.ENDC}
  • "Todo list app"
  • "Note taking app"
  • "Project management tool"

{Colors.OKGREEN}E-commerce:{Colors.ENDC}
  • "Simple shopping cart"
  • "Product catalog"

{Colors.WARNING}Tip:{Colors.ENDC} Be specific! Instead of "app", try "Todo app with categories and deadlines"
"""
    print(help_text)

def create_project_summary(saved_count: int) -> None:
    """Show project summary and next steps"""
    summary = f"""
{Colors.OKGREEN}{Colors.BOLD}
╔══════════════════════════════════════════════════════════════════╗
║                  ✅ PROJECT CREATED SUCCESSFULLY!                ║
╚══════════════════════════════════════════════════════════════════╝
{Colors.ENDC}

{Colors.OKCYAN}📊 Summary:{Colors.ENDC}
  • Files created: {saved_count}
  • Framework: Flask + SQLAlchemy + JWT
  • UI: Tailwind CSS (Dark Theme)
  • Database: SQLite (auto-created)

{Colors.WARNING}🚀 Next Steps:{Colors.ENDC}

  1️⃣  Install dependencies:
      {Colors.OKBLUE}uv add -r requirements.txt{Colors.ENDC}

  2️⃣  Run the application:
      {Colors.OKBLUE}uv run app.py{Colors.ENDC}

  3️⃣  Open in browser:
      {Colors.OKBLUE}http://localhost:5000{Colors.ENDC}

{Colors.OKGREEN}📁 Project Structure:{Colors.ENDC}
  ├── app.py              (Main Flask application)
  ├── config.py           (Configuration settings)
  ├── models.py           (Database models)
  ├── requirements.txt    (Dependencies)
  ├── templates/
  │   └── index.html      (Frontend UI)
  └── static/
      └── js/
          └── script.js   (JavaScript logic)

{Colors.OKCYAN}{'─' * 70}{Colors.ENDC}
"""
    print(summary)

def get_improved_system_prompt() -> str:
    """Return improved system prompt"""
    return """
You are a SENIOR Full-Stack Web Developer specializing in modern, production-ready web applications.

CRITICAL RULES:
✅ Create COMPLETE, WORKING applications that run immediately
✅ Use Flask + SQLAlchemy + JWT + Flask-CORS
✅ Beautiful dark theme with Tailwind CSS
✅ All imports must be present in app.py
✅ HTML must have COMPLETE UI (not just headers)
✅ JavaScript must be FUNCTIONAL with event listeners
✅ NO MARKDOWN (```) in output
✅ Use Indian Rupee (₹) for currency if relevant

--------------------------------------------------
REQUIRED FILES:

1. requirements.txt - EXACT versions:
flask>=3.0.0
flask-sqlalchemy>=3.1.1
flask-jwt-extended>=4.6.0
flask-cors>=4.0.0
werkzeug>=3.0.1
python-dotenv>=1.0.0

2. config.py:
import os
from datetime import timedelta

class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL', 'sqlite:///app.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY', 'jwt-secret-key-change-in-production')
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

# Add more models based on app requirements

4. app.py - MUST include:
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

# Add authentication routes (register, login)
# Add protected routes based on app functionality

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True, port=5000)

5. templates/index.html - MUST include:
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>App Title</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap" rel="stylesheet">
</head>
<body class="bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 min-h-screen font-['Inter']">
    <!-- COMPLETE UI with navigation, forms, content areas -->
    <script src="{{ url_for('static', filename='js/script.js') }}"></script>
</body>
</html>

6. static/js/script.js - MUST include:
document.addEventListener('DOMContentLoaded', function() {
    // Complete event listeners and API calls
});

--------------------------------------------------
DESIGN REQUIREMENTS:

✅ Modern glassmorphism: backdrop-blur-md bg-white/10
✅ Gradient backgrounds: from-slate-900 via-slate-800 to-slate-900
✅ Smooth animations: transition-all duration-300
✅ Hover effects: hover:scale-105 hover:shadow-xl
✅ Professional spacing and typography
✅ Responsive design: mobile-first approach
✅ Loading states and error handling in UI

--------------------------------------------------
OUTPUT FORMAT (STRICT):

ACTION:save_file:requirements.txt:
flask>=3.0.0
flask-sqlalchemy>=3.1.1

ACTION:save_file:config.py:
import os
from datetime import timedelta

ACTION:save_file:models.py:
from flask_sqlalchemy import SQLAlchemy

ACTION:save_file:app.py:
from flask import Flask

ACTION:save_file:templates/index.html:
<!DOCTYPE html>

ACTION:save_file:static/js/script.js:
document.addEventListener('DOMContentLoaded'

--------------------------------------------------
VALIDATION CHECKLIST:

Before responding, verify:
✅ requirements.txt has >= not == for versions
✅ app.py has ALL necessary imports
✅ models.py has all required database models
✅ HTML has COMPLETE forms and UI elements
✅ JavaScript has working event listeners
✅ No ``` markdown anywhere
✅ All routes are implemented
✅ Beautiful dark theme applied

Return ONLY ACTION:save_file lines. NO explanations. NO markdown.
"""

def main() -> None:
    print_banner()
    
    try:
        validate_environment()
    except SystemExit:
        return

    while True:
        try:
            # Get user input with colored prompt
            print(f"\n{Colors.BOLD}{Colors.OKGREEN}👨‍💻 You:{Colors.ENDC} ", end="")
            user_query = input().strip()
            
            # Handle commands
            if user_query.lower() in EXIT_COMMANDS:
                print(f"\n{Colors.OKCYAN}👋 Goodbye! Happy coding!{Colors.ENDC}\n")
                break

            if user_query.lower() == "help":
                show_help()
                continue

            if not user_query:
                continue

            # Show working status
            print_working("Analyzing your requirements...")
            time.sleep(0.5)
            print_working("Generating project structure...")
            
            system_prompt = get_improved_system_prompt()
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_query},
            ]
            
            print_working("Creating beautiful application...")
            response = call_openai(messages)

            result = response.choices[0].message.content.strip()

            print_working("Saving files...")
            saved_count = parse_and_save_actions(result)
            
            if saved_count > 0:
                create_project_summary(saved_count)
            else:
                print_error("No files were created. Please try again with a different prompt.")

        except KeyboardInterrupt:
            print(f"\n\n{Colors.WARNING}⚠️  Interrupted by user{Colors.ENDC}")
            print(f"{Colors.OKCYAN}👋 Goodbye! Happy coding!{Colors.ENDC}\n")
            break
        except Exception as e:
            print_error(f"An error occurred: {str(e)}")
            logger.exception("Fatal error in main loop")
            print_info("Please try again or type 'exit' to quit")

if __name__ == "__main__":
    main()


