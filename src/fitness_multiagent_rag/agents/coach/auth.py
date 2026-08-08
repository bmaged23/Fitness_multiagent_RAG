"""
Authentication: login/signup terminal flow, password hashing (scrypt), username helpers.

All auth runs in Python before the Coach agent starts — the LLM never sees passwords.
"""
from __future__ import annotations

import hashlib
import os
import re
import string
import sys
import termios
import tty
from pathlib import Path
from typing import Optional


sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))

from fitness_multiagent_rag.db import crud
from fitness_multiagent_rag.db.models import Trainee

# ── ANSI ──────────────────────────────────────────────────────────────────────
_CYAN = "\033[96m"
_BOLD = "\033[1m"
_DIM  = "\033[2m"
_RED  = "\033[91m"
_GRN  = "\033[92m"
_YEL  = "\033[93m"
_RST  = "\033[0m"


# ── Password: scrypt hashing (memory-hard, GPU-resistant) ────────────────────

_SCRYPT_N = 2**14   # OWASP-recommended interactive-login cost (16 MB RAM, ~100 ms)
_SCRYPT_R = 8       # block size
_SCRYPT_P = 1       # parallelisation


def _hash_password(password: str) -> str:
    """Return 'salt_hex:dk_hex' using scrypt."""
    salt = os.urandom(32)
    dk = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
    )
    return salt.hex() + ":" + dk.hex()


def _verify_password(password: str, stored: str) -> bool:
    try:
        salt_hex, dk_hex = stored.split(":", 1)
        salt = bytes.fromhex(salt_hex)
        dk = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=_SCRYPT_N,
            r=_SCRYPT_R,
            p=_SCRYPT_P,
        )
        return dk.hex() == dk_hex
    except Exception:
        return False


def validate_password(pw: str) -> tuple[bool, str]:
    """Password must be ≥ 8 chars and contain letters, digits, AND punctuation."""
    if len(pw) < 8:
        return False, "Password must be at least 8 characters."
    if not any(c.isalpha() for c in pw):
        return False, "Password must contain at least one letter (a–z / A–Z)."
    if not any(c.isdigit() for c in pw):
        return False, "Password must contain at least one number (0–9)."
    if not any(c in string.punctuation for c in pw):
        sample = "".join(list(string.punctuation)[:12])
        return False, f"Password must contain at least one special character (e.g. {sample})."
    return True, ""


# ── Username helpers ──────────────────────────────────────────────────────────

_USERNAME_RE = re.compile(r"^[a-z0-9_]{3,20}$")


def validate_username_format(username: str) -> tuple[bool, str]:
    if not _USERNAME_RE.match(username):
        return False, "Username: 3–20 chars, lowercase letters, digits, or underscores only."
    return True, ""


def suggest_usernames(name: str) -> list[str]:
    """Return up to 3 available username suggestions based on the trainee's display name."""
    import random
    base = re.sub(r"[^a-z0-9]", "", name.lower())
    if not base:
        base = "user"
    candidates = [
        base[:20],
        (base[:16] + "_fit")[:20],
        (base[:18] + str(random.randint(10, 99)))[:20],
    ]
    results = []
    for c in candidates:
        if len(c) >= 3 and validate_username_format(c)[0] and not crud.username_exists(c):
            results.append(c)
        if len(results) == 3:
            break
    return results


# ── Terminal I/O ──────────────────────────────────────────────────────────────

def _read_starred(prompt: str) -> str:
    """Read password from terminal, echoing '*' for each character typed.
    Handles backspace and Ctrl+C."""
    print(f"  {_BOLD}{prompt}{_RST}", end="", flush=True)
    chars: list[str] = []
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        while True:
            ch = os.read(fd, 1).decode("utf-8", errors="ignore")
            if ch in ("\r", "\n"):
                print()
                break
            elif ch in ("\x7f", "\x08"):  # backspace / delete
                if chars:
                    chars.pop()
                    sys.stdout.write("\b \b")
                    sys.stdout.flush()
            elif ch == "\x03":  # Ctrl+C
                print()
                raise KeyboardInterrupt
            else:
                chars.append(ch)
                sys.stdout.write("*")
                sys.stdout.flush()
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
    return "".join(chars)


