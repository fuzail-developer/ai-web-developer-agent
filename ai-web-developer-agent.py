"""
AI Web Developer Agent v7.0 - PRODUCTION READY
Created by: FUZAIL (fuzail-developer)

FIXES IN v7.0:
- Real Flask-Login authentication added
- SQLite + SQLAlchemy database integration
- Proper password hashing (werkzeug)
- @login_required on all protected routes
- PDF generation with WeasyPrint
- Dynamic resume form with JS add/remove
- CSRF protection
- Proper error handling + flash messages
- Deployment ready (Procfile, gunicorn, .env)
- OpenAI resume-specific prompts improved
"""

from dotenv import load_dotenv
import importlib
import threading

OpenAI = None
OPENAI_AVAILABLE = False
OPENAI_IMPORT_ATTEMPTED = False
OPENAI_IMPORT_TIMEOUT_SECONDS = 5.0

import logging
import os
import subprocess
import sys
import time
import argparse
import asyncio
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import ClassVar, Dict, List, Optional, Any, Tuple
import shlex 
import re
import json
import ast

# ---------------- BRANDING ----------------
CREATOR = "FUZAIL"
CREATOR_GITHUB = "fuzail-developer"
VERSION = "7.0.0"

# ---------------- LOGGING ----------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("agent.log", encoding="utf-8")
    ]
)
logger = logging.getLogger(__name__)

# Optional dependency health check (startup)
try:
    import weasyprint  # type: ignore
    WEASYPRINT_AVAILABLE = True
except Exception:
    WEASYPRINT_AVAILABLE = False
    logger.warning("WeasyPrint not installed - PDF generation may be disabled in generated apps.")

# ---------------- CONSTANTS ----------------
EXIT_COMMANDS = {"exit", "quit", "stop", "bye"}
MARKDOWN_MARKERS = ("```python", "```javascript", "```html", "```css", "```js", "```")
SAVE_ACTION_PREFIX = "ACTION:save_file:"
MODEL_TEMPERATURE = 0.3
MAX_FILE_BYTES = 2_000_000
MAX_TOKENS = 8000
RATE_LIMIT_CALLS = 15
TIMEOUT_SECONDS = 120
AUTO_INSTALL_PACKAGES = False
RETRY_ATTEMPTS = 3
RETRY_BASE_DELAY_SECONDS = 1.5
RATE_LIMIT_WINDOW_SECONDS = 60
LAST_AI_FALLBACK_REASON: Optional[str] = None
MAX_PROJECT_NAME_LEN = 64
MAX_PROJECT_PATH_LEN = 220
MAX_REVISION_FILES = 30
MAX_REVISION_FILE_BYTES = 200_000
DEFAULT_REVISION_ROUNDS = 3
DEFAULT_SELF_FIX_ATTEMPTS = 3
PROJECT_HISTORY_FILE = ".ai-agent-project-history.json"
WINDOWS_RESERVED_NAMES = {
    "con", "prn", "aux", "nul",
    "com1", "com2", "com3", "com4", "com5", "com6", "com7", "com8", "com9",
    "lpt1", "lpt2", "lpt3", "lpt4", "lpt5", "lpt6", "lpt7", "lpt8", "lpt9",
}

# ---------------- COLORS ----------------
class Colors:
    HEADER:   ClassVar[str] = "\033[95m"
    OKBLUE:   ClassVar[str] = "\033[94m"
    OKCYAN:   ClassVar[str] = "\033[96m"
    OKGREEN:  ClassVar[str] = "\033[92m"
    WARNING:  ClassVar[str] = "\033[93m"
    FAIL:     ClassVar[str] = "\033[91m"
    ENDC:     ClassVar[str] = "\033[0m"
    BOLD:     ClassVar[str] = "\033[1m"
    UNDERLINE:ClassVar[str] = "\033[4m"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

load_dotenv()
client = None

def _import_openai_with_timeout(timeout_s: float) -> tuple[Optional[Any], Optional[Exception]]:
    result: dict[str, Any] = {"module": None, "error": None}

    def _target() -> None:
        try:
            result["module"] = importlib.import_module("openai")
        except Exception as e:
            result["error"] = e

    t = threading.Thread(target=_target, daemon=True)
    t.start()
    t.join(timeout_s)
    if t.is_alive():
        return None, TimeoutError("OpenAI import timed out")
    if result["error"] is not None:
        return None, result["error"]
    return result["module"], None

def ensure_openai_client() -> Optional[Any]:
    global OPENAI_AVAILABLE, OPENAI_IMPORT_ATTEMPTED, OpenAI, client
    if OPENAI_IMPORT_ATTEMPTED:
        return client
    OPENAI_IMPORT_ATTEMPTED = True
    module, err = _import_openai_with_timeout(OPENAI_IMPORT_TIMEOUT_SECONDS)
    if err is not None:
        logger.warning("OpenAI import failed: %s", err)
        return None
    if module is None or not hasattr(module, "OpenAI"):
        logger.warning("OpenAI module missing OpenAI client.")
        return None
    try:
        OpenAI = module.OpenAI
        OPENAI_AVAILABLE = True
        if os.getenv("OPENAI_API_KEY"):
            client = OpenAI()
        else:
            client = None
        return client
    except Exception as e:
        logger.warning("OpenAI client init failed: %s", e)
        return None

# ==================== HELPER FUNCTIONS ====================
def print_banner():
    banner = f"""
{Colors.OKCYAN}{Colors.BOLD}
╔══════════════════════════════════════════════════════════════════╗
║                                                                  ║
║        🏆 AI WEB DEVELOPER AGENT v{VERSION} - PRODUCTION 🏆     ║
║                                                                  ║
║            Created by: {CREATOR} ({CREATOR_GITHUB})              ║
║                                                                  ║
╚══════════════════════════════════════════════════════════════════╝
{Colors.ENDC}
{Colors.OKGREEN}✅ v7.0 Features:{Colors.ENDC}
  • 🔐 Flask-Login + session auth (login_required)
  • 🗄️  SQLite + SQLAlchemy (users + resumes tables)
  • 🔑  Secure password hashing (werkzeug pbkdf2)
  • 📄  PDF export (WeasyPrint HTML→PDF)
  • 🛡️  CSRF protection + input sanitization
  • 💬  Flash messages + 404/500 error pages
  • 🚀  Deployment ready (Procfile + gunicorn)
  • 🤖  AI resume bullet points (OpenAI)
{Colors.OKCYAN}{'─' * 70}{Colors.ENDC}
"""
    print(banner)

def print_success(msg: str): print(f"{Colors.OKGREEN}✅ {msg}{Colors.ENDC}")
def print_error(msg: str):   print(f"{Colors.FAIL}❌ {msg}{Colors.ENDC}")
def print_info(msg: str):    print(f"{Colors.OKCYAN}ℹ️  {msg}{Colors.ENDC}")
def print_working(msg: str): print(f"{Colors.WARNING}⚙️  {msg}{Colors.ENDC}")

# ==================== MODEL MANAGER ====================
class ModelManager:
    MODELS = {
        'gpt-4o':      {'provider': 'openai', 'name': 'gpt-4o'},
        'gpt-4o-mini': {'provider': 'openai', 'name': 'gpt-4o-mini'},
        'o1-mini':     {'provider': 'openai', 'name': 'o1-mini'},
    }

    @staticmethod
    def get_client(_model: str) -> Optional[Any]:
        ensure_openai_client()
        if client is None:
            logger.warning("OpenAI client unavailable.")
            return None
        if not os.getenv("OPENAI_API_KEY"):
            logger.warning("OPENAI_API_KEY missing.")
            return None
        return client

# ==================== API SAFETY GUARD ====================
class APICallGuard:
    def __init__(self, max_calls: int, window_seconds: int):
        self.max_calls = max_calls
        self.window_seconds = window_seconds
        self.call_timestamps: List[float] = []

    def _prune(self, now: float) -> None:
        cutoff = now - self.window_seconds
        self.call_timestamps = [ts for ts in self.call_timestamps if ts >= cutoff]

    def wait_for_slot(self) -> None:
        now = time.monotonic()
        self._prune(now)
        if len(self.call_timestamps) < self.max_calls:
            self.call_timestamps.append(now)
            return
        sleep_for = (self.call_timestamps[0] + self.window_seconds) - now
        if sleep_for > 0:
            logger.warning(f"Rate limit waiting {sleep_for:.1f}s")
            print_info(f"Rate limit active. Waiting {sleep_for:.1f}s...")
            time.sleep(sleep_for)
        now = time.monotonic()
        self._prune(now)
        self.call_timestamps.append(now)

    def call_with_retry(self, func, *args, **kwargs):
        last_error = None
        for attempt in range(1, RETRY_ATTEMPTS + 1):
            self.wait_for_slot()
            try:
                return func(*args, **kwargs)
            except Exception as e:
                last_error = e
                if attempt == RETRY_ATTEMPTS:
                    break
                delay = RETRY_BASE_DELAY_SECONDS * attempt
                logger.warning("API call failed (attempt %s/%s): %s", attempt, RETRY_ATTEMPTS, e)
                time.sleep(delay)
        raise last_error

api_guard = APICallGuard(RATE_LIMIT_CALLS, RATE_LIMIT_WINDOW_SECONDS)

# ==================== SYSTEM PROMPT (IMPROVED) ====================
def build_system_prompt(config: Dict[str, str]) -> str:
    mode = config.get('mode', 'web')
    database = config.get('database', 'sqlite')

    base = f"""
You are a senior full-stack engineer. Generate a COMPLETE, PRODUCTION-READY project.

Project type: {mode}
Database: {database}

CRITICAL REQUIREMENTS — include ALL of these:

1. AUTHENTICATION (Flask-Login required):
   - LoginManager + UserMixin + user_loader
   - login_user / logout_user / current_user usage
   - /signup, /login, /logout routes
   - @login_required on ALL protected routes

2. DATABASE (SQLAlchemy + {database}):
   - User table: id, username, email, password_hash, created_at
   - Main data table (resumes/posts/etc): id, title, content/data, user_id FK, timestamps
   - db.create_all() in if __name__ == '__main__'

3. SECURITY:
   - SECRET_KEY must be loaded from environment; fail fast if missing
   - CSRF protection via Flask-WTF (CSRFProtect)
   - Include CSRF token in all forms; JSON endpoints must send X-CSRFToken or be exempted
   - Input validation + length limits
   - Password min 6 chars check
   - Duplicate username/email check
   - Email verification + forgot/reset password flow using token links

4. FRONTEND:
   - Modern dark/light theme with CSS variables
   - Theme toggle button persisted in localStorage
   - Responsive design (mobile-friendly)
   - Dynamic JS forms (add/remove fields)
   - Flash messages display
   - 404 and 500 error pages

5. PDF EXPORT (if resume/document app):
   - WeasyPrint HTML→PDF route
   - /resume/<id>/pdf endpoint
   - Clean print-ready template

6. DEPLOYMENT FILES:
   - requirements.txt (all dependencies)
   - Procfile: web: gunicorn app:app
   - .env.example: SECRET_KEY=, DATABASE_URL=
   - Include project ZIP export route and dashboard button

Return ONLY ACTION:save_file blocks. No markdown fences. No explanations.
Format:
ACTION:save_file:filename.ext:
<complete file content>
"""
    if mode == 'saas':
        base += "\n7. Include subscription/plan model and stripe placeholder."
    elif mode == 'api':
        base += "\n7. Include JWT token auth, /api/v1/ prefix, OpenAPI docs comments."

    return base

# ==================== RESUME-SPECIFIC AI PROMPT ====================
def build_resume_ai_prompt(section: str, context: str) -> str:
    """Generate AI bullet points for resume sections"""
    return f"""You are a professional resume writer.
Generate 3-4 strong, ATS-optimized bullet points for this resume section.

Section: {section}
Context: {context}

Rules:
- Start each bullet with a strong action verb (Led, Built, Increased, Reduced, etc.)
- Include metrics where possible (%, $, time saved)
- Keep each bullet under 120 characters
- Be specific and professional

Return ONLY the bullet points, one per line, starting with •
No explanations, no extra text."""

