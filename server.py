from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse
import hashlib
import html
from pathlib import Path
import secrets
import sqlite3
import socketserver
import threading
import time
import uuid


BIND_HOST = "0.0.0.0"
UUID_HOST = "127.0.0.1"
PORT = 8001
BACKUP_HOST = "0.0.0.0"
BACKUP_PORT = 9000
KNOCK_PORTS = (8002, 8003, 8004)
KNOCK_TIMEOUT = 5
KNOCK_UNLOCK_SECONDS = 180
DATABASE = Path(__file__).resolve().parent / "idor_lab.db"
BACKUP_DIRECTORY = Path(__file__).resolve().parent / "backups"
ASSET_DIRECTORY = Path(__file__).resolve().parent / "assets"
SESSIONS = {}
DISPLAY_NAMES = {"jinvicular": "Jinvicular", "eve": "Jin Jin Sakhur", "Capitan Jin": "Dr Jinsday"}
PROFILE_IMAGES = {
    "jinvicular": "/assets/jinvicular.png",
    "eve": "/assets/jin_jin_sakhur.png",
    "Capitan Jin": "/assets/dr_jinsday.png",
}


def password_hash(password):
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def generate_uuid(user_name):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{UUID_HOST}/users/{user_name}"))


def database():
    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row
    return connection


def display_name(username):
    return DISPLAY_NAMES.get(username, username.title())


def render_post_body(body):
    paragraphs = [paragraph for paragraph in body.split("\n\n") if paragraph]
    return "".join(f"<p>{html.escape(paragraph)}</p>" for paragraph in paragraphs)


class BackupRequestHandler(socketserver.StreamRequestHandler):
    def write_line(self, message):
        self.wfile.write(f"{message}\n".encode("utf-8"))

    def handle(self):
        if not self.server.knock_state.is_unlocked(self.client_address[0]):
            self.write_line("ERROR complete the port knock first")
            return
        self.write_line("Backup service")
        self.write_line("Commands: LIST, GET <file>, QUIT")
        while True:
            raw_command = self.rfile.readline()
            if not raw_command:
                return
            command = raw_command.decode("utf-8", errors="replace").strip()
            if command.upper() == "LIST":
                self.write_line("backup.txt")
            elif command.upper().startswith("GET "):
                requested_name = command[4:].strip()
                if requested_name != "backup.txt":
                    self.write_line("ERROR file not found")
                    continue
                backup_file = BACKUP_DIRECTORY / requested_name
                if not backup_file.is_file():
                    self.write_line("ERROR backup unavailable")
                    continue
                self.write_line("BEGIN")
                self.wfile.write(backup_file.read_bytes())
                self.write_line("END")
            elif command.upper() == "QUIT":
                self.write_line("BYE")
                return
            else:
                self.write_line("ERROR unknown command")


class BackupServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


class PortKnockState:
    def __init__(self, sequence, sequence_timeout, unlock_duration):
        self.sequence = sequence
        self.sequence_timeout = sequence_timeout
        self.unlock_duration = unlock_duration
        self.progress = {}
        self.unlocked_until = {}
        self.lock = threading.Lock()

    def record(self, address, port):
        now = time.monotonic()
        with self.lock:
            if self.unlocked_until.get(address, 0) > now:
                return

            current = self.progress.get(address)
            if not current or now - current[0] > self.sequence_timeout or port != self.sequence[current[1]]:
                current = (now, 0)
            if port == self.sequence[current[1]]:
                next_index = current[1] + 1
                if next_index == len(self.sequence):
                    self.unlocked_until[address] = now + self.unlock_duration
                    self.progress.pop(address, None)
                else:
                    self.progress[address] = (now, next_index)
            else:
                self.progress.pop(address, None)

    def is_unlocked(self, address):
        with self.lock:
            if self.unlocked_until.get(address, 0) > time.monotonic():
                return True
            self.unlocked_until.pop(address, None)
            return False


class PortKnockRequestHandler(socketserver.BaseRequestHandler):
    def handle(self):
        self.server.knock_state.record(self.client_address[0], self.server.knock_port)


class PortKnockServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def start_port_knockers():
    state = PortKnockState(KNOCK_PORTS, KNOCK_TIMEOUT, KNOCK_UNLOCK_SECONDS)
    servers = []
    for knock_port in KNOCK_PORTS:
        server = PortKnockServer(
            ("0.0.0.0", knock_port),
            PortKnockRequestHandler,
        )
        server.knock_state = state
        server.knock_port = knock_port
        threading.Thread(
            target=server.serve_forever,
            name=f"port-knock-{knock_port}",
            daemon=True,
        ).start()
        servers.append(server)
    return state, servers


def initialize_database():
    with database() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL,
                email TEXT NOT NULL,
                secret_note TEXT NOT NULL,
                uuid TEXT
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS posts (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                topic TEXT NOT NULL,
                body TEXT NOT NULL,
                published_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS user_files (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL,
                file_name TEXT NOT NULL,
                file_path TEXT,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
            """
        )
        file_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(user_files)")
        }
        if "file_path" not in file_columns:
            connection.execute("ALTER TABLE user_files ADD COLUMN file_path TEXT")
        connection.execute(
            "UPDATE users SET username = ? WHERE username = ?",
            ("CuriousDuck228", "alice"),
        )
        connection.execute(
            "UPDATE users SET username = ? WHERE username = ?",
            ("MegaJin", "diana"),
        )
        connection.execute(
            "UPDATE users SET username = ? WHERE username = ?",
            ("Capitan Jin", "MegaJin"),
        )
        connection.execute(
            "UPDATE users SET username = ? WHERE username = ?",
            ("jinvicular", "bob"),
        )
        connection.execute(
            """UPDATE user_files SET file_path = ?
            WHERE file_path = ?""",
            (
                "jinvicular_account/__pycache__/Top_Secret",
                "bob_account/__pycache__/Top_Secret",
            ),
        )
        connection.executemany(
            """
            INSERT OR IGNORE INTO users
                (username, password_hash, role, email, secret_note, uuid)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                ("CuriousDuck228", password_hash("v3rys1!r0ngp2ssw0r8"), "user", "alice@example.test",
                 "Alice's private project is called Lighthouse.", generate_uuid("alice")),
                ("jinvicular", password_hash("P8pVqr{hQP85"), "user", "jinvicular@example.test",
                 "Jinvicular's private project is called Paperclip.", generate_uuid("jinvicular")),
                ("Capitan Jin", password_hash("dianapass"), "user", "diana@example.test",
                 "Diana's private project is called Atlas.", generate_uuid("diana")),
                ("eve", password_hash("evepass"), "user", "eve@example.test",
                 "Eve's private project is called Orbit.", generate_uuid("eve")),
            ],
        )
        users = {
            row["username"]: row["id"]
            for row in connection.execute(
                "SELECT id, username FROM users WHERE username IN ('CuriousDuck228', 'jinvicular', 'Capitan Jin', 'eve')"
            )
        }
        connection.executemany(
            """
            INSERT INTO posts (id, user_id, title, topic, body, published_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                user_id = excluded.user_id,
                title = excluded.title,
                topic = excluded.topic,
                body = excluded.body,
                published_at = excluded.published_at
            """,
            [
                (1, users["CuriousDuck228"], "Building a Safer Password Routine", "Account Security",
                 "A strong password is only the beginning of account security. I have started using a unique passphrase for every service, storing them in a password manager, and enabling multi-factor authentication wherever it is available.", "September 18, 2026"),
                (2, users["jinvicular"], "The Smallest Patch That Matters", "Vulnerability Management",
                 "A neglected software update can become an easy entry point for an attacker. I now review security advisories, prioritize internet-facing systems, and verify that critical patches were actually applied instead of assuming the update completed.", "September 16, 2026"),
                (3, users["Capitan Jin"], "A Calm Way to Read Suspicious Messages", "Phishing Awareness",
                 "Phishing attempts often rely on urgency rather than sophisticated code. Before clicking a link or opening an attachment, I check the sender, inspect the destination carefully, and confirm unusual requests through a trusted channel.", "September 14, 2026"),
                (4, users["eve"], "A Quiet Knock at the Door", "Network Security",
                 ("Some doors in the CyberMaxxing Forum do not open with a key; they listen for a quiet knock. If you are looking for the backup service, start with port 8002, then knock on 8003, and finish with 8004 in that exact order.\n\n"
                  "Keep the sequence moving and do not pause for more than a few seconds between knocks. Once all three ports answer in order, the way forward should open briefly, so be ready to connect and see what is waiting on the other side."),
                  "September 12, 2026"),
            ],
        )
        connection.executemany(
            """
            INSERT INTO user_files (user_id, file_name, file_path)
            SELECT ?, ?, ?
            WHERE NOT EXISTS (
                SELECT 1 FROM user_files WHERE user_id = ? AND file_name = ?
            )
            """,
            [
                (users["CuriousDuck228"], "Recipe Notes", "alice_account/recipe_notes.txt", users["CuriousDuck228"], "Recipe Notes"),
                (users["Capitan Jin"], "Training Plan", "diana_account/training_plan.txt", users["Capitan Jin"], "Training Plan"),
                (users["eve"], "Game Backlog", "eve_account/game_backlog.txt", users["eve"], "Game Backlog"),
            ],
        )
        connection.execute(
            """
            INSERT INTO user_files (user_id, file_name, file_path)
            SELECT ?, ?, ?
            WHERE NOT EXISTS (
                SELECT 1 FROM user_files WHERE user_id = ? AND file_name = ?
            )
            """,
            (
                users["jinvicular"],
                "Top_Secret",
                "jinvicular_account/__pycache__/Top_Secret",
                users["jinvicular"],
                "Top_Secret",
            ),
        )
        connection.execute("DELETE FROM user_files WHERE file_path IS NULL")
        connection.execute(
            "UPDATE users SET uuid = ? WHERE username = 'CuriousDuck228' AND (uuid IS NULL OR uuid = '')",
            (generate_uuid("alice"),),
        )
        connection.execute(
            "UPDATE users SET password_hash = ? WHERE username = ?",
            (password_hash("v3rys1!r0ngp2ssw0r8"), "CuriousDuck228"),
        )
        connection.execute(
            "UPDATE users SET password_hash = ? WHERE username = ?",
            (password_hash("no1!0rpu8li6k"), "admin"),
        )
        connection.execute(
            "UPDATE users SET password_hash = ? WHERE username = ?",
            (password_hash("P8pVqr{hQP85"), "jinvicular"),
        )
        connection.execute(
            "UPDATE users SET uuid = ? WHERE username = 'jinvicular' AND (uuid IS NULL OR uuid = '')",
            (generate_uuid("jinvicular"),),
        )


