"""Entry point of the desktop exe: load .env, update itself, migrate the database, serve the UI and API, open the browser."""
import os
import socket
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path

FROZEN = getattr(sys, "frozen", False)
BUNDLE = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))  # read-only files shipped inside the exe
INSTALL = Path(sys.executable).parent if FROZEN else Path(__file__).resolve().parent  # .env, exports, updates live here
os.chdir(INSTALL)

from dotenv import load_dotenv  # noqa: E402

load_dotenv(INSTALL / ".env")
os.environ.setdefault("ZCS_STATIC_DIR", str(BUNDLE / "static" if FROZEN else BUNDLE.parent / "frontend" / "out"))

PORT = int(os.environ.get("ZCS_PORT", "8000"))
MIGRATION_LOCK = 727001  # Postgres advisory lock: two teammates starting at once migrate one after the other


def say(msg: str) -> None:
    print(f"[zcs] {msg}", flush=True)


def self_update() -> None:
    from app import updater
    from app.version import VERSION

    token = updater.token_from_env()
    repo = os.environ.get("ZCS_UPDATE_REPO", updater.DEFAULT_REPO)
    try:
        rel = updater.latest_release(repo, token)
        if not rel or not updater.is_newer(rel["tag_name"], VERSION):
            return
        say(f"Updating {VERSION} -> {rel['tag_name']} ...")
        stage = INSTALL / "_update"
        if not updater.stage_update(rel, stage, token):
            say("Update skipped: no valid download in the release.")
            return
    except Exception as e:  # offline, rate limited, bad token: run the version we have
        say(f"Update check failed ({type(e).__name__}); starting the current version.")
        return
    bat = updater.apply_script(INSTALL, Path(sys.executable).name)
    subprocess.Popen(["cmd", "/c", str(bat)], cwd=INSTALL, creationflags=0x00000008 | 0x00000200)  # DETACHED | NEW_GROUP
    sys.exit(0)


def migrate() -> None:
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine, text

    from app.config import get_settings

    cfg = Config(str(BUNDLE / "alembic.ini"))
    cfg.set_main_option("script_location", str(BUNDLE / "migrations"))
    engine = create_engine(get_settings().database_url)
    with engine.connect() as lock:
        lock.execute(text("SELECT pg_advisory_lock(:k)"), {"k": MIGRATION_LOCK})
        try:
            command.upgrade(cfg, "head")
        finally:
            lock.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": MIGRATION_LOCK})
    engine.dispose()


def port_open(port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def main() -> None:
    from app.version import VERSION

    if port_open(PORT):  # already running: just show it
        webbrowser.open(f"http://127.0.0.1:{PORT}")
        return
    say(f"ZCS LeadEngine {VERSION}")
    if FROZEN and not os.environ.get("ZCS_NO_UPDATE"):
        self_update()
    if not (INSTALL / ".env").exists() and "DATABASE_URL" not in os.environ:
        say(f"Missing {INSTALL / '.env'}. Ask the team admin for the .env file and put it next to this exe.")
        input("Press Enter to close.")
        return
    say("Checking the database ...")
    migrate()

    import uvicorn

    from app.main import create_app

    threading.Timer(1.5, lambda: webbrowser.open(f"http://127.0.0.1:{PORT}")).start()
    say(f"Open http://127.0.0.1:{PORT} (close this window to stop)")
    uvicorn.run(create_app(), host="127.0.0.1", port=PORT, log_level="warning", loop="asyncio", http="h11", ws="none")


if __name__ == "__main__":
    main()