# ==================== FILE PARSER ====================
def parse_action_blocks(response_text: str) -> Dict[str, str]:
    files: Dict[str, str] = {}
    if SAVE_ACTION_PREFIX not in response_text:
        return files
    chunks = response_text.split(SAVE_ACTION_PREFIX)[1:]
    for chunk in chunks:
        idx = chunk.find(":")
        if idx == -1:
            continue
        filename = chunk[:idx].strip().replace("\x00", "")
        content  = chunk[idx + 1:].strip()
        if SAVE_ACTION_PREFIX in content:
            content = content.split(SAVE_ACTION_PREFIX, 1)[0].strip()
        for marker in MARKDOWN_MARKERS:
            content = content.replace(marker, "")
        if filename and content:
            files[filename] = content.strip()
    return files

def save_generated_files(files: Dict[str, str]) -> List[str]:
    saved: List[str] = []
    base_dir = Path.cwd().resolve()
    for filename, content in files.items():
        normalized = os.path.normpath(filename)
        if os.path.isabs(normalized):
            logger.warning("Skipping absolute path: %s", filename)
            continue
        target = (base_dir / normalized).resolve()
        try:
            if os.path.commonpath([str(base_dir), str(target)]) != str(base_dir):
                logger.warning("Blocked path traversal: %s", filename)
                continue
        except ValueError:
            continue
        if len(content.encode("utf-8")) > MAX_FILE_BYTES:
            logger.warning("Skipping oversized file: %s", filename)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        saved.append(filename)
    return saved