def _ask(prompt: str) -> str:
    return input(f"  {_BOLD}{prompt}{_RST}").strip()


def _ask_password(prompt: str) -> str:
    return _read_starred(prompt)


def _ok(msg: str) -> None:
    print(f"  {_GRN}✓  {msg}{_RST}")


def _err(msg: str) -> None:
    print(f"  {_RED}✗  {msg}{_RST}")


def _info(msg: str) -> None:
    print(f"  {_DIM}{msg}{_RST}")


def _header(title: str) -> None:
    print(f"\n{_CYAN}{'═' * 62}{_RST}")
    print(f"{_CYAN}  {_BOLD}{title}{_RST}{_CYAN}{_RST}")
    print(f"{_CYAN}{'═' * 62}{_RST}\n")


# ── Login ─────────────────────────────────────────────────────────────────────

def do_login() -> Optional[Trainee]:
    """Prompt for username → then password. Returns Trainee (no credentials) on success."""
    _header("LOGIN")
    while True:
        username = _ask("Username › ").lower()
        if not username:
            continue
        password = _ask_password("Password › ")
        # Step 1: find the auth record by username (credentials table only)
        auth = crud.get_auth_by_username(username)
        # Step 2: verify password against the stored scrypt hash
        if auth and _verify_password(password, auth.password_hash):
            # Step 3: load the profile from trainees (no credentials exposed)
            trainee = crud.get_trainee_by_id(auth.trainee_id)
            if trainee:
                trainee.username = username  # runtime-only display field
                _ok(f"Welcome back, {trainee.name}!")
                return trainee

        # Generic error — never reveal which part failed (security best practice)
        _err("Incorrect username or password.")
        print()
        print(f"  {_DIM}[1]{_RST}  Try again")
        print(f"  {_DIM}[2]{_RST}  Sign up instead")
        print(f"  {_DIM}[q]{_RST}  Quit")
        print()
        while True:
            choice = input(f"  {_BOLD}Choose › {_RST}").strip().lower()
            if choice in ("1", "try again", "retry", ""):
                print()
                break
            if choice in ("2", "signup", "sign up", "s", "register"):
                return do_signup()
            if choice in ("q", "quit", "exit"):
                return None
            _err("Enter '1' to try again, '2' to sign up, or 'q' to quit.")


# ── Signup ────────────────────────────────────────────────────────────────────