def page(title, body, user=None):
    account_link = '<a href="/login">Log in</a>'
    if user:
        account_link = (
            f'<span class="session-user">Hi, {html.escape(display_name(user["username"]))}</span>'
            f'<a href="/users/user?userid={html.escape(user["uuid"])}">My profile</a>'
            '<a href="/logout">Log out</a>'
        )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)} · CyberMaxxing Forum</title>
  <style>
    :root {{ --ink: #e8edf2; --muted: #9caaba; --paper: #111b27; --cream: #08111c; --line: #2b3b4d; --navy: #0d1926; --red: #d44f4f; --gold: #c6a76b; }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; color: var(--ink); background: radial-gradient(circle at 90% 0%, #172a3e 0, transparent 32rem), var(--cream); font-family: "Segoe UI", Arial, sans-serif; }}
    .shell {{ width: min(1080px, calc(100% - 40px)); margin: 0 auto; }}
    header {{ padding: 22px 0; display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid var(--line); }}
    .brand {{ color: var(--ink); display: flex; align-items: center; gap: 12px; font-size: 1.05rem; font-weight: 800; letter-spacing: .12em; text-decoration: none; text-transform: uppercase; }}
    .brand::before {{ content: "M"; display: grid; place-items: center; width: 34px; height: 34px; border: 2px solid var(--gold); border-radius: 50%; color: var(--gold); font-size: .9rem; }}
    nav a, .session-user {{ color: var(--muted); margin-left: 24px; text-decoration: none; font: 700 .74rem Arial, sans-serif; letter-spacing: .08em; text-transform: uppercase; }}
    nav a:hover {{ color: var(--red); }}
    main {{ padding: 68px 0 90px; }}
    .intro {{ max-width: 720px; margin-bottom: 44px; }}
    .kicker {{ color: var(--red); font: 800 .7rem Arial, sans-serif; letter-spacing: .2em; text-transform: uppercase; }}
    h1 {{ color: var(--ink); font-size: clamp(2.6rem, 7vw, 5.5rem); letter-spacing: -.055em; line-height: .95; margin: 14px 0 20px; }}
    h2 {{ color: var(--ink); font-size: 1.6rem; letter-spacing: -.025em; margin: 10px 0; }}
    p {{ font-size: 1.05rem; line-height: 1.7; }}
    .subtle {{ color: var(--muted); }}
    .post-grid, .author-grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 22px; }}
    .post-card, .post-page, .profile {{ background: linear-gradient(145deg, rgba(22, 35, 50, .98), rgba(13, 25, 38, .98)); border: 1px solid var(--line); border-radius: 3px; padding: 28px; box-shadow: 0 18px 40px rgba(0, 0, 0, .18); }}
    .author-card {{ background: var(--paper); border: 1px solid var(--line); border-radius: 3px; padding: 25px; }}
    .author-card h2 {{ margin-bottom: 5px; }}
    .post-card {{ min-height: 295px; display: flex; flex-direction: column; transition: transform .2s, border-color .2s; }}
    .post-card:hover {{ transform: translateY(-4px); border-color: var(--gold); }}
    .post-card p {{ flex: 1; }}
    .file-list {{ list-style: none; margin: 18px 0 28px; padding: 0; text-align: left; }}
    .file-list li {{ background: #0b1520; border-left: 3px solid var(--red); margin: 8px 0; padding: 11px 14px; }}
    .meta {{ color: var(--muted); font: .82rem Arial, sans-serif; }}
    .topic {{ color: var(--gold); font-weight: 700; }}
    .read-link, .back-link {{ color: var(--gold); font: 700 .82rem Arial, sans-serif; text-decoration: none; text-transform: uppercase; letter-spacing: .06em; }}
    .read-link:hover, .back-link:hover {{ color: var(--red); }}
    .author-link {{ color: var(--ink); font-weight: 700; text-decoration: underline; text-decoration-color: var(--red); text-underline-offset: 3px; }}
    .post-page {{ max-width: 760px; margin: 0 auto; }}
    .post-page h1 {{ font-size: clamp(2.5rem, 6vw, 4.5rem); }}
    .post-body {{ margin: 38px 0; }}
    .profile {{ max-width: 680px; margin: 0 auto; text-align: center; }}
    .avatar {{ align-items: center; background: #1e3247; border: 2px solid var(--gold); border-radius: 50%; color: var(--gold); display: flex; font: 700 1.8rem Arial, sans-serif; height: 76px; justify-content: center; margin: 0 auto 20px; object-fit: cover; width: 76px; }}
    .avatar-image {{ display: block; }}
    .profile .avatar-image {{ height: 240px; width: 240px; margin-bottom: 26px; }}
    input {{ background: #0b1520; border: 1px solid var(--line); color: var(--ink); padding: 10px; width: min(100%, 300px); }}
    button {{ background: var(--red); border: 0; color: white; cursor: pointer; font-weight: 800; padding: 11px 20px; text-transform: uppercase; letter-spacing: .08em; }}
    footer {{ border-top: 1px solid var(--line); color: var(--muted); font: .72rem Arial, sans-serif; letter-spacing: .08em; padding: 22px 0 34px; text-transform: uppercase; }}
    .policy {{ margin-top: 14px; text-transform: none; letter-spacing: normal; }}
    .policy summary {{ color: var(--gold); cursor: pointer; display: inline-block; font-weight: 700; letter-spacing: .06em; list-style: none; text-transform: uppercase; }}
    .policy summary::-webkit-details-marker {{ display: none; }}
    .policy summary::before {{ content: "+ "; }}
    .policy[open] summary::before {{ content: "− "; }}
    .policy p {{ font-size: .78rem; line-height: 1.5; margin: 10px auto 0; max-width: 760px; }}
    @media (max-width: 680px) {{ .shell {{ width: min(100% - 28px, 560px); }} header {{ padding: 20px 0; }} nav a {{ margin-left: 12px; }} main {{ padding-top: 44px; }} .post-grid {{ grid-template-columns: 1fr; }} .post-card {{ min-height: 260px; }} }}
  </style>
</head>
<body>
  <div class="shell">
    <header><a class="brand" href="/">CyberMaxxing Forum</a><nav><a href="/">Briefings</a><a href="/authors">Personnel</a>{account_link}</nav></header>
    <main>{body}</main>
    <footer>Restricted community forum · CyberMaxxing Forum · Internal use
      <details class="policy">
        <summary>Policy</summary>
        <p>This is not an official CITS3006 or government website. It is provided for lab use only, and any similarities to real people, organisations, or websites are unintentional.</p>
        <p>Dr Jin Hong has authorised the use of his pictures and identity for this challenge.</p>
      </details>
    </footer>
  </div>
</body>
</html>"""


def author_link(author):
    return (
        f'<a class="author-link" href="/profile/stories?userid={html.escape(author["uuid"])}">'
        f'{html.escape(display_name(author["username"]))}</a>'
    )


class Handler(BaseHTTPRequestHandler):
    def current_user(self):
        session = cookies.SimpleCookie(self.headers.get("Cookie", ""))
        token = session.get("session")
        if not token or token.value not in SESSIONS:
            return None
        with database() as connection:
            return connection.execute(
                "SELECT id, username, uuid FROM users WHERE id = ?",
                (SESSIONS[token.value],),
            ).fetchone()

    def send_page(self, content, status=200, headers=None):
        encoded = content.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(encoded)

    def render_profile(self, connection, profile, user, private=False):
        posts = connection.execute(
            "SELECT id, title, topic, published_at FROM posts WHERE user_id = ? ORDER BY id DESC",
            (profile["id"],),
        ).fetchall()
        links = "".join(
            f'<p><span class="topic">{html.escape(post["topic"])}</span> · <a class="back-link" href="/post/{post["id"]}">{html.escape(post["title"])}</a></p>'
            for post in posts
        )
        if private:
            files = connection.execute(
                "SELECT id, file_name, file_path FROM user_files WHERE user_id = ? ORDER BY file_name",
                (profile["id"],),
            ).fetchall()
            file_links = "".join(
                f'<li>{html.escape(file["file_name"])}'
                + (f' · <a class="read-link" href="/files/{file["id"]}">Download</a>' if file["file_path"] else "")
                + "</li>"
                for file in files
            )
            files_section = f'<h2>Personal files</h2><ul class="file-list">{file_links}</ul>'
        else:
            files_section = '<p class="subtle">Personal files are private to this user.</p>'
        flag_section = (
            '<h2>Recovered flag</h2><p class="flag">FLAG{Bob_7hE_BUiLDerFL@9}</p>'
            if private and profile["username"] == "jinvicular"
            else ""
        )
        name = display_name(profile["username"])
        image = PROFILE_IMAGES.get(profile["username"])
        avatar = (
            f'<img class="avatar avatar-image profile-avatar" src="{image}" alt="{html.escape(name)}">'
            if image
            else f'<div class="avatar">{html.escape(name[0].upper())}</div>'
        )
        body = f"""<section class="profile"><div class="kicker">Personnel dossier · {html.escape("private" if private else "public")}</div>{avatar}<h1>{html.escape(name)}</h1><p class="subtle">Field notes, personal briefings, and material cleared for this forum.</p><h2>Stories by {html.escape(name)}</h2>{links}{files_section}{flag_section}<p><a class="back-link" href="/">← Back to briefings</a></p></section>"""
        title = f'{name} · Personnel'
        self.send_page(page(title, body, user))

    def do_GET(self):
        path = urlparse(self.path).path.rstrip("/") or "/"
        user = self.current_user()
        if path.startswith("/assets/"):
            image_name = path.removeprefix("/assets/")
            image_path = ASSET_DIRECTORY / image_name
            if image_path.parent != ASSET_DIRECTORY or image_path.suffix.lower() != ".png":
                self.send_page(page("Not found", '<div class="post-page"><h1>Asset not found</h1></div>'), 404)
                return
            if not image_path.is_file():
                self.send_page(page("Not found", '<div class="post-page"><h1>Asset not found</h1></div>'), 404)
                return
            image = image_path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(image)))
            self.end_headers()
            self.wfile.write(image)
            return
        if path == "/login":
            body = """<section class="profile"><div class="kicker">Welcome back</div><h1>Log in</h1>
              <p class="subtle">Authenticate to access the CyberMaxxing Forum.</p>
              <form method="post" action="/login">
                <p><label for="username">Username</label><br><input id="username" name="username" required></p>
                <p><label for="password">Password</label><br><input id="password" name="password" type="password" required></p>
                <button type="submit">Log in</button>
              </form>
              <p class="subtle">Demo accounts: CuriousDuck228 / v3rys1!r0ngp2ssw0r8 and jinvicular / P8pVqr{hQP85.</p>
            </section>"""
            self.send_page(page("Log in", body, user))
            return
        if path == "/logout":
            session = cookies.SimpleCookie(self.headers.get("Cookie", ""))
            token = session.get("session")
            if token:
                SESSIONS.pop(token.value, None)
            self.send_page(page("Logged out", '<div class="profile"><h1>You are logged out</h1><a class="back-link" href="/">← Back to stories</a></div>'), headers={"Set-Cookie": "session=; Max-Age=0; HttpOnly; Path=/"})
            return
        if path.startswith("/files/"):
            if not user:
                self.send_page(page("Log in required", '<div class="profile"><h1>Log in required</h1><p class="subtle">Log in to access your personal files.</p><a class="back-link" href="/login">Log in →</a></div>'), 401)
                return
            file_id = path.rsplit("/", 1)[-1]
            with database() as connection:
                file_record = connection.execute(
                    """SELECT file_name, file_path FROM user_files
                    WHERE id = ? AND user_id = ?""",
                    (file_id, user["id"]),
                ).fetchone()
            if not file_record or not file_record["file_path"]:
                self.send_page(page("Not found", '<div class="profile"><h1>File not found</h1><a class="back-link" href="/">← Back to stories</a></div>'), 404)
                return
            file_path = Path(__file__).resolve().parent / file_record["file_path"]
            if not file_path.is_file():
                self.send_page(page("Not found", '<div class="profile"><h1>File not found</h1><a class="back-link" href="/">← Back to stories</a></div>'), 404)
                return
            content = file_path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Disposition", f'attachment; filename="{file_record["file_name"]}"')
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
            return
        with database() as connection:
            if path == "/authors":
                authors = connection.execute(
                    """
                    SELECT users.username, users.uuid, COUNT(posts.id) AS story_count
                    FROM users JOIN posts ON posts.user_id = users.id
                    GROUP BY users.id, users.username, users.uuid
                    ORDER BY users.username
                    """
                ).fetchall()
                cards = "".join(
                    f"""<article class="author-card">
                      {f'<img class="avatar avatar-image" src="{PROFILE_IMAGES[author["username"]]}" alt="{html.escape(display_name(author["username"]))}">' if author["username"] in PROFILE_IMAGES else f'<div class="avatar">{html.escape(display_name(author["username"])[0].upper())}</div>'}
                      <h2>{html.escape(display_name(author["username"]))}</h2>
                      <p class="subtle">{author["story_count"]} public {"stories" if author["story_count"] != 1 else "story"}</p>
                      <a class="read-link" href="/profile/stories?userid={html.escape(author["uuid"])}">View profile and stories →</a>
                    </article>"""
                    for author in authors
                )
                body = f"""<section class="intro"><div class="kicker">Personnel registry · clearance level 01</div><h1>Know the network.</h1><p class="subtle">Browse cleared contributors, active briefings, and the people behind the CyberMaxxing Forum.</p></section><section class="author-grid">{cards}</section>"""
                self.send_page(page("Authors", body, user))
                return
            if path == "/":
                posts = connection.execute(
                    """
                    SELECT posts.*, users.username, users.uuid
                    FROM posts JOIN users ON users.id = posts.user_id
                    ORDER BY posts.id DESC
                    """
                ).fetchall()
                cards = "".join(
                    f"""<article class="post-card">
                      <div class="meta"><span class="topic">{html.escape(post["topic"])}</span> · {html.escape(post["published_at"])}</div>
                      <h2>{html.escape(post["title"])}</h2>
                      {render_post_body(post["body"])}
                      <div class="meta">By {author_link(post)} &nbsp; <a class="read-link" href="/post/{post["id"]}">Read story →</a></div>
                    </article>"""
                    for post in posts
                )
                body = f"""<section class="intro"><div class="kicker">CyberMaxxing Forum · internal briefings</div><h1>Signals from the field.</h1><p class="subtle">A restricted channel for observations, routines, and the small details worth passing along.</p></section><section class="post-grid">{cards}</section>"""
                self.send_page(page("Stories", body, user))
                return

            if path.startswith("/post/"):
                post_id = path.removeprefix("/post/")
                post = connection.execute(
                    """SELECT posts.*, users.username, users.uuid FROM posts
                    JOIN users ON users.id = posts.user_id WHERE posts.id = ?""",
                    (post_id,),
                ).fetchone()
                if not post:
                    self.send_page(page("Not found", '<div class="post-page"><h1>Story not found</h1><a class="back-link" href="/">← Back to stories</a></div>'), 404)
                    return
                body = f"""<article class="post-page">
                  <div class="kicker">{html.escape(post["topic"])} · {html.escape(post["published_at"])}</div>
                  <h1>{html.escape(post["title"])}</h1>
                  <div class="meta">Written by {author_link(post)}</div>
                  <div class="post-body">{render_post_body(post["body"])}</div>
                  <a class="back-link" href="/">← Back to stories</a>
                </article>"""
                self.send_page(page(post["title"], body, user))
                return

            if path == "/users/user":
                if not user:
                    self.send_page(page("Log in required", '<div class="profile"><h1>Log in required</h1><p class="subtle">Log in to access your personal profile.</p><a class="back-link" href="/login">Log in →</a></div>'), 401)
                    return
                requested_uuid = parse_qs(urlparse(self.path).query).get("userid", [""])[0]
                profile = connection.execute(
                    "SELECT id, username, email, uuid FROM users WHERE uuid = ?",
                    (requested_uuid,),
                ).fetchone()
                if not profile:
                    self.send_page(page("Not found", '<div class="profile"><h1>Profile not found</h1><a class="back-link" href="/">← Back to stories</a></div>'), 404)
                    return
                if profile["id"] != user["id"]:
                    self.send_page(page("Forbidden", '<div class="profile"><h1>Private profile</h1><p class="subtle">You can only access your own private profile.</p><a class="back-link" href="/">← Back to briefings</a></div>'), 403)
                    return
                self.render_profile(connection, profile, user, private=True)
                return

            if path == "/profile/stories":
                requested_uuid = parse_qs(urlparse(self.path).query).get("userid", [""])[0]
                profile = connection.execute(
                    "SELECT id, username, email, uuid FROM users WHERE uuid = ?",
                    (requested_uuid,),
                ).fetchone()
                if not profile:
                    self.send_page(page("Not found", '<div class="profile"><h1>Author not found</h1><a class="back-link" href="/">← Back to stories</a></div>'), 404)
                    return
                self.render_profile(connection, profile, user)
                return

        self.send_page(page("Not found", '<div class="post-page"><h1>Page not found</h1><a class="back-link" href="/">← Back to stories</a></div>'), 404)

    def do_POST(self):
        if urlparse(self.path).path != "/login":
            self.send_page(page("Not found", '<div class="post-page"><h1>Page not found</h1></div>'), 404)
            return
        length = int(self.headers.get("Content-Length", "0"))
        values = parse_qs(self.rfile.read(length).decode("utf-8"))
        username = values.get("username", [""])[0].strip()
        password = values.get("password", [""])[0]
        with database() as connection:
            user = connection.execute(
                "SELECT id FROM users WHERE username = ? AND password_hash = ?",
                (username, password_hash(password)),
            ).fetchone()
        if not user:
            body = '<section class="profile"><h1>Log in failed</h1><p class="subtle">Those credentials were not recognised.</p><a class="back-link" href="/login">Try again</a></section>'
            self.send_page(page("Log in failed", body), 401)
            return
        token = secrets.token_urlsafe(32)
        SESSIONS[token] = user["id"]
        self.send_page(page("Logged in", '<div class="profile"><h1>Welcome back</h1><a class="back-link" href="/">Go to stories →</a></div>'), headers={"Set-Cookie": f"session={token}; HttpOnly; Path=/"})


if __name__ == "__main__":
    KNOCK_STATE, knock_servers = start_port_knockers()
    initialize_database()
    backup_server = BackupServer((BACKUP_HOST, BACKUP_PORT), BackupRequestHandler)
    backup_server.knock_state = KNOCK_STATE
    backup_server_thread = threading.Thread(
        target=backup_server.serve_forever,
        name="backup-service",
        daemon=True,
    )
    backup_server_thread.start()
    print(f"Website is running at http://{BIND_HOST}:{PORT}")
    print(f"Knock ports: {', '.join(str(port) for port in KNOCK_PORTS)}")
    print(f"Backup service running at {BACKUP_HOST}:{BACKUP_PORT}")
    ThreadingHTTPServer((BIND_HOST, PORT), Handler).serve_forever()