def slugify(text: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", text.strip().lower()).strip("-")
    if len(slug) > MAX_PROJECT_NAME_LEN:
        slug = slug[:MAX_PROJECT_NAME_LEN].rstrip("-")
    return slug or "project"

def extract_query_from_command_like_input(text: str) -> str:
    """
    If user pastes a full CLI command in interactive prompt, extract --query value.
    """
    raw = text.strip()
    # --query "..."
    m = re.search(r'--query\s+"([^"]+)"', raw)
    if m:
        return m.group(1).strip()
    # --query '...'
    m = re.search(r"--query\s+'([^']+)'", raw)
    if m:
        return m.group(1).strip()
    return raw

def fit_project_name_to_path(base_dir: Path, project_name: str) -> str:
    safe = project_name
    while len(str((base_dir / safe).resolve())) > MAX_PROJECT_PATH_LEN and len(safe) > 8:
        safe = safe[:-1].rstrip("-")
    return safe or "project"

def normalize_project_dir_name(project_name: str) -> str:
    """
    Make project directory names safe on Windows and portable across OSes.
    """
    safe = (project_name or "").strip().strip(". ")
    if not safe:
        safe = "project"
    if safe.lower() in WINDOWS_RESERVED_NAMES:
        safe = f"{safe}-app"
    return safe

def resolve_unique_project_name(base_dir: Path, preferred_name: str) -> str:
    """
    Return an available project folder name by appending -2, -3, ...
    """
    base_name = normalize_project_dir_name(fit_project_name_to_path(base_dir, preferred_name))
    candidate = base_name
    if not (base_dir / candidate).exists():
        return candidate

    for i in range(2, 1000):
        with_suffix = fit_project_name_to_path(base_dir, f"{base_name}-{i}")
        with_suffix = normalize_project_dir_name(with_suffix)
        if not (base_dir / with_suffix).exists():
            return with_suffix
    return normalize_project_dir_name(fit_project_name_to_path(base_dir, f"{base_name}-{int(time.time())}"))

def load_project_history(index_file: Path) -> List[Dict[str, Any]]:
    if not index_file.exists():
        return []
    try:
        data = json.loads(index_file.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return [x for x in data if isinstance(x, dict)]
    except Exception:
        logger.warning("Project history is invalid JSON, starting fresh.")
    return []

def save_project_history(index_file: Path, rows: List[Dict[str, Any]]) -> None:
    index_file.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")

def upsert_project_history(
    index_file: Path,
    project_dir: Path,
    query: str,
    config: Dict[str, str],
) -> None:
    rows = load_project_history(index_file)
    now = datetime.now(timezone.utc).isoformat()
    normalized = str(project_dir.resolve())
    name = project_dir.name
    existing = next((r for r in rows if r.get("path") == normalized), None)
    if existing:
        existing["last_used_at"] = now
        if query:
            existing["last_query"] = query
        existing["mode"] = config.get("mode", "web")
        existing["database"] = config.get("database", "sqlite")
        existing["model"] = config.get("model", "gpt-4o-mini")
    else:
        rows.append(
            {
                "name": name,
                "path": normalized,
                "created_at": now,
                "last_used_at": now,
                "last_query": query,
                "mode": config.get("mode", "web"),
                "database": config.get("database", "sqlite"),
                "model": config.get("model", "gpt-4o-mini"),
            }
        )
    rows = sorted(rows, key=lambda r: r.get("last_used_at", ""), reverse=True)[:500]
    save_project_history(index_file, rows)

def resolve_project_reference(project_ref: str, base_dir: Path, index_file: Path) -> Optional[Path]:
    direct = Path(project_ref).expanduser()
    if not direct.is_absolute():
        direct = (base_dir / direct).resolve()
    if direct.exists() and direct.is_dir():
        return direct

    rows = load_project_history(index_file)
    project_ref_l = project_ref.strip().lower()
    exact = next((r for r in rows if str(r.get("name", "")).lower() == project_ref_l), None)
    if exact:
        p = Path(str(exact.get("path", "")))
        if p.exists() and p.is_dir():
            return p
    partial = next((r for r in rows if project_ref_l in str(r.get("name", "")).lower()), None)
    if partial:
        p = Path(str(partial.get("path", "")))
        if p.exists() and p.is_dir():
            return p
    return None

def print_project_history(index_file: Path) -> None:
    rows = load_project_history(index_file)
    if not rows:
        print_info("No saved project history yet.")
        return
    print_success(f"Found {len(rows)} project(s) in history")
    for row in rows[:30]:
        name = row.get("name", "unknown")
        path = row.get("path", "")
        last_used = row.get("last_used_at", "-")
        print(f"  {Colors.OKCYAN}• {name}{Colors.ENDC}  ({last_used})")
        print(f"    {path}")

def validate_python_source(source: str) -> bool:
    try:
        ast.parse(source)
        return True
    except Exception:
        return False

def validate_template_structure(source: str) -> bool:
    """
    Basic Jinja structure validation to catch truncated templates.
    """
    def count(tag: str) -> int:
        return len(re.findall(tag, source))

    if_count = count(r"{%\s*if\b")
    endif_count = count(r"{%\s*endif\s*%}")
    for_count = count(r"{%\s*for\b")
    endfor_count = count(r"{%\s*endfor\s*%}")
    block_count = count(r"{%\s*block\b")
    endblock_count = count(r"{%\s*endblock\s*%}")

    if if_count != endif_count:
        return False
    if for_count != endfor_count:
        return False
    if block_count != endblock_count:
        return False
    return True

def auto_fix_generated_app_py(app_source: str) -> str:
    """
    Patch common runtime issues found in LLM-generated Flask apps.
    """
    fixed = app_source

    # Fix: db.create_all() called outside application context.
    if re.search(r"\bdb\.create_all\s*\(", fixed) and "app.app_context()" not in fixed:
        fixed = re.sub(
            r"^(?P<indent>\s*)db\.create_all\s*\((?P<args>.*)\)\s*$",
            r"\g<indent>with app.app_context():\n\g<indent>    db.create_all(\g<args>)",
            fixed,
            count=1,
            flags=re.MULTILINE,
        )

    # Fix: missing root route causes 404 on http://127.0.0.1:5000/
    has_root_route = ("@app.route('/')" in fixed) or ('@app.route("/")' in fixed)
    if not has_root_route:
        root_snippet = (
            "@app.route('/')\n"
            "def home():\n"
            "    if 'dashboard' in app.view_functions:\n"
            "        return redirect(url_for('dashboard'))\n"
            "    if 'login' in app.view_functions:\n"
            "        return redirect(url_for('login'))\n"
            "    return 'App is running', 200\n\n"
        )
        marker = "@app.route('/signup'"
        if marker in fixed:
            fixed = fixed.replace(marker, root_snippet + marker, 1)
        else:
            marker2 = "@app.route('/login'"
            if marker2 in fixed:
                fixed = fixed.replace(marker2, root_snippet + marker2, 1)

    return fixed

def sync_requirements_with_app(requirements_text: str, app_source: str) -> str:
    """
    Ensure requirements include packages actually imported by app.py.
    """
    req_lines = [line.strip() for line in requirements_text.splitlines() if line.strip()]
    existing = {line.split("==")[0].split(">=")[0].lower() for line in req_lines}

    import_matches = set(re.findall(r"^\s*from\s+([a-zA-Z0-9_\.]+)\s+import\s+", app_source, flags=re.MULTILINE))
    import_matches.update(re.findall(r"^\s*import\s+([a-zA-Z0-9_\.]+)", app_source, flags=re.MULTILINE))
    modules = {m.split(".")[0].lower() for m in import_matches}

    module_to_req = {
        "flask_wtf": "flask-wtf>=1.2.0",
        "flask_login": "flask-login>=0.6.3",
        "flask_mail": "flask-mail>=0.10.0",
        "flask_migrate": "flask-migrate>=4.0.5",
        "flask_cors": "flask-cors>=4.0.0",
        "email_validator": "email-validator>=2.1.0",
        "wtforms": "wtforms>=3.1.0",
    }

    for module, requirement in module_to_req.items():
        pkg = requirement.split(">=")[0].lower()
        if module in modules and pkg not in existing:
            req_lines.append(requirement)
            existing.add(pkg)
            logger.warning("Added missing dependency from app imports: %s", requirement)

    return "\n".join(req_lines).rstrip() + "\n"

def has_minimum_security_features(app_source: str) -> bool:
    required_markers = [
        "/forgot-password",
        "/reset-password/",
        "/verify-email/",
        "/project/export.zip",
        "is_verified",
    ]
    return all(marker in app_source for marker in required_markers)

def ensure_project_integrity(files_map: Dict[str, str], project_name: str, config: Dict) -> Dict[str, str]:
    """
    Ensure generated output always has minimum runnable files.
    If AI output is partial/broken, patch missing or invalid files from fallback scaffold.
    """
    base = dict(files_map)
    fallback = fallback_scaffold(project_name, config)

    required = [
        "app.py",
        "requirements.txt",
        ".env.example",
        "Procfile",
        "README.md",
        "DEPLOY.md",
        "templates/home.html",
        "templates/login.html",
        "templates/signup.html",
        "templates/forgot_password.html",
        "templates/reset_password.html",
        "templates/dashboard.html",
        "templates/404.html",
        "templates/500.html",
        "templates/item_form.html",
        "templates/item_view.html",
        "templates/item_pdf.html",
    ]

    for path in required:
        if path not in base or not str(base[path]).strip():
            logger.warning("Missing critical file from AI output: %s (using fallback copy)", path)
            base[path] = fallback[path]

    # Replace syntactically invalid Python files with safe fallback versions.
    replaced_invalid = False
    for path, content in list(base.items()):
        if path.endswith(".py") and not validate_python_source(content):
            logger.warning("Invalid Python generated for %s (using fallback copy if available)", path)
            if path in fallback:
                base[path] = fallback[path]
                replaced_invalid = True

    # Replace structurally invalid templates to avoid Jinja runtime errors.
    replaced_templates = False
    for path, content in list(base.items()):
        if path.endswith(".html") and not validate_template_structure(content):
            logger.warning("Invalid template structure for %s (using fallback copy if available)", path)
            if path in fallback:
                base[path] = fallback[path]
                replaced_templates = True

    if replaced_invalid or replaced_templates:
        base["ai-fallback-reason.txt"] = "AI output had invalid Python; fallback files were applied.\n"

    if "app.py" in base:
        original_app = base["app.py"]
        repaired_app = auto_fix_generated_app_py(original_app)
        if repaired_app != original_app:
            logger.warning("Auto-repaired generated app.py for common Flask runtime issues.")
            base["app.py"] = repaired_app
            base["ai-fallback-reason.txt"] = "Auto-repaired generated app.py for runtime safety.\n"
        if not has_minimum_security_features(base["app.py"]):
            logger.warning("Generated app.py missing required auth/security/export features; using fallback app.py.")
            base["app.py"] = fallback["app.py"]
            base["ai-fallback-reason.txt"] = "Fallback app.py applied: missing required auth/security/export features.\n"

    if "app.py" in base:
        req_text = base.get("requirements.txt", fallback["requirements.txt"])
        base["requirements.txt"] = sync_requirements_with_app(req_text, base["app.py"])

    return base

# ==================== FALLBACK SCAFFOLD (PRODUCTION-READY) ====================
def fallback_scaffold(project_name: str, config: Dict) -> Dict[str, str]:
    """
    FIXED: Complete production-ready scaffold with:
    - Real auth (login_required, session, password hashing)
    - SQLite + SQLAlchemy
    - PDF export
    - Security best practices
    - Deployment files
    """
    secret_key = secrets.token_hex(32)

    files = {}

    # ── requirements.txt ──────────────────────────────────────
    files["requirements.txt"] = (
        "flask>=3.0.0\n"
        "flask-login>=0.6.3\n"
        "flask-sqlalchemy>=3.1.0\n"
        "flask-mail>=0.10.0\n"
        "flask-wtf>=1.2.0\n"
        "werkzeug>=3.0.0\n"
        "python-dotenv>=1.0.0\n"
        "openai>=2.0.0\n"
        "gunicorn>=21.0.0\n"
        "weasyprint>=60.0\n"
    )

    # ── Procfile ───────────────────────────────────────────────
    files["Procfile"] = "web: gunicorn app:app\n"

    # ── .env.example ──────────────────────────────────────────
    files[".env.example"] = (
        f"SECRET_KEY={secret_key}\n"
        "DATABASE_URL=sqlite:///app.db\n"
        "FLASK_ENV=production\n"
        "REQUIRE_EMAIL_VERIFICATION=auto\n"
        "MAIL_SERVER=smtp.gmail.com\n"
        "MAIL_PORT=587\n"
        "MAIL_USE_TLS=true\n"
        "MAIL_USERNAME=your-email@example.com\n"
        "MAIL_PASSWORD=your-email-password\n"
        "MAIL_DEFAULT_SENDER=your-email@example.com\n"
        "OPENAI_API_KEY=your-key-here\n"
    )

    # ── .gitignore ────────────────────────────────────────────
    files[".gitignore"] = (
        "ai-fallback-reason.txt\n"
    )

    # ── README.md ──────────────────────────────────────────────
    files["README.md"] = f"""# {project_name}

Generated by AI Web Developer Agent v{VERSION}

## Setup

```bash
pip install -r requirements.txt
python -c "from shutil import copyfile; copyfile('.env.example', '.env')"
python app.py
```

## One-Click Deploy

- Render: https://render.com/deploy?repo=<YOUR_GITHUB_REPO_URL>
- Railway: https://railway.app/new?referralCode=<YOUR_CODE>

See `DEPLOY.md` for full deployment steps.

## Deploy to Render/Heroku

- Set environment variables from .env.example
- Push to GitHub
- Connect repo to Render/Heroku
"""

    # ── DEPLOY.md ─────────────────────────────────────────────
    files["DEPLOY.md"] = f"""# Deploy Helper

## One-Click Links

- Render: https://render.com/deploy?repo=<YOUR_GITHUB_REPO_URL>
- Railway: https://railway.app/new?referralCode=<YOUR_CODE>

## Quick Commands

```bash
git init
git add .
git commit -m "deploy prep"
git branch -M main
git remote add origin <YOUR_GITHUB_REPO_URL>
git push -u origin main
```

## Required Env Vars

```bash
SECRET_KEY=<generate-random-secret>
DATABASE_URL=sqlite:///app.db
OPENAI_API_KEY=<optional>
```

## Procfile

`web: gunicorn app:app`
"""

    # ── app.py ─────────────────────────────────────────────────
    files["app.py"] = f'''from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_wtf.csrf import CSRFProtect
from werkzeug.security import generate_password_hash, check_password_hash
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from datetime import datetime
from pathlib import Path
import json, os, secrets, io, logging, zipfile
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

try:
    from weasyprint import HTML
    PDF_ENABLED = True
except ImportError:
    HTML = None
    PDF_ENABLED = False
    logger.warning("WeasyPrint not installed - PDF generation disabled")

try:
    from flask_mail import Mail, Message
    MAIL_IMPORT_OK = True
except Exception:
    Mail = None
    Message = None
    MAIL_IMPORT_OK = False
    logger.warning("Flask-Mail not installed - email sending disabled")

AI_CLIENT = None
AI_ENABLED = False
if os.getenv("OPENAI_API_KEY"):
    try:
        from openai import OpenAI
        AI_CLIENT = OpenAI()
        AI_ENABLED = True
    except Exception as e:
        logger.warning("OpenAI client unavailable: %s", e)

app = Flask(__name__)
secret_key = os.getenv("SECRET_KEY")
if not secret_key:
    raise RuntimeError("SECRET_KEY is required. Set it in .env or environment.")
app.secret_key = secret_key
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL", "sqlite:///app.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["TEMPLATES_AUTO_RELOAD"] = True
app.config["MAIL_SERVER"] = os.getenv("MAIL_SERVER", "")
app.config["MAIL_PORT"] = int(os.getenv("MAIL_PORT", "587"))
app.config["MAIL_USE_TLS"] = os.getenv("MAIL_USE_TLS", "true").lower() == "true"
app.config["MAIL_USERNAME"] = os.getenv("MAIL_USERNAME", "")
app.config["MAIL_PASSWORD"] = os.getenv("MAIL_PASSWORD", "")
app.config["MAIL_DEFAULT_SENDER"] = os.getenv("MAIL_DEFAULT_SENDER", app.config["MAIL_USERNAME"])
app.jinja_env.auto_reload = True

def _is_real_mail_config() -> bool:
    server = str(app.config.get("MAIL_SERVER", "")).strip().lower()
    sender = str(app.config.get("MAIL_DEFAULT_SENDER", "")).strip().lower()
    username = str(app.config.get("MAIL_USERNAME", "")).strip().lower()
    password = str(app.config.get("MAIL_PASSWORD", "")).strip()
    if not (server and sender and username and password):
        return False
    placeholders = ("your-email", "example.com", "your-email-password", "changeme")
    if any(p in sender for p in placeholders):
        return False
    if any(p in username for p in placeholders):
        return False
    if any(p in password.lower() for p in placeholders):
        return False
    return True

verification_mode = os.getenv("REQUIRE_EMAIL_VERIFICATION", "auto").strip().lower()
if verification_mode in {"1", "true", "yes", "on"}:
    EMAIL_VERIFICATION_REQUIRED = True
elif verification_mode in {"0", "false", "no", "off"}:
    EMAIL_VERIFICATION_REQUIRED = False
else:
    EMAIL_VERIFICATION_REQUIRED = MAIL_IMPORT_OK and _is_real_mail_config()
logger.info("EMAIL_VERIFICATION_REQUIRED=%s", EMAIL_VERIFICATION_REQUIRED)

db = SQLAlchemy(app)
csrf = CSRFProtect(app)
mail = Mail(app) if MAIL_IMPORT_OK and Mail is not None else None
login_manager = LoginManager()
login_manager.login_view = "login"
login_manager.init_app(app)
serializer = URLSafeTimedSerializer(app.secret_key)

# ── MODELS ──────────────────────────────────────────────────
class User(UserMixin, db.Model):
    id         = db.Column(db.Integer, primary_key=True)
    username   = db.Column(db.String(80),  unique=True, nullable=False)
    email      = db.Column(db.String(120), unique=True, nullable=False)
    password   = db.Column(db.String(200), nullable=False)
    is_verified = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    items      = db.relationship("Item", backref="user", lazy=True, cascade="all, delete-orphan")

class Item(db.Model):
    id         = db.Column(db.Integer, primary_key=True)
    title      = db.Column(db.String(100), nullable=False)
    data       = db.Column(db.Text, nullable=False, default="{{}}")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    user_id    = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def _token(kind: str, user_id: int) -> str:
    return serializer.dumps({{"kind": kind, "uid": user_id}})

def _verify_token(token: str, kind: str, max_age: int):
    try:
        data = serializer.loads(token, max_age=max_age)
    except (BadSignature, SignatureExpired):
        return None
    if data.get("kind") != kind:
        return None
    uid = data.get("uid")
    if not uid:
        return None
    return User.query.get(int(uid))

def _send_mail(to_email: str, subject: str, body: str) -> bool:
    if (not MAIL_IMPORT_OK) or (mail is None) or (Message is None):
        logger.info("Mail library unavailable. Subject=%s Body=%s", subject, body)
        return False
    if not app.config.get("MAIL_SERVER") or not app.config.get("MAIL_DEFAULT_SENDER"):
        logger.info("Mail not configured. Subject=%s Body=%s", subject, body)
        return False
    try:
        msg = Message(subject=subject, recipients=[to_email], body=body)
        mail.send(msg)
        return True
    except Exception as e:
        logger.warning("Mail send failed: %s", e)
        logger.info("Mail fallback body: %s", body)
        return False

# ── ROUTES ───────────────────────────────────────────────────
@app.route("/")
def home():
    return render_template("home.html")

@app.route("/signup", methods=["GET", "POST"])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email    = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm  = request.form.get("confirm_password", "")
        # Allow accidental leading/trailing spaces only if both become equal after trim.
        if password != confirm and password.strip() == confirm.strip():
            password = password.strip()
            confirm = confirm.strip()

        if not all([username, email, password]):
            flash("All fields are required!", "error")
        elif len(username) < 3:
            flash("Username must be at least 3 characters!", "error")
        elif len(password) < 6:
            flash("Password must be at least 6 characters!", "error")
        elif password != confirm:
            flash("Passwords do not match! (check extra spaces too)", "error")
        elif User.query.filter_by(username=username).first():
            flash("Username already taken!", "error")
        elif User.query.filter_by(email=email).first():
            flash("Email already registered!", "error")
        else:
            user = User(
                username=username,
                email=email,
                password=generate_password_hash(password, method="pbkdf2:sha256")
            )
            db.session.add(user)
            db.session.commit()
            if not EMAIL_VERIFICATION_REQUIRED:
                user.is_verified = True
                db.session.commit()
                login_user(user)
                flash(f"Welcome, {{user.username}}! Account created.", "success")
                return redirect(url_for("dashboard"))
            token = _token("verify", user.id)
            verify_link = url_for("verify_email", token=token, _external=True)
            sent = _send_mail(
                user.email,
                "Verify your account",
                f"Hi {{user.username}}, verify your account: {{verify_link}}"
            )
            if sent:
                flash("Account created. Check your email to verify.", "success")
            else:
                flash(f"Account created. Mail not configured. Verify here: {{verify_link}}", "error")
            return redirect(url_for("login"))
    return render_template("signup.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = User.query.filter(
            (User.username == username) | (User.email == username.lower())
        ).first()
        if user and check_password_hash(user.password, password):
            if not user.is_verified:
                if EMAIL_VERIFICATION_REQUIRED:
                    flash("Please verify your email before login.", "error")
                    return redirect(url_for("login"))
                user.is_verified = True
                db.session.commit()
            login_user(user)
            flash(f"Welcome back, {{user.username}}!", "success")
            return redirect(url_for("dashboard"))
        flash("Invalid username or password!", "error")
    return render_template("login.html")

@app.route("/logout")
def logout():
    logout_user()
    flash("Logged out successfully.", "success")
    return redirect(url_for("home"))

@app.route("/verify-email/<token>")
def verify_email(token):
    user = _verify_token(token, "verify", max_age=60 * 60 * 24)
    if not user:
        flash("Invalid or expired verification link.", "error")
        return redirect(url_for("login"))
    user.is_verified = True
    db.session.commit()
    flash("Email verified. You can login now.", "success")
    return redirect(url_for("login"))

@app.route("/resend-verification", methods=["POST"])
@csrf.exempt
def resend_verification():
    email = request.form.get("email", "").strip().lower()
    user = User.query.filter_by(email=email).first()
    if user and not user.is_verified:
        token = _token("verify", user.id)
        verify_link = url_for("verify_email", token=token, _external=True)
        _send_mail(user.email, "Verify your account", f"Verify: {{verify_link}}")
    flash("If account exists, verification link was sent.", "success")
    return redirect(url_for("login"))

@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        user = User.query.filter_by(email=email).first()
        if user:
            token = _token("reset", user.id)
            reset_link = url_for("reset_password", token=token, _external=True)
            _send_mail(user.email, "Reset your password", f"Reset password: {{reset_link}}")
        flash("If account exists, password reset link was sent.", "success")
        return redirect(url_for("login"))
    return render_template("forgot_password.html")

@app.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    user = _verify_token(token, "reset", max_age=60 * 60)
    if not user:
        flash("Invalid or expired reset link.", "error")
        return redirect(url_for("forgot_password"))
    if request.method == "POST":
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")
        if len(password) < 6:
            flash("Password must be at least 6 characters.", "error")
        elif password != confirm:
            flash("Passwords do not match.", "error")
        else:
            user.password = generate_password_hash(password, method="pbkdf2:sha256")
            db.session.commit()
            flash("Password reset successful. Please login.", "success")
            return redirect(url_for("login"))
    return render_template("reset_password.html")

@app.route("/dashboard")
@login_required
def dashboard():
    items = Item.query.filter_by(user_id=current_user.id).order_by(Item.updated_at.desc()).all()
    fallback_msg = None
    try:
        with open("ai-fallback-reason.txt", "r", encoding="utf-8") as f:
            fallback_msg = f.read().strip()
    except FileNotFoundError:
        pass
    return render_template("dashboard.html", items=items, fallback_msg=fallback_msg, project_name="{project_name}")

@app.route("/fallback/clear", methods=["POST"])
@login_required
def clear_fallback_reason():
    try:
        os.remove("ai-fallback-reason.txt")
        flash("Fallback notice cleared.", "success")
    except FileNotFoundError:
        pass
    except Exception:
        flash("Could not clear fallback notice.", "error")
    return redirect(url_for("dashboard"))

@app.route("/item/new")
@login_required
def new_item():
    return render_template("item_form.html", item=None)

@app.route("/item/save", methods=["POST"])
@login_required
def save_item():
    try:
        data = request.get_json()
        if not data:
            return jsonify({{"error": "No data provided"}}), 400
        item_id = data.get("id")
        if item_id:
            item = Item.query.filter_by(id=item_id, user_id=current_user.id).first_or_404()
            item.title      = str(data.get("title", item.title))[:100]
            item.data       = json.dumps(data)
            item.updated_at = datetime.utcnow()
        else:
            item = Item(
                title   = str(data.get("title", "Untitled"))[:100],
                data    = json.dumps(data),
                user_id = current_user.id
            )
            db.session.add(item)
        db.session.commit()
        return jsonify({{"success": True, "id": item.id}})
    except Exception as e:
        db.session.rollback()
        return jsonify({{"error": str(e)}}), 500

@app.route("/item/<int:item_id>")
@login_required
def view_item(item_id):
    item = Item.query.filter_by(id=item_id, user_id=current_user.id).first_or_404()
    data = json.loads(item.data)
    return render_template("item_view.html", item=item, data=data)

@app.route("/item/<int:item_id>/edit")
@login_required
def edit_item(item_id):
    item = Item.query.filter_by(id=item_id, user_id=current_user.id).first_or_404()
    return render_template("item_form.html", item=item)

@app.route("/item/<int:item_id>/delete", methods=["POST"])
@login_required
def delete_item(item_id):
    item = Item.query.filter_by(id=item_id, user_id=current_user.id).first_or_404()
    db.session.delete(item)
    db.session.commit()
    flash("Deleted successfully!", "success")
    return redirect(url_for("dashboard"))

@app.route("/project/export.zip")
@login_required
def export_project_zip():
    root = Path.cwd()
    excluded = {{".git", "__pycache__", ".venv", "venv", ".pytest_cache"}}
    mem = io.BytesIO()
    with zipfile.ZipFile(mem, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if any(part in excluded for part in path.parts):
                continue
            rel = path.relative_to(root)
            zf.write(path, arcname=str(rel))
    mem.seek(0)
    return send_file(
        mem,
        mimetype="application/zip",
        as_attachment=True,
        download_name=f"{project_name}.zip"
    )

if not PDF_ENABLED:
    @app.route("/item/<int:item_id>/pdf")
    @login_required
    def download_pdf(item_id):
        flash("PDF generation is disabled. Install WeasyPrint: pip install weasyprint", "error")
        return redirect(url_for("view_item", item_id=item_id))
else:
    @app.route("/item/<int:item_id>/pdf")
    @login_required
    def download_pdf(item_id):
        item = Item.query.filter_by(id=item_id, user_id=current_user.id).first_or_404()
        data = json.loads(item.data)
        html = render_template("item_pdf.html", item=item, data=data)
        pdf  = HTML(string=html).write_pdf()
        return send_file(
            io.BytesIO(pdf),
            mimetype="application/pdf",
            as_attachment=True,
            download_name=f"{{item.title.replace(' ', '_')}}.pdf"
        )

@app.route("/ai/bullets", methods=["POST"])
@login_required
def ai_bullets():
    if not AI_ENABLED or AI_CLIENT is None:
        return jsonify({{"error": "AI unavailable. Set OPENAI_API_KEY and install openai."}}), 503
    data = request.get_json() or {{}}
    section = str(data.get("section", "")).strip()
    context = str(data.get("context", "")).strip()
    if not section or not context:
        return jsonify({{"error": "section and context are required"}}), 400
    prompt = (
        "You are a professional resume writer.\\n"
        "Generate 3-4 strong, ATS-optimized bullet points.\\n"
        f"Section: {{section}}\\n"
        f"Context: {{context}}\\n"
        "Rules:\\n"
        "- Start each bullet with a strong action verb\\n"
        "- Include metrics where possible\\n"
        "- Keep each bullet under 120 characters\\n"
        "Return ONLY bullets, one per line, starting with •"
    )
    response = AI_CLIENT.chat.completions.create(
        model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        messages=[{{"role": "user", "content": prompt}}],
        max_tokens=300,
        temperature=0.7,
    )
    text = response.choices[0].message.content or ""
    bullets = [line.strip() for line in text.split("\\n") if line.strip().startswith("•")]
    if not bullets:
        bullets = [line.strip() for line in text.split("\\n") if line.strip()]
    return jsonify({{"bullets": bullets}})

# ── ERROR HANDLERS ───────────────────────────────────────────
@app.errorhandler(404)
def not_found(e):
    return render_template("404.html"), 404

@app.errorhandler(500)
def server_error(e):
    return render_template("500.html"), 500

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True, use_reloader=True, reloader_type="stat", port=5000)
'''

    # ── templates/home.html ────────────────────────────────────
    files["templates/home.html"] = f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{project_name}</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
:root{{--bg:#0a0a0f;--card:#13131a;--accent:#f5c842;--text:#f0f0f0;--muted:#888;--border:#222230}}
[data-theme="light"]{{--bg:#f7f8fc;--card:#ffffff;--accent:#d38b00;--text:#171717;--muted:#555;--border:#ddd}}
body{{background:var(--bg);color:var(--text);font-family:'DM Sans',system-ui,sans-serif;min-height:100vh}}
nav{{display:flex;justify-content:space-between;align-items:center;padding:1.2rem 2.5rem;background:rgba(10,10,15,.9);border-bottom:1px solid var(--border);position:sticky;top:0;z-index:50}}
.logo{{font-size:1.5rem;font-weight:700;color:var(--accent);text-decoration:none}}
.madeby{{display:block;font-size:.72rem;color:var(--muted);margin-top:.15rem}}
.nav-links a{{color:var(--muted);text-decoration:none;margin-left:1.5rem;font-size:.9rem;transition:.3s}}
.nav-links a:hover{{color:var(--text)}}
.btn-primary{{background:var(--accent)!important;color:#000!important;padding:.5rem 1.4rem;border-radius:50px;font-weight:700}}
.theme-btn{{margin-left:1rem;border:1px solid var(--border);background:transparent;color:var(--text);padding:.4rem .8rem;border-radius:999px;cursor:pointer}}
hero{{min-height:90vh;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;padding:2rem}}
hero h1{{font-size:clamp(2.5rem,7vw,5rem);font-weight:900;margin-bottom:1rem;line-height:1.1}}
hero h1 span{{color:var(--accent)}}
hero p{{color:var(--muted);font-size:1.1rem;max-width:500px;line-height:1.7;margin-bottom:2.5rem}}
.btns{{display:flex;gap:1rem;flex-wrap:wrap;justify-content:center}}
.btn{{padding:.9rem 2.2rem;border-radius:50px;font-weight:700;text-decoration:none;transition:.3s;font-size:1rem}}
.btn-g{{background:var(--accent);color:#000}}
.btn-g:hover{{background:#ffd700;transform:translateY(-3px)}}
.btn-o{{border:1px solid var(--border);color:var(--text)}}
.btn-o:hover{{border-color:var(--accent);color:var(--accent);transform:translateY(-3px)}}
</style>
</head>
<body>
<nav>
  <div>
    <a href="/" class="logo">{project_name}</a>
    <span class="madeby">Built by FUZAIL</span>
  </div>
  <div class="nav-links">
    <button id="theme-toggle" class="theme-btn" type="button">Theme</button>
    <a href="/login">Login</a>
    <a href="/signup" class="btn-primary">Get Started Free</a>
  </div>
</nav>
<hero>
  <h1>Build <span>Something</span><br>Amazing Today</h1>
  <p>A powerful app to manage your work. Sign up free and get started in minutes.</p>
  <div class="btns">
    <a href="/signup" class="btn btn-g">Start Free →</a>
    <a href="/login"  class="btn btn-o">Sign In</a>
  </div>
</hero>
<script>
  const themeKey = 'app-theme';
  const root = document.documentElement;
  const saved = localStorage.getItem(themeKey);
  if (saved) root.setAttribute('data-theme', saved);
  document.getElementById('theme-toggle')?.addEventListener('click', () => {{
    const next = root.getAttribute('data-theme') === 'light' ? 'dark' : 'light';
    root.setAttribute('data-theme', next);
    localStorage.setItem(themeKey, next);
  }});
</script>
</body>
</html>'''

    # ── templates/login.html ───────────────────────────────────
    files["templates/login.html"] = '''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Login</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
:root{--bg1:#0a0a0f;--bg2:#12101a;--card:#13131a;--border:#222230;--text:#f0f0f0;--muted:#888;--accent:#f5c842}
[data-theme="light"]{--bg1:#eef2ff;--bg2:#f8fafc;--card:#ffffff;--border:#d7d9e3;--text:#171717;--muted:#555;--accent:#c58000}
body{background:linear-gradient(135deg,var(--bg1),var(--bg2));min-height:100vh;display:flex;align-items:center;justify-content:center;font-family:system-ui,sans-serif;color:var(--text)}
.card{background:var(--card);border:1px solid var(--border);border-radius:20px;padding:2.5rem;width:100%;max-width:420px;box-shadow:0 25px 60px rgba(0,0,0,.25)}
h2{font-size:1.8rem;font-weight:700;text-align:center;margin-bottom:.4rem}
.sub{color:var(--muted);text-align:center;font-size:.9rem;margin-bottom:2rem}
.flash-error{background:rgba(255,107,107,.1);border:1px solid rgba(255,107,107,.3);color:#ff6b6b;padding:.7rem 1rem;border-radius:8px;font-size:.85rem;margin-bottom:1rem}
.flash-success{background:rgba(80,220,140,.1);border:1px solid rgba(80,220,140,.3);color:#50dc8c;padding:.7rem 1rem;border-radius:8px;font-size:.85rem;margin-bottom:1rem}
label{display:block;font-size:.78rem;font-weight:600;color:var(--muted);margin-bottom:.4rem;text-transform:uppercase;letter-spacing:.5px}
input{width:100%;background:transparent;border:1px solid var(--border);border-radius:10px;padding:.85rem 1rem;color:var(--text);font-size:.95rem;outline:none;margin-bottom:1.2rem;transition:.3s}
input:focus{border-color:var(--accent);box-shadow:0 0 0 3px rgba(245,200,66,.1)}
.btn{width:100%;background:var(--accent);color:#000;border:none;padding:1rem;border-radius:10px;font-weight:700;font-size:1rem;cursor:pointer;transition:.3s}
.btn:hover{filter:brightness(1.04);transform:translateY(-2px)}
.link-row{text-align:center;margin-top:1rem;color:var(--muted);font-size:.9rem}
.link-row a{color:var(--accent);text-decoration:none;font-weight:500}
.theme-wrap{text-align:right;margin-bottom:.8rem}
.theme-btn{border:1px solid var(--border);padding:.25rem .7rem;border-radius:999px;background:transparent;color:var(--text);cursor:pointer}
.match-note{font-size:.82rem;margin-top:-.6rem;margin-bottom:.9rem;color:var(--muted)}
.match-note.bad{color:#ff6b6b}
</style>
</head>
<body>
<div class="card">
  <div class="theme-wrap"><button type="button" class="theme-btn" id="theme-toggle">Theme</button></div>
  <h2>Welcome Back</h2>
  <div class="sub">Sign in to your account</div>
  {% with messages = get_flashed_messages(with_categories=true) %}
    {% for cat, msg in messages %}
      <div class="flash-{{ cat }}">{{ msg }}</div>
    {% endfor %}
  {% endwith %}
  <form method="POST">
    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
    <label>Username or Email</label>
    <input type="text" name="username" placeholder="username or you@email.com" required autofocus>
    <label>Password</label>
    <input type="password" name="password" placeholder="Your password" required>
    <button type="submit" class="btn">Sign In →</button>
  </form>
  <div class="link-row"><a href="/forgot-password">Forgot password?</a></div>
  <div class="link-row">No account? <a href="/signup">Create one free</a></div>
</div>
<script>
  const k='app-theme', r=document.documentElement, s=localStorage.getItem(k);
  if(s) r.setAttribute('data-theme', s);
  document.getElementById('theme-toggle')?.addEventListener('click', () => {
    const n = r.getAttribute('data-theme') === 'light' ? 'dark' : 'light';
    r.setAttribute('data-theme', n); localStorage.setItem(k, n);
  });
</script>
</body>
</html>'''

    # ── templates/signup.html ──────────────────────────────────
    files["templates/signup.html"] = '''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Sign Up</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
:root{--bg1:#0a0a0f;--bg2:#12101a;--card:#13131a;--border:#222230;--text:#f0f0f0;--muted:#888;--accent:#f5c842}
[data-theme="light"]{--bg1:#eef2ff;--bg2:#f8fafc;--card:#ffffff;--border:#d7d9e3;--text:#171717;--muted:#555;--accent:#c58000}
body{background:linear-gradient(135deg,var(--bg1),var(--bg2));min-height:100vh;display:flex;align-items:center;justify-content:center;font-family:system-ui,sans-serif;color:var(--text)}
.card{background:var(--card);border:1px solid var(--border);border-radius:20px;padding:2.5rem;width:100%;max-width:440px;box-shadow:0 25px 60px rgba(0,0,0,.25)}
h2{font-size:1.8rem;font-weight:700;text-align:center;margin-bottom:.4rem}
.sub{color:var(--muted);text-align:center;font-size:.9rem;margin-bottom:2rem}
.flash-error{background:rgba(255,107,107,.1);border:1px solid rgba(255,107,107,.3);color:#ff6b6b;padding:.7rem 1rem;border-radius:8px;font-size:.85rem;margin-bottom:1rem}
.flash-success{background:rgba(80,220,140,.1);border:1px solid rgba(80,220,140,.3);color:#50dc8c;padding:.7rem 1rem;border-radius:8px;font-size:.85rem;margin-bottom:1rem}
label{display:block;font-size:.78rem;font-weight:600;color:var(--muted);margin-bottom:.4rem;text-transform:uppercase;letter-spacing:.5px}
input{width:100%;background:transparent;border:1px solid var(--border);border-radius:10px;padding:.85rem 1rem;color:var(--text);font-size:.95rem;outline:none;margin-bottom:1.2rem;transition:.3s}
input:focus{border-color:var(--accent);box-shadow:0 0 0 3px rgba(245,200,66,.1)}
.btn{width:100%;background:var(--accent);color:#000;border:none;padding:1rem;border-radius:10px;font-weight:700;font-size:1rem;cursor:pointer;transition:.3s}
.btn:hover{filter:brightness(1.04);transform:translateY(-2px)}
.link-row{text-align:center;margin-top:1rem;color:var(--muted);font-size:.9rem}
.link-row a{color:var(--accent);text-decoration:none;font-weight:500}
.theme-wrap{text-align:right;margin-bottom:.8rem}
.theme-btn{border:1px solid var(--border);padding:.25rem .7rem;border-radius:999px;background:transparent;color:var(--text);cursor:pointer}
</style>
</head>
<body>
<div class="card">
  <div class="theme-wrap"><button type="button" class="theme-btn" id="theme-toggle">Theme</button></div>
  <h2>Create Account</h2>
  <div class="sub">Join today — it\'s completely free</div>
  {% with messages = get_flashed_messages(with_categories=true) %}
    {% for cat, msg in messages %}
      <div class="flash-{{ cat }}">{{ msg }}</div>
    {% endfor %}
  {% endwith %}
  <form method="POST">
    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
    <label>Username</label>
    <input type="text" name="username" placeholder="Choose a username" required minlength="3">
    <label>Email Address</label>
    <input type="email" name="email" placeholder="your@email.com" required>
    <label>Password</label>
    <input id="pw" type="password" name="password" placeholder="Min 6 characters" required minlength="6">
    <label>Confirm Password</label>
    <input id="cpw" type="password" name="confirm_password" placeholder="Repeat password" required>
    <div id="match-note" class="match-note">Tip: same password type karo (spaces count hote hain).</div>
    <button type="submit" class="btn">Create Free Account →</button>
  </form>
  <div class="link-row">Already have an account? <a href="/login">Sign in</a></div>
</div>
<script>
  const k='app-theme', r=document.documentElement, s=localStorage.getItem(k);
  if(s) r.setAttribute('data-theme', s);
  document.getElementById('theme-toggle')?.addEventListener('click', () => {
    const n = r.getAttribute('data-theme') === 'light' ? 'dark' : 'light';
    r.setAttribute('data-theme', n); localStorage.setItem(k, n);
  });
  const pw = document.getElementById('pw');
  const cpw = document.getElementById('cpw');
  const note = document.getElementById('match-note');
  function checkMatch() {
    if (!pw || !cpw || !note) return;
    if (!cpw.value) {
      note.textContent = 'Tip: same password type karo (spaces count hote hain).';
      note.classList.remove('bad');
      return;
    }
    if (pw.value === cpw.value) {
      note.textContent = 'Passwords match.';
      note.classList.remove('bad');
      return;
    }
    note.textContent = 'Passwords do not match.';
    note.classList.add('bad');
  }
  pw?.addEventListener('input', checkMatch);
  cpw?.addEventListener('input', checkMatch);
</script>
</body>
</html>'''

    # ── templates/forgot_password.html ────────────────────────
    files["templates/forgot_password.html"] = '''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Forgot Password</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#0c1018;color:#eaf0ff;font-family:system-ui,sans-serif;min-height:100vh;display:flex;align-items:center;justify-content:center}
.card{background:#151a24;border:1px solid #2b3444;border-radius:16px;padding:2rem;width:100%;max-width:460px}
label{display:block;margin:.8rem 0 .35rem;color:#9ba7bf}
input{width:100%;padding:.8rem;border-radius:10px;border:1px solid #2b3444;background:#0f141e;color:#eaf0ff}
button{margin-top:1rem;width:100%;padding:.85rem;border:none;border-radius:10px;background:#6ec1ff;color:#001a2d;font-weight:700;cursor:pointer}
a{color:#6ec1ff;text-decoration:none}
.flash-error,.flash-success{margin:.6rem 0;padding:.6rem .8rem;border-radius:8px}
.flash-error{background:rgba(255,107,107,.14);color:#ff8b8b}
.flash-success{background:rgba(80,220,140,.14);color:#78e9ab}
</style>
</head>
<body>
<div class="card">
  <h2>Forgot Password</h2>
  <p style="color:#9ba7bf;margin-top:.3rem;">Enter your email and we'll send a reset link.</p>
  {% with messages = get_flashed_messages(with_categories=true) %}
    {% for cat, msg in messages %}
      <div class="flash-{{ cat }}">{{ msg }}</div>
    {% endfor %}
  {% endwith %}
  <form method="POST">
    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
    <label>Email Address</label>
    <input type="email" name="email" required placeholder="you@example.com">
    <button type="submit">Send Reset Link</button>
  </form>
  <p style="margin-top:1rem;"><a href="/login">Back to login</a></p>
</div>
</body>
</html>'''

    # ── templates/reset_password.html ─────────────────────────
    files["templates/reset_password.html"] = '''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Reset Password</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#0c1018;color:#eaf0ff;font-family:system-ui,sans-serif;min-height:100vh;display:flex;align-items:center;justify-content:center}
.card{background:#151a24;border:1px solid #2b3444;border-radius:16px;padding:2rem;width:100%;max-width:460px}
label{display:block;margin:.8rem 0 .35rem;color:#9ba7bf}
input{width:100%;padding:.8rem;border-radius:10px;border:1px solid #2b3444;background:#0f141e;color:#eaf0ff}
button{margin-top:1rem;width:100%;padding:.85rem;border:none;border-radius:10px;background:#6ec1ff;color:#001a2d;font-weight:700;cursor:pointer}
a{color:#6ec1ff;text-decoration:none}
.flash-error,.flash-success{margin:.6rem 0;padding:.6rem .8rem;border-radius:8px}
.flash-error{background:rgba(255,107,107,.14);color:#ff8b8b}
.flash-success{background:rgba(80,220,140,.14);color:#78e9ab}
</style>
</head>
<body>
<div class="card">
  <h2>Reset Password</h2>
  {% with messages = get_flashed_messages(with_categories=true) %}
    {% for cat, msg in messages %}
      <div class="flash-{{ cat }}">{{ msg }}</div>
    {% endfor %}
  {% endwith %}
  <form method="POST">
    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
    <label>New Password</label>
    <input type="password" name="password" minlength="6" required>
    <label>Confirm Password</label>
    <input type="password" name="confirm_password" minlength="6" required>
    <button type="submit">Update Password</button>
  </form>
  <p style="margin-top:1rem;"><a href="/login">Back to login</a></p>
</div>
</body>
</html>'''

    # ── templates/dashboard.html ───────────────────────────────
    files["templates/dashboard.html"] = f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Dashboard — {project_name}</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
:root{{--bg:#0a0a0f;--card:#13131a;--accent:#f5c842;--text:#f0f0f0;--muted:#888;--border:#222230}}
[data-theme="light"]{{--bg:#f7f8fc;--card:#ffffff;--accent:#d38b00;--text:#171717;--muted:#555;--border:#ddd}}
body{{background:var(--bg);color:var(--text);font-family:system-ui,sans-serif;min-height:100vh}}
nav{{display:flex;justify-content:space-between;align-items:center;padding:1.2rem 2.5rem;background:rgba(10,10,15,.9);border-bottom:1px solid var(--border);position:sticky;top:0;z-index:50}}
.logo{{font-size:1.3rem;font-weight:700;color:var(--accent);text-decoration:none}}
.nav-right{{display:flex;align-items:center;gap:1rem}}
.badge{{background:rgba(245,200,66,.1);border:1px solid rgba(245,200,66,.2);color:var(--accent);padding:.3rem .8rem;border-radius:20px;font-size:.85rem}}
.logout{{color:var(--muted);text-decoration:none;font-size:.9rem;transition:.3s}}
.logout:hover{{color:#ff6b6b}}
.theme-btn{{border:1px solid var(--border);background:transparent;color:var(--text);padding:.35rem .75rem;border-radius:999px;cursor:pointer}}
main{{max-width:1100px;margin:0 auto;padding:3rem 2rem}}
.header-row{{display:flex;justify-content:space-between;align-items:flex-end;margin-bottom:2rem;flex-wrap:wrap;gap:1rem}}
.header-row h1{{font-size:2rem;font-weight:700}}
.header-row p{{color:var(--muted);margin-top:.3rem;font-size:.9rem}}
.btn-new{{background:var(--accent);color:#000;padding:.8rem 1.8rem;border-radius:10px;text-decoration:none;font-weight:700;font-size:.9rem;transition:.3s}}
.btn-new:hover{{background:#ffd700;transform:translateY(-2px)}}
.flash-error{{background:rgba(255,107,107,.1);border:1px solid rgba(255,107,107,.3);color:#ff6b6b;padding:.7rem 1rem;border-radius:8px;font-size:.85rem;margin-bottom:1rem}}
.flash-success{{background:rgba(80,220,140,.1);border:1px solid rgba(80,220,140,.3);color:#50dc8c;padding:.7rem 1rem;border-radius:8px;font-size:.85rem;margin-bottom:1rem}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:1.5rem}}
.card{{background:var(--card);border:1px solid var(--border);border-radius:16px;padding:1.8rem;transition:.4s;position:relative;overflow:hidden}}
.card::before{{content:\'\';position:absolute;top:0;left:0;right:0;height:3px;background:linear-gradient(90deg,var(--accent),#ff6b6b);transform:scaleX(0);transform-origin:left;transition:.4s}}
.card:hover::before{{transform:scaleX(1)}}
.card:hover{{transform:translateY(-5px);box-shadow:0 15px 40px rgba(0,0,0,.4)}}
.card-icon{{width:44px;height:44px;background:rgba(245,200,66,.1);border-radius:10px;display:flex;align-items:center;justify-content:center;font-size:1.3rem;margin-bottom:1rem}}
.card-title{{font-size:1.1rem;font-weight:700;margin-bottom:.3rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.card-date{{color:var(--muted);font-size:.8rem;margin-bottom:1.2rem}}
.card-actions{{display:flex;gap:.6rem;flex-wrap:wrap}}
.btn-sm{{padding:.4rem .9rem;border-radius:7px;font-size:.82rem;font-weight:600;text-decoration:none;transition:.3s;cursor:pointer;border:none;font-family:inherit}}
.btn-view{{background:rgba(245,200,66,.12);color:var(--accent);border:1px solid rgba(245,200,66,.25)}}
.btn-view:hover{{background:rgba(245,200,66,.25)}}
.btn-edit{{background:rgba(100,150,255,.1);color:#7aadff;border:1px solid rgba(100,150,255,.25)}}
.btn-edit:hover{{background:rgba(100,150,255,.2)}}
.btn-pdf{{background:rgba(80,220,140,.1);color:#50dc8c;border:1px solid rgba(80,220,140,.25)}}
.btn-pdf:hover{{background:rgba(80,220,140,.2)}}
.btn-del{{background:rgba(255,107,107,.08);color:#ff6b6b;border:1px solid rgba(255,107,107,.2)}}
.btn-del:hover{{background:rgba(255,107,107,.2)}}
.empty{{text-align:center;padding:5rem 2rem;color:var(--muted)}}
.empty .icon{{font-size:4rem;margin-bottom:1rem;opacity:.3}}
.empty h3{{font-size:1.2rem;color:var(--text);margin-bottom:.5rem}}
</style>
</head>
<body>
<nav>
  <a href="/" class="logo">{project_name}</a>
  <div class="nav-right">
    <button id="theme-toggle" class="theme-btn" type="button">Theme</button>
    <span class="badge">👤 {{{{ current_user.username }}}}</span>
    <a href="/logout" class="logout">Logout</a>
  </div>
</nav>
<main>
  <div class="header-row">
    <div><h1>Dashboard</h1><p>Manage all your items</p></div>
    <div style="display:flex;gap:.6rem;flex-wrap:wrap;">
      <a href="/project/export.zip" class="btn-new">Download ZIP</a>
      <a href="/item/new" class="btn-new">+ New Item</a>
    </div>
  </div>
  {{% if not current_user.is_verified %}}
    <div class="flash-error">
      Email not verified.
      <form method="POST" action="/resend-verification" style="display:inline;">
        <input type="hidden" name="csrf_token" value="{{{{ csrf_token() }}}}">
        <input type="hidden" name="email" value="{{{{ current_user.email }}}}">
        <button type="submit" class="btn-sm btn-view">Resend verification</button>
      </form>
    </div>
  {{% endif %}}
  {{% if fallback_msg %}}
    <div id="fallback-alert" class="flash-error" style="position:relative;padding-right:7rem;">
      AI generation failed: {{{{ fallback_msg }}}} (using default scaffold)
      <form method="POST" action="/fallback/clear" style="display:inline;position:absolute;top:6px;right:34px;">
        <input type="hidden" name="csrf_token" value="{{{{ csrf_token() }}}}">
        <button type="submit" style="background:none;border:none;color:#ff6b6b;cursor:pointer;">Clear</button>
      </form>
      <button onclick="this.parentElement.style.display='none'" style="position:absolute;top:8px;right:10px;background:none;border:none;color:#ff6b6b;cursor:pointer;">✕</button>
    </div>
    <script>
      setTimeout(() => {{
        const alert = document.getElementById('fallback-alert');
        if (alert) alert.style.display = 'none';
      }}, 10000);
    </script>
  {{% endif %}}
  {{% with messages = get_flashed_messages(with_categories=true) %}}
    {{% for cat, msg in messages %}}
      <div class="flash-{{{{cat}}}}">{{{{msg}}}}</div>
    {{% endfor %}}
  {{% endwith %}}
  {{% if items %}}
    <div class="grid">
      {{% for item in items %}}
      <div class="card">
        <div class="card-icon">📄</div>
        <div class="card-title">{{{{item.title}}}}</div>
        <div class="card-date">Updated {{{{item.updated_at.strftime(\'%b %d, %Y\')}}}}</div>
        <div class="card-actions">
          <a href="/item/{{{{item.id}}}}"      class="btn-sm btn-view">👁 View</a>
          <a href="/item/{{{{item.id}}}}/edit" class="btn-sm btn-edit">✏️ Edit</a>
          <a href="/item/{{{{item.id}}}}/pdf"  class="btn-sm btn-pdf">⬇️ PDF</a>
          <form method="POST" action="/item/{{{{item.id}}}}/delete" style="display:inline"
                onsubmit="return confirm(\'Delete this item?\')">
            <input type="hidden" name="csrf_token" value="{{{{ csrf_token() }}}}">
            <button type="submit" class="btn-sm btn-del">🗑 Delete</button>
          </form>
        </div>
      </div>
      {{% endfor %}}
    </div>
  {{% else %}}
    <div class="empty">
      <div class="icon">📋</div>
      <h3>No items yet</h3>
      <p>Create your first item to get started</p>
      <br><a href="/item/new" class="btn-new">+ Create First Item</a>
    </div>
  {{% endif %}}
</main>
<script>
  const k='app-theme', r=document.documentElement, s=localStorage.getItem(k);
  if(s) r.setAttribute('data-theme', s);
  document.getElementById('theme-toggle')?.addEventListener('click', () => {{
    const n = r.getAttribute('data-theme') === 'light' ? 'dark' : 'light';
    r.setAttribute('data-theme', n); localStorage.setItem(k, n);
  }});
</script>
</body>
</html>'''

    # ── templates/item_form.html ──────────────────────────────
    files["templates/item_form.html"] = '''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{% if item %}Edit{% else %}New{% endif %} Item</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#0a0a0f;color:#f0f0f0;font-family:system-ui,sans-serif;min-height:100vh}
.wrap{max-width:900px;margin:2rem auto;padding:1rem}
.card{background:#13131a;border:1px solid #222230;border-radius:14px;padding:1.2rem}
label{display:block;margin:.8rem 0 .3rem;color:#aaa;font-size:.85rem}
input,textarea{width:100%;background:#0d0d14;border:1px solid #2a2a38;border-radius:10px;padding:.8rem;color:#f0f0f0}
textarea{min-height:180px;resize:vertical}
.row{display:flex;gap:.7rem;margin-top:1rem;flex-wrap:wrap}
button,a{padding:.7rem 1rem;border-radius:9px;border:none;cursor:pointer;text-decoration:none}
.btn-primary{background:#f5c842;color:#000;font-weight:700}
.btn-muted{background:#1f2230;color:#f0f0f0}
.msg{margin-top:.8rem;font-size:.9rem}
</style>
</head>
<body>
<div class="wrap">
  <div class="card">
    <h2>{% if item %}Edit Item{% else %}Create Item{% endif %}</h2>
    <label>Title</label>
    <input id="title" type="text" maxlength="100" value="{{ item.title if item else '' }}" placeholder="Enter title">
    <label>Content / Data (JSON or plain text)</label>
    <textarea id="content" placeholder='{"summary":"..."}'>{% if item %}{{ item.data }}{% endif %}</textarea>
    <div class="row">
      <button class="btn-primary" onclick="saveItem()">Save</button>
      <a class="btn-muted" href="/dashboard">Back</a>
    </div>
    <div id="msg" class="msg"></div>
  </div>
</div>
<script>
async function saveItem() {
  const csrfToken = "{{ csrf_token() }}";
  const title = document.getElementById('title').value.trim();
  const raw = document.getElementById('content').value.trim();
  const msg = document.getElementById('msg');
  if (!title) { msg.textContent = 'Title is required'; return; }
  let payload = {};
  try {
    payload = raw ? JSON.parse(raw) : {};
  } catch {
    payload = { content: raw };
  }
  payload.title = title;
  {% if item %}payload.id = {{ item.id }};{% endif %}
  const res = await fetch('/item/save', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
    body: JSON.stringify(payload)
  });
  const data = await res.json();
  if (data.success && data.id) {
    window.location.href = '/item/' + data.id;
    return;
  }
  msg.textContent = data.error || 'Save failed';
}
</script>
</body>
</html>'''

    # ── templates/item_view.html ──────────────────────────────
    files["templates/item_view.html"] = '''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{{ item.title }}</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#0a0a0f;color:#f0f0f0;font-family:system-ui,sans-serif;min-height:100vh}
.wrap{max-width:900px;margin:2rem auto;padding:1rem}
.card{background:#13131a;border:1px solid #222230;border-radius:14px;padding:1.2rem}
pre{white-space:pre-wrap;word-break:break-word;background:#0d0d14;border:1px solid #2a2a38;border-radius:10px;padding:1rem;margin-top:1rem}
.row{display:flex;gap:.7rem;margin-top:1rem;flex-wrap:wrap}
a{padding:.7rem 1rem;border-radius:9px;text-decoration:none}
.btn-primary{background:#f5c842;color:#000;font-weight:700}
.btn-muted{background:#1f2230;color:#f0f0f0}
</style>
</head>
<body>
<div class="wrap">
  <div class="card">
    <h2>{{ item.title }}</h2>
    <div style="color:#888;margin-top:.3rem;">Updated {{ item.updated_at.strftime('%b %d, %Y %H:%M') }}</div>
    <pre>{{ data | tojson(indent=2) }}</pre>
    <div class="row">
      <a class="btn-primary" href="/item/{{ item.id }}/edit">Edit</a>
      <a class="btn-muted" href="/item/{{ item.id }}/pdf">Download PDF</a>
      <a class="btn-muted" href="/dashboard">Back</a>
    </div>
  </div>
</div>
</body>
</html>'''

    # ── templates/item_pdf.html ───────────────────────────────
    files["templates/item_pdf.html"] = '''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>{{ item.title }}</title>
<style>
body{font-family:Arial,sans-serif;color:#111;font-size:12px;padding:20px}
h1{font-size:24px;margin:0 0 8px}
.muted{color:#666;font-size:11px;margin-bottom:14px}
pre{white-space:pre-wrap;word-wrap:break-word;border:1px solid #ddd;padding:10px;border-radius:6px;background:#fafafa}
</style>
</head>
<body>
  <h1>{{ item.title }}</h1>
  <div class="muted">Updated {{ item.updated_at.strftime('%b %d, %Y %H:%M') }}</div>
  <pre>{{ data | tojson(indent=2) }}</pre>
</body>
</html>'''

    # ── templates/404.html ─────────────────────────────────────
    files["templates/404.html"] = '''<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>404</title>
<style>*{margin:0;padding:0;box-sizing:border-box}body{background:#0a0a0f;color:#f0f0f0;font-family:system-ui;min-height:100vh;display:flex;align-items:center;justify-content:center;text-align:center}
h1{font-size:8rem;color:#f5c842;line-height:1}h2{font-size:1.5rem;margin:.5rem 0 1rem}p{color:#888;margin-bottom:2rem}
a{background:#f5c842;color:#000;padding:.8rem 2rem;border-radius:10px;text-decoration:none;font-weight:700}</style></head>
<body><div><h1>404</h1><h2>Page Not Found</h2><p>This page does not exist.</p><a href="/">Go Home →</a></div></body></html>'''

    # ── templates/500.html ─────────────────────────────────────
    files["templates/500.html"] = '''<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>500</title>
<style>*{margin:0;padding:0;box-sizing:border-box}body{background:#0a0a0f;color:#f0f0f0;font-family:system-ui;min-height:100vh;display:flex;align-items:center;justify-content:center;text-align:center}
h1{font-size:8rem;color:#ff6b6b;line-height:1}h2{font-size:1.5rem;margin:.5rem 0 1rem}p{color:#888;margin-bottom:2rem}
a{background:#f5c842;color:#000;padding:.8rem 2rem;border-radius:10px;text-decoration:none;font-weight:700}</style></head>
<body><div><h1>500</h1><h2>Server Error</h2><p>Something went wrong. Please try again.</p><a href="/">Go Home →</a></div></body></html>'''

    return files

# ==================== AI GENERATION ====================
def generate_project_files(user_query: str, config: Dict) -> Dict[str, str]:
    global LAST_AI_FALLBACK_REASON
    LAST_AI_FALLBACK_REASON = None

    def fallback_with_reason(reason: str) -> Dict[str, str]:
        global LAST_AI_FALLBACK_REASON
        LAST_AI_FALLBACK_REASON = reason
        files = fallback_scaffold(slugify(user_query), config)
        files["ai-fallback-reason.txt"] = f"{reason}\n"
        return files

    model_client = ModelManager.get_client(config["model"])
    if model_client is None:
        print_info("AI client unavailable — using production scaffold.")
        return fallback_with_reason("OpenAI client unavailable or OPENAI_API_KEY missing")
    try:
        response = api_guard.call_with_retry(
            model_client.chat.completions.create,
            model=config["model"],
            temperature=MODEL_TEMPERATURE,
            max_tokens=MAX_TOKENS,
            timeout=TIMEOUT_SECONDS,
            messages=[
                {"role": "system", "content": build_system_prompt(config)},
                {"role": "user",   "content": user_query},
            ],
        )
        if not getattr(response, "choices", None):
            print_info("Empty response from AI — using production scaffold.")
            return fallback_with_reason("Empty response from OpenAI")
        text  = response.choices[0].message.content or ""
        
        files = parse_action_blocks(text)
        if files:
            return ensure_project_integrity(files, slugify(user_query), config)
        print_info("No ACTION blocks from AI — using production scaffold.")
        return fallback_with_reason("No ACTION blocks returned by OpenAI")
    except Exception as e:
        logger.warning("AI generation failed: %s", e)
        print_error(f"AI error: {e}")
        print_info("Using production scaffold instead.")
        return fallback_with_reason(f"OpenAI call failed: {e}")

def generate_ai_bullets(section: str, context: str, model: str = "gpt-4o-mini") -> List[str]:
    """Generate AI bullet points for resume/content sections"""
    model_client = ModelManager.get_client(model)
    if model_client is None:
        return ["• Built and maintained core application features",
                "• Collaborated with team to deliver projects on time",
                "• Improved system performance by 25%"]
    try:
        response = api_guard.call_with_retry(
            model_client.chat.completions.create,
            model=model,
            temperature=0.7,
            max_tokens=300,
            timeout=TIMEOUT_SECONDS,
            messages=[{"role": "user", "content": build_resume_ai_prompt(section, context)}]
        )
        if not getattr(response, "choices", None):
            return ["• Built and maintained core application features"]
        text    = response.choices[0].message.content or ""
        bullets = [line.strip() for line in text.split("\n") if line.strip().startswith("•")]
        return bullets if bullets else ["• " + line.strip() for line in text.split("\n") if line.strip()]
    except Exception as e:
        logger.warning("AI bullets failed: %s", e)
        return ["• Built and maintained core application features"]

def save_files_to_project(project_dir: Path, files: Dict[str, str]) -> List[str]:
    saved: List[str] = []
    base_dir = project_dir.resolve()
    for filename, content in files.items():
        normalized = os.path.normpath(filename)
        if os.path.isabs(normalized):
            logger.warning("Skipping absolute path: %s", filename)
            continue
        target = (base_dir / normalized).resolve()
        try:
            if os.path.commonpath([str(base_dir), str(target)]) != str(base_dir):
                logger.warning("Blocked path traversal: %s", filename)
                continue
        except ValueError:
            continue
        if len(content.encode("utf-8")) > MAX_FILE_BYTES:
            logger.warning("Skipping oversized file: %s", filename)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        saved.append(filename)
    return saved

def collect_project_context_files(project_dir: Path) -> List[Tuple[str, str]]:
    allowed_ext = {".py", ".html", ".css", ".js", ".json", ".md", ".txt", ".yml", ".yaml"}
    blocked_dirs = {".git", ".venv", "venv", "__pycache__", "node_modules", ".pytest_cache"}
    collected: List[Tuple[str, str]] = []

    for path in sorted(project_dir.rglob("*")):
        if not path.is_file():
            continue
        if any(part in blocked_dirs for part in path.parts):
            continue
        if path.suffix.lower() not in allowed_ext:
            continue
        try:
            size = path.stat().st_size
            if size > MAX_REVISION_FILE_BYTES:
                continue
            rel = str(path.relative_to(project_dir)).replace("\\", "/")
            content = path.read_text(encoding="utf-8", errors="replace")
            collected.append((rel, content))
        except Exception:
            continue
        if len(collected) >= MAX_REVISION_FILES:
            break
    return collected

def build_revision_prompt(feedback: str, context_files: List[Tuple[str, str]]) -> str:
    files_blob_parts = []
    for rel, content in context_files:
        files_blob_parts.append(f"FILE:{rel}\n{content}\n")
    files_blob = "\n".join(files_blob_parts)
    return f"""You are a senior software engineer doing iterative project revision.
User feedback to apply:
{feedback}

Current project files are below. Update only what's needed.
{files_blob}

Return ONLY ACTION:save_file blocks for changed/new files.
No markdown fences. No explanation text.
"""

def apply_feedback_revision(project_dir: Path, feedback: str, config: Dict[str, str]) -> List[str]:
    model_client = ModelManager.get_client(config["model"])
    if model_client is None:
        print_error("AI client unavailable; cannot run revision loop.")
        return []

    context_files = collect_project_context_files(project_dir)
    if not context_files:
        print_error("No project files found for revision.")
        return []

    try:
        prompt = build_revision_prompt(feedback, context_files)
        response = api_guard.call_with_retry(
            model_client.chat.completions.create,
            model=config["model"],
            temperature=0.2,
            max_tokens=MAX_TOKENS,
            timeout=TIMEOUT_SECONDS,
            messages=[{"role": "user", "content": prompt}],
        )
        if not getattr(response, "choices", None):
            return []
        text = response.choices[0].message.content or ""
        changed = parse_action_blocks(text)
        if not changed:
            return []
        return save_files_to_project(project_dir, changed)
    except Exception as e:
        logger.warning("Revision loop failed: %s", e)
        return []

def ensure_basic_pytest(project_dir: Path) -> bool:
    tests_dir = project_dir / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)
    test_file = tests_dir / "test_smoke.py"
    if test_file.exists():
        return False
    test_file.write_text(
        "def test_smoke_import_app():\n"
        "    import importlib.util\n"
        "    from pathlib import Path\n"
        "    app_path = Path(__file__).resolve().parents[1] / 'app.py'\n"
        "    spec = importlib.util.spec_from_file_location('generated_app', app_path)\n"
        "    assert spec is not None and spec.loader is not None\n"
        "    module = importlib.util.module_from_spec(spec)\n"
        "    spec.loader.exec_module(module)\n"
        "    assert hasattr(module, 'app')\n",
        encoding="utf-8",
    )
    return True

def run_pytest_once(project_dir: Path) -> Tuple[bool, str]:
    cmd = [sys.executable, "-m", "pytest", "-q"]
    result = subprocess.run(
        cmd,
        cwd=str(project_dir),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )
    output = (result.stdout or "") + ("\n" + result.stderr if result.stderr else "")
    return result.returncode == 0, output[-8000:]

def ensure_pytest_available() -> bool:
    check = subprocess.run(
        [sys.executable, "-c", "import pytest; print(pytest.__version__)"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
    )
    if check.returncode == 0:
        return True
    if AUTO_INSTALL_PACKAGES:
        install = subprocess.run(
            [sys.executable, "-m", "pip", "install", "pytest"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
        )
        return install.returncode == 0
    print_info("Pytest is not installed in current Python. Use --auto-install or install pytest manually.")
    return False

def self_fix_from_test_error(project_dir: Path, config: Dict[str, str], test_output: str) -> List[str]:
    model_client = ModelManager.get_client(config["model"])
    if model_client is None:
        return []
    context_files = collect_project_context_files(project_dir)
    if not context_files:
        return []

    files_blob_parts = []
    for rel, content in context_files:
        files_blob_parts.append(f"FILE:{rel}\n{content}\n")
    files_blob = "\n".join(files_blob_parts)

    prompt = f"""Fix the project so tests pass.
Pytest output:
{test_output}

Current files:
{files_blob}

Return ONLY ACTION:save_file blocks for modified files.
"""
    try:
        response = api_guard.call_with_retry(
            model_client.chat.completions.create,
            model=config["model"],
            temperature=0.1,
            max_tokens=MAX_TOKENS,
            timeout=TIMEOUT_SECONDS,
            messages=[{"role": "user", "content": prompt}],
        )
        if not getattr(response, "choices", None):
            return []
        text = response.choices[0].message.content or ""
        changed = parse_action_blocks(text)
        if not changed:
            return []
        return save_files_to_project(project_dir, changed)
    except Exception as e:
        logger.warning("Self-fix loop failed: %s", e)
        return []

def run_tests_with_self_fix(project_dir: Path, config: Dict[str, str], attempts: int) -> bool:
    if not ensure_pytest_available():
        return False
    ensure_basic_pytest(project_dir)
    for attempt in range(1, attempts + 1):
        ok, output = run_pytest_once(project_dir)
        if ok:
            print_success(f"Tests passed on attempt {attempt}")
            return True
        print_error(f"Tests failed on attempt {attempt}")
        if attempt == attempts:
            print_info("Reached max self-fix attempts.")
            print_info(output[-600:])
            return False
        changed_files = self_fix_from_test_error(project_dir, config, output)
        if not changed_files:
            print_info("Self-fix could not produce patch from test errors.")
            print_info(output[-600:])
            return False
        print_info(f"Self-fix updated {len(changed_files)} file(s): {', '.join(changed_files[:5])}")
    return False

def run_git_auto_init(project_dir: Path, commit_message: str) -> bool:
    def _run(args: List[str]) -> subprocess.CompletedProcess:
        return subprocess.run(
            args,
            cwd=str(project_dir),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )

    try:
        _run(["git", "init"])
        _run(["git", "add", "."])
        status = _run(["git", "status", "--porcelain"])
        if not status.stdout.strip():
            print_info("No changes to commit.")
            return True
        commit = _run(["git", "commit", "-m", commit_message])
        if commit.returncode == 0:
            print_success("Git initial commit created.")
            return True
        identity_error = "Please tell me who you are" in (commit.stderr or "")
        if identity_error:
            _run(["git", "config", "user.name", CREATOR])
            _run(["git", "config", "user.email", f"{CREATOR_GITHUB}@users.noreply.github.com"])
            retry = _run(["git", "commit", "-m", commit_message])
            if retry.returncode == 0:
                print_success("Git initial commit created.")
                return True
            print_error(f"Git commit failed: {retry.stderr.strip()[:250]}")
            return False
        print_error(f"Git commit failed: {commit.stderr.strip()[:250]}")
        return False
    except Exception as e:
        print_error(f"Git init/commit failed: {e}")
        return False

def write_deploy_helper(project_dir: Path, project_name: str) -> None:
    deploy_md = project_dir / "DEPLOY.md"
    content = f"""# Deploy Helper

## One-Click Links

- Render: https://render.com/deploy?repo=<YOUR_GITHUB_REPO_URL>
- Railway: https://railway.app/new?referralCode=<YOUR_CODE>

## Quick Commands

```bash
# 1) Push project to GitHub first
git init
git add .
git commit -m "deploy prep"
git branch -M main
git remote add origin <YOUR_GITHUB_REPO_URL>
git push -u origin main
```

```bash
# 2) Required env vars in hosting dashboard
SECRET_KEY=<generate-random-secret>
DATABASE_URL=sqlite:///app.db
OPENAI_API_KEY=<optional>
```

## Procfile

This project already includes:

```text
web: gunicorn app:app
```

## App Name

`{project_name}`
"""
    deploy_md.write_text(content, encoding="utf-8")

# ==================== TERMINAL AGENT ====================
class TerminalAgent:
    def __init__(self):
        self.history = []

    def run_command(self, command: str, auto_fix: bool = True) -> Dict:
        print_working(f"Terminal: {command}")
        try:
            result = subprocess.run(
                command, shell=True, capture_output=True,
                text=True, timeout=30, encoding="utf-8", errors="replace"
            )
            self.history.append({"command": command, "returncode": result.returncode})
            if result.returncode == 0:
                print_success(f"Done: {command}")
                return {"status": "success", "output": result.stdout}
            print_error(f"Failed: {command}")
            print_info(f"Error: {result.stderr[:200]}")
            if auto_fix:
                return self.auto_fix(command, result.stderr)
            return {"status": "failed", "error": result.stderr}
        except subprocess.TimeoutExpired:
            return {"status": "timeout", "output": "Timed out"}
        except Exception as e:
            return {"status": "error", "message": str(e)[:100]}

    def auto_fix(self, command: str, error: str) -> Dict:
        print_working("Attempting auto-fix...")
        if "ModuleNotFoundError" in error or "No module named" in error:
            match = re.search(r"No module named ['\"]?([\w\.\-]+)['\"]?", error)
            if match:
                pkg = match.group(1).split(".")[0]
                if not AUTO_INSTALL_PACKAGES:
                    print_info(f"Run: pip install {pkg}")
                    return {"status": "failed", "error": "Auto-install disabled"}
                self.run_command(f"{sys.executable} -m pip install {shlex.quote(pkg)}", auto_fix=False)
                return self.run_command(command, auto_fix=False)
        elif "address already in use" in error.lower():
            return self.run_command(command.replace(":5000", ":5001"), auto_fix=False)
        return {"status": "failed", "error": error[:300]}

    def run_tests(self) -> Dict:
        return self.run_command("pytest -v --cov=.", auto_fix=True)

terminal = TerminalAgent()

# ==================== MULTI-AGENT SYSTEM ====================
class MultiAgentSystem:
    async def execute_parallel(self, user_query: str, config: Dict) -> Dict:
        print(f"\n{Colors.BOLD}🚀 Multi-Agent Execution{Colors.ENDC}\n")
        files_map = generate_project_files(user_query, config)
        print_success("Multi-agent execution complete")
        return {"coder": {"files": files_map, "status": "generated"}}

multi_agent = MultiAgentSystem()

# ==================== ENVIRONMENT VALIDATION ====================
def validate_environment():
    ensure_openai_client()
    if client is None:
        print_info("OpenAI unavailable — production scaffold mode active.")
        return
    if not os.getenv("OPENAI_API_KEY"):
        print_info("OPENAI_API_KEY not set — using scaffold mode.")
        return
    print_success("Environment validated — AI mode active")

# ==================== MAIN ====================
def main():
    global LAST_AI_FALLBACK_REASON
    LAST_AI_FALLBACK_REASON = None

    parser = argparse.ArgumentParser(description=f"AI Web Developer Agent v{VERSION}")
    parser.add_argument("--mode",     choices=["web", "api", "saas"], default="web")
    parser.add_argument("--db",       choices=["sqlite", "postgresql", "mysql"], default="sqlite")
    parser.add_argument("--model",    choices=["gpt-4o", "gpt-4o-mini", "o1-mini"], default="gpt-4o-mini")
    parser.add_argument("--parallel", action="store_true")
    parser.add_argument("--run-tests",action="store_true")
    parser.add_argument("--auto-install", action="store_true")
    parser.add_argument("--query",    help="Project description (non-interactive)")
    parser.add_argument("--project",  help="Existing project folder path for revisions/self-fix")
    parser.add_argument("--list-projects", action="store_true",
                        help="List known projects from local history index")
    parser.add_argument("--feedback", action="append",
                        help="Revision feedback (repeatable). Example: --feedback \"Add dark mode toggle\"")
    parser.add_argument("--revision-rounds", type=int, default=DEFAULT_REVISION_ROUNDS,
                        help="Max iterative revision rounds (default: 3)")
    parser.add_argument("--self-fix-attempts", type=int, default=DEFAULT_SELF_FIX_ATTEMPTS,
                        help="Max test self-fix attempts (default: 3)")
    parser.add_argument("--ai-bullets", nargs=2, metavar=("SECTION","CONTEXT"),
                        help="Generate AI bullet points: --ai-bullets 'Work Experience' 'Python developer at Google'")
    parser.add_argument("--auto-test-fix", action="store_true",
                        help="Run pytest and AI self-fix loop")
    parser.add_argument("--git-init", action="store_true",
                        help="Auto init git and create initial commit")
    parser.add_argument("--deploy-helper", action="store_true",
                        help="Generate/update DEPLOY.md helper file for the project")
    args = parser.parse_args()

    global AUTO_INSTALL_PACKAGES
    AUTO_INSTALL_PACKAGES = bool(args.auto_install)
    original_cwd = Path.cwd()
    history_file = original_cwd / PROJECT_HISTORY_FILE

    if args.list_projects:
        print_project_history(history_file)
        return

    # AI bullets mode
    if args.ai_bullets:
        section, context = args.ai_bullets
        print(f"\n{Colors.BOLD}🤖 AI Bullet Points for: {section}{Colors.ENDC}\n")
        bullets = generate_ai_bullets(section, context, args.model)
        for b in bullets:
            print(f"{Colors.OKGREEN}{b}{Colors.ENDC}")
        return

    print_banner()
    if not WEASYPRINT_AVAILABLE:
        print_error("WARNING: WeasyPrint missing - PDF generation disabled in generated projects")
    validate_environment()

    config = {"mode": args.mode, "database": args.db, "model": args.model}

    user_query = ""
    project_dir: Optional[Path] = None
    project_name = ""

    if args.project:
        resolved = resolve_project_reference(args.project, original_cwd, history_file)
        project_dir = resolved if resolved is not None else Path(args.project).expanduser().resolve()
        if not project_dir.exists() or not project_dir.is_dir():
            print_error(f"Project folder not found: {project_dir}")
            return
        project_name = project_dir.name
        user_query = args.query.strip() if args.query else project_name
    else:
        if args.query:
            user_query = args.query.strip()
        else:
            prompt = f"\n{Colors.BOLD}{Colors.OKGREEN}👨‍💻 Describe your app:{Colors.ENDC} "
            user_query = extract_query_from_command_like_input(input(prompt))

        if not user_query or user_query.lower() in EXIT_COMMANDS:
            return

        requested_name = normalize_project_dir_name(fit_project_name_to_path(Path.cwd(), slugify(user_query)))
        project_name = resolve_unique_project_name(Path.cwd(), requested_name)
        project_dir = original_cwd / project_name

        if project_name != requested_name:
            print_info(f"Project folder already existed, using: {project_name}")
        project_dir.mkdir()

    try:
        assert project_dir is not None
        os.chdir(project_dir)

        if not args.project:
            if args.parallel:
                results  = asyncio.run(multi_agent.execute_parallel(user_query, config))
                files_map = results["coder"]["files"]
            else:
                files_map = generate_project_files(user_query, config)

            files_created = save_generated_files(files_map)
            print_success(f"Created {len(files_created)} files")
            for f in files_created:
                print(f"  {Colors.OKCYAN}📄 {f}{Colors.ENDC}")
            if LAST_AI_FALLBACK_REASON:
                logger.warning("Fallback scaffold used: %s", LAST_AI_FALLBACK_REASON)
                print_info(f"AI fallback active: {LAST_AI_FALLBACK_REASON}")

        feedbacks = args.feedback or []
        rounds = max(0, min(args.revision_rounds, DEFAULT_REVISION_ROUNDS))
        for i, feedback in enumerate(feedbacks[:rounds], start=1):
            print_working(f"Revision {i}/{rounds}: {feedback}")
            changed = apply_feedback_revision(project_dir, feedback, config)
            if changed:
                print_success(f"Revision {i} applied to {len(changed)} file(s)")
            else:
                print_info(f"Revision {i} produced no changes")

        if args.auto_test_fix:
            print_working("Running pytest self-fix loop...")
            run_tests_with_self_fix(project_dir, config, max(1, args.self_fix_attempts))

        if args.run_tests:
            print(f"\n{Colors.BOLD}🧪 Running Tests:{Colors.ENDC}\n")
            terminal.run_tests()

        if args.git_init:
            print_working("Initializing git and creating initial commit...")
            run_git_auto_init(project_dir, f"Initial commit by AI Agent v{VERSION}")

        if args.deploy_helper or not args.project:
            write_deploy_helper(project_dir, project_name)
            print_success("DEPLOY.md helper generated.")

        upsert_project_history(history_file, project_dir, user_query, config)

        print(f"\n{Colors.OKGREEN}{Colors.BOLD}✅ Project '{project_name}' ready!{Colors.ENDC}")
        print(f"\n{Colors.WARNING}Next steps:{Colors.ENDC}")
        env_copy_cmd = "python -c \"from shutil import copyfile; copyfile('.env.example', '.env')\""
        print(f"  cd {project_name}")
        print(f"  pip install -r requirements.txt")
        print(f"  {env_copy_cmd}")
        print(f"  python app.py")
        print(f"\n{Colors.OKCYAN}🏆 Built by {CREATOR} — v{VERSION}{Colors.ENDC}\n")

    except Exception as e:
        logger.error(f"Error: {e}")
        print_error(f"Something went wrong: {e}")
    finally:
        os.chdir(original_cwd)

if __name__ == "__main__":
    main()