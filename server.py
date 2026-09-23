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


HOST = "127.0.0.1"
PORT = 8001
BACKUP_HOST = "0.0.0.0"
BACKUP_PORT = 9000
KNOCK_PORTS = (8002, 8003, 8004)
KNOCK_TIMEOUT = 5
KNOCK_UNLOCK_SECONDS = 60
DATABASE = Path(__file__).resolve().parent / "idor_lab.db"
BACKUP_DIRECTORY = Path(__file__).resolve().parent / "backups"
SESSIONS = {}


def password_hash(password):
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def generate_uuid(user_name):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{HOST}/users/{user_name}"))


def database():
    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row
    return connection


class BackupRequestHandler(socketserver.StreamRequestHandler):
    def write_line(self, message):
        self.wfile.write(f"{message}\n".encode("utf-8"))

    def handle(self):
        if not self.server.knock_state.is_unlocked(self.client_address[0]):
            self.write_line("ERROR complete the port knock first")
            return
        self.write_line("Common Ground backup service")
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
        connection.executemany(
            """
            INSERT OR IGNORE INTO users
                (username, password_hash, role, email, secret_note, uuid)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                ("alice", password_hash("alicepass"), "user", "alice@example.test",
                 "Alice's private project is called Lighthouse.", generate_uuid("alice")),
                ("bob", password_hash("bobpass"), "user", "bob@example.test",
                 "Bob's private project is called Paperclip.", generate_uuid("bob")),
                ("diana", password_hash("dianapass"), "user", "diana@example.test",
                 "Diana's private project is called Atlas.", generate_uuid("diana")),
                ("eve", password_hash("evepass"), "user", "eve@example.test",
                 "Eve's private project is called Orbit.", generate_uuid("eve")),
            ],
        )
        users = {
            row["username"]: row["id"]
            for row in connection.execute(
                "SELECT id, username FROM users WHERE username IN ('alice', 'bob', 'diana', 'eve')"
            )
        }
        connection.executemany(
            """
            INSERT INTO posts (id, user_id, title, topic, body, published_at)
            SELECT ?, ?, ?, ?, ?, ?
            WHERE NOT EXISTS (SELECT 1 FROM posts WHERE id = ?)
            """,
            [
                (1, users["alice"], "A Sunday Bowl Worth Repeating", "Food",
                 "I put together a bright bowl with roasted sweet potato, crunchy greens, and a lemony dressing. It was simple, filling, and exactly the kind of meal I want to make again next weekend.", "September 18, 2026", 1),
                (2, users["bob"], "The Small Gym Habit That Stuck", "Gym",
                 "My best gym upgrade was lowering the pressure to do everything perfectly. Three focused sessions a week, a good playlist, and tracking one small improvement has made training feel sustainable instead of intimidating.", "September 16, 2026", 2),
                (3, users["diana"], "A Cozy Game for a Rainy Evening", "Games",
                 "I spent last night with a gentle puzzle game that rewards curiosity instead of speed. The soft music and tiny discoveries made it a perfect rainy-evening reset, and I logged off feeling calmer than when I started.", "September 14, 2026", 3),
                (4, users["eve"], "The Snack I Keep Making", "Food",
                 "My current favorite snack is toasted bread with ricotta, sliced fruit, and a little honey. It takes only a few minutes, feels special without much effort, and has become my reliable afternoon break.", "September 12, 2026", 4),
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
                (users["alice"], "Recipe Notes", "alice_account/recipe_notes.txt", users["alice"], "Recipe Notes"),
                (users["diana"], "Training Plan", "diana_account/training_plan.txt", users["diana"], "Training Plan"),
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
                users["bob"],
                "Top_Secret",
                "bob_account/__pycache__/Top_Secret",
                users["bob"],
                "Top_Secret",
            ),
        )
        connection.execute("DELETE FROM user_files WHERE file_path IS NULL")
        connection.execute(
            "UPDATE users SET uuid = ? WHERE username = 'alice' AND (uuid IS NULL OR uuid = '')",
            (generate_uuid("alice"),),
        )
        connection.execute(
            "UPDATE users SET uuid = ? WHERE username = 'bob' AND (uuid IS NULL OR uuid = '')",
            (generate_uuid("bob"),),
        )


def page(title, body, user=None):
    account_link = '<a href="/login">Log in</a>'
    if user:
        account_link = (
            f'<span class="session-user">Hi, {html.escape(user["username"].title())}</span>'
            f'<a href="/users/user?userid={html.escape(user["uuid"])}">My profile</a>'
            '<a href="/logout">Log out</a>'
        )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)} · Common Ground</title>
  <style>
    :root {{ --ink: #24302b; --muted: #66736b; --paper: #fffdf8; --cream: #f5f0e7; --line: #dfe5db; --green: #285b4d; --orange: #db704b; }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; color: var(--ink); background: var(--cream); font-family: Georgia, "Times New Roman", serif; }}
    .shell {{ width: min(1080px, calc(100% - 40px)); margin: 0 auto; }}
    header {{ padding: 28px 0; display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid var(--line); }}
    .brand {{ color: var(--green); font-size: 1.35rem; font-weight: 700; letter-spacing: -.03em; text-decoration: none; }}
    nav a, .session-user {{ color: var(--muted); margin-left: 24px; text-decoration: none; font: 600 .86rem Arial, sans-serif; }}
    nav a:hover {{ color: var(--orange); }}
    main {{ padding: 68px 0 90px; }}
    .intro {{ max-width: 660px; margin-bottom: 44px; }}
    .kicker {{ color: var(--orange); font: 700 .72rem Arial, sans-serif; letter-spacing: .16em; text-transform: uppercase; }}
    h1 {{ color: var(--green); font-size: clamp(2.6rem, 7vw, 5.5rem); letter-spacing: -.065em; line-height: .95; margin: 14px 0 20px; }}
    h2 {{ color: var(--green); font-size: 2rem; letter-spacing: -.045em; margin: 10px 0; }}
    p {{ font-size: 1.1rem; line-height: 1.7; }}
    .subtle {{ color: var(--muted); }}
    .post-grid, .author-grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 22px; }}
    .post-card, .post-page, .profile {{ background: var(--paper); border: 1px solid var(--line); border-radius: 18px; padding: 28px; }}
    .author-card {{ background: var(--paper); border: 1px solid var(--line); border-radius: 18px; padding: 25px; }}
    .author-card h2 {{ margin-bottom: 5px; }}
    .post-card {{ min-height: 295px; display: flex; flex-direction: column; transition: transform .2s, box-shadow .2s; }}
    .post-card:hover {{ transform: translateY(-4px); box-shadow: 0 14px 30px rgba(40, 91, 77, .1); }}
    .post-card p {{ flex: 1; }}
    .file-list {{ list-style: none; margin: 18px 0 28px; padding: 0; text-align: left; }}
    .file-list li {{ background: #f0f4ed; border-radius: 8px; margin: 8px 0; padding: 11px 14px; }}
    .meta {{ color: var(--muted); font: .82rem Arial, sans-serif; }}
    .topic {{ color: var(--orange); font-weight: 700; }}
    .read-link, .back-link {{ color: var(--green); font: 700 .9rem Arial, sans-serif; text-decoration: none; }}
    .read-link:hover, .back-link:hover {{ color: var(--orange); }}
    .author-link {{ color: var(--green); font-weight: 700; text-decoration: underline; text-decoration-color: #b8d0c4; text-underline-offset: 3px; }}
    .post-page {{ max-width: 760px; margin: 0 auto; }}
    .post-page h1 {{ font-size: clamp(2.5rem, 6vw, 4.5rem); }}
    .post-body {{ margin: 38px 0; }}
    .profile {{ max-width: 680px; margin: 0 auto; text-align: center; }}
    .avatar {{ align-items: center; background: #dcebe1; border-radius: 50%; color: var(--green); display: flex; font: 700 1.8rem Arial, sans-serif; height: 76px; justify-content: center; margin: 0 auto 20px; width: 76px; }}
    footer {{ border-top: 1px solid var(--line); color: var(--muted); font: .8rem Arial, sans-serif; padding: 22px 0 34px; }}
    @media (max-width: 680px) {{ .shell {{ width: min(100% - 28px, 560px); }} header {{ padding: 20px 0; }} nav a {{ margin-left: 12px; }} main {{ padding-top: 44px; }} .post-grid {{ grid-template-columns: 1fr; }} .post-card {{ min-height: 260px; }} }}
  </style>
</head>
<body>
  <div class="shell">
    <header><a class="brand" href="/">Common Ground</a><nav><a href="/">Stories</a><a href="/authors">Authors</a>{account_link}</nav></header>
    <main>{body}</main>
    <footer>Small stories from everyday life · Common Ground</footer>
  </div>
</body>
</html>"""


def author_link(author):
    return (
        f'<a class="author-link" href="/profile/stories?userid={html.escape(author["uuid"])}">'
        f'{html.escape(author["username"].title())}</a>'
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
        initial = html.escape(profile["username"][0].upper())
        bob_flag = '<p class="subtle">FLAG{Bob_7hE_BUiLDerFL@9}</p>' if profile["username"] == "bob" else ""
        body = f"""<section class="profile"><div class="avatar">{initial}</div><div class="kicker">Author profile</div><h1>{html.escape(profile["username"].title())}</h1><p class="subtle">Sharing a few personal notes and things worth remembering.</p><h2>Stories by {html.escape(profile["username"].title())}</h2>{bob_flag}{links}{files_section}<p><a class="back-link" href="/">← Back to stories</a></p></section>"""
        title = f'{profile["username"].title()} · Author'
        self.send_page(page(title, body, user))

    def do_GET(self):
        path = urlparse(self.path).path.rstrip("/") or "/"
        user = self.current_user()
        if path == "/login":
            body = """<section class="profile"><div class="kicker">Welcome back</div><h1>Log in</h1>
              <p class="subtle">Sign in to your Common Ground account.</p>
              <form method="post" action="/login">
                <p><label for="username">Username</label><br><input id="username" name="username" required></p>
                <p><label for="password">Password</label><br><input id="password" name="password" type="password" required></p>
                <button type="submit">Log in</button>
              </form>
              <p class="subtle">Demo accounts: alice / alicepass and bob / bobpass.</p>
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
                    "SELECT file_name, file_path FROM user_files WHERE id = ?",
                    (file_id,),
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
                      <div class="avatar">{html.escape(author["username"][0].upper())}</div>
                      <h2>{html.escape(author["username"].title())}</h2>
                      <p class="subtle">{author["story_count"]} public {"stories" if author["story_count"] != 1 else "story"}</p>
                      <a class="read-link" href="/profile/stories?userid={html.escape(author["uuid"])}">View profile and stories →</a>
                    </article>"""
                    for author in authors
                )
                body = f"""<section class="intro"><div class="kicker">The community</div><h1>Meet the authors.</h1><p class="subtle">Browse every writer on Common Ground and discover their personal stories.</p></section><section class="author-grid">{cards}</section>"""
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
                      <p>{html.escape(post["body"])}</p>
                      <div class="meta">By {author_link(post)} &nbsp; <a class="read-link" href="/post/{post["id"]}">Read story →</a></div>
                    </article>"""
                    for post in posts
                )
                body = f"""<section class="intro"><div class="kicker">A personal blog</div><h1>Notes from the everyday.</h1><p class="subtle">A quiet corner for food, movement, games, and the little ideas that make a week feel like your own.</p></section><section class="post-grid">{cards}</section>"""
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
                  <div class="post-body"><p>{html.escape(post["body"])}</p></div>
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
    print(f"Common Ground running at http://{HOST}:{PORT}")
    print(f"Knock ports: {', '.join(str(port) for port in KNOCK_PORTS)}")
    print(f"Backup service running at {BACKUP_HOST}:{BACKUP_PORT}")
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