def do_signup() -> Optional[Trainee]:
    """Collect all signup fields and create a new Trainee. Returns the saved Trainee."""
    _header("CREATE YOUR ACCOUNT")

    # ── Mandatory fields ──────────────────────────────────────────────────────
    _info("Mandatory fields\n")

    name = ""
    while not name:
        name = _ask("Full name  › ")
        if not name:
            _err("Name is required.")

    email = ""
    while not email:
        email = _ask("Email      › ")
        if not email:
            _err("Email is required.")

    phone = ""
    while not phone:
        phone = _ask("Phone      › ")
        if not phone:
            _err("Phone number is required.")

    age: int = 0
    while age <= 0:
        raw = _ask("Age        › ")
        try:
            age = int(raw)
            if age <= 0:
                raise ValueError
        except ValueError:
            _err("Please enter a valid age (number).")

    gender = ""
    while not gender:
        raw = _ask("Gender (male / female) › ").lower().strip()
        if raw in ("male", "m"):
            gender = "male"
        elif raw in ("female", "f"):
            gender = "female"
        else:
            _err("Please enter 'male' or 'female'.")

    # ── Username ──────────────────────────────────────────────────────────────
    print(f"\n{_CYAN}  {'─' * 58}{_RST}")
    _info("Choose a username\n")
    suggestions = suggest_usernames(name)
    if suggestions:
        _info("Suggestions based on your name:")
        for s in suggestions:
            print(f"    {_CYAN}→  {s}{_RST}")
        print()

    username = ""
    while not username:
        raw = _ask("Username   › ").lower().strip()
        ok, reason = validate_username_format(raw)
        if not ok:
            _err(reason)
            continue
        if crud.username_exists(raw):
            _err(f"'{raw}' is already taken. Please choose another.")
            continue
        username = raw
    _ok(f"Username '{username}' is available.")

    # ── Password ──────────────────────────────────────────────────────────────
    print(f"\n{_CYAN}  {'─' * 58}{_RST}")
    _info("Create a password")
    _info("Requirements: letters + numbers + special character (e.g. !@#$%)\n")

    password = ""
    while not password:
        pw1 = _ask_password("Password        › ")
        ok, reason = validate_password(pw1)
        if not ok:
            print(f"  {_RED}✗  {reason}{_RST}")
            continue
        pw2 = _ask_password("Confirm password › ")
        if pw1 != pw2:
            print(f"  {_RED}✗  Passwords do not match. Try again.{_RST}")
            continue
        password = pw1
    print(f"  {_GRN}✓  Password accepted.{_RST}")

    # ── Optional body stats ───────────────────────────────────────────────────
    print(f"\n{_CYAN}  {'─' * 58}{_RST}")
    _info("Optional body stats — press Enter to skip\n")

    def _opt_float(prompt: str) -> Optional[float]:
        raw = _ask(prompt)
        if not raw:
            return None
        try:
            v = float(raw)
            return v if v > 0 else None
        except ValueError:
            return None

    height_cm    = _opt_float("Height (cm) › ")
    weight_kg    = _opt_float("Weight (kg) › ")
    body_fat_pct = _opt_float("Body fat %  › ")
    muscle_pct   = _opt_float("Muscle %    › ")

    # ── Optional physique images ──────────────────────────────────────────────
    images_dir: Optional[str] = None
    print()
    raw = _ask("Physique images folder path (or Enter to skip) › ")
    if raw:
        p = Path(raw).expanduser()
        if p.is_dir():
            images_dir = str(p)
            _ok(f"Images folder set: {images_dir}")
        else:
            _err("Path not found — skipping images.")

    # ── Persist (atomic: trainees row + trainee_auth row in one transaction) ──
    trainee = Trainee(
        name=name,
        secondary_id=email,
        email=email,
        phone=phone,
        age=age,
        gender=gender,
        height_cm=height_cm,
        weight_kg=weight_kg,
        body_fat_pct=body_fat_pct,
        muscle_pct=muscle_pct,
        images_dir=images_dir,
    )
    password_hash = _hash_password(password)
    saved = crud.create_trainee_with_auth(trainee, username, password_hash)
    print()
    _ok(f"Account created! Welcome to your fitness journey, {saved.name}.")
    return saved


# ── Entry point: login or signup ──────────────────────────────────────────────

def authenticate() -> Optional[Trainee]:
    """Show the login/signup menu. Returns an authenticated Trainee or None (quit)."""
    print(f"\n{_CYAN}{'═' * 62}{_RST}")
    print(f"{_CYAN}  {_BOLD}FITNESS COACH — Alex{_RST}{_CYAN}                              {_RST}")
    print(f"{_CYAN}{'═' * 62}{_RST}\n")
    print(f"  {_DIM}[1]{_RST}  Login")
    print(f"  {_DIM}[2]{_RST}  Sign up")
    print(f"  {_DIM}[q]{_RST}  Quit\n")

    while True:
        choice = input(f"  {_BOLD}Choose › {_RST}").strip().lower()
        if choice in ("1", "login", "l"):
            return do_login()
        if choice in ("2", "signup", "sign up", "s", "register", "register"):
            return do_signup()
        if choice in ("q", "quit", "exit"):
            return None
        _err("Enter '1' to login, '2' to sign up, or 'q' to quit.")
