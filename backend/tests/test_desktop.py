import hashlib
import io
import zipfile

import httpx
from fastapi.testclient import TestClient

from app import updater
from app.main import create_app


def test_is_newer_compares_numbers_not_text():
    assert updater.is_newer("v1.10.0", "1.9.9")
    assert not updater.is_newer("v1.2.0", "1.2.0")
    assert not updater.is_newer("v1.2.0", "dev")  # a dev build never self-updates
    assert not updater.is_newer("nightly", "1.0.0")


def test_ui_is_served_and_api_still_wins(tmp_path, monkeypatch):
    (tmp_path / "index.html").write_text("<h1>ui</h1>")
    monkeypatch.setenv("ZCS_STATIC_DIR", str(tmp_path))
    c = TestClient(create_app(testing=True))
    assert "<h1>ui</h1>" in c.get("/").text
    assert c.get("/openapi.json").json()["info"]["title"] == "ZCS LeadEngine"


def _zip_bytes() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("zcs-leadengine/zcs-leadengine.exe", "x")
    return buf.getvalue()


def test_stage_update_checks_the_checksum(tmp_path, monkeypatch):
    data = _zip_bytes()
    monkeypatch.setattr(httpx, "get", lambda *a, **k: httpx.Response(200, content=data, request=httpx.Request("GET", "https://x")))
    good = {"assets": [{"name": "a.zip", "url": "https://x", "digest": "sha256:" + hashlib.sha256(data).hexdigest()}]}
    assert updater.stage_update(good, tmp_path / "ok")
    assert (tmp_path / "ok" / "zcs-leadengine" / "zcs-leadengine.exe").exists()
    bad = {"assets": [{"name": "a.zip", "url": "https://x", "digest": "sha256:" + "0" * 64}]}
    assert not updater.stage_update(bad, tmp_path / "bad")
    assert not (tmp_path / "bad").exists()
    assert not updater.stage_update({"assets": []}, tmp_path / "none")
    nodigest = {"assets": [{"name": "a.zip", "url": "https://x"}]}
    assert not updater.stage_update(nodigest, tmp_path / "nodigest")
    assert not (tmp_path / "nodigest").exists()


def test_apply_script_never_touches_env(tmp_path):
    text = updater.apply_script(tmp_path, "zcs-leadengine.exe").read_text()
    assert "xcopy" in text and ".env" not in text and 'start "" "zcs-leadengine.exe"' in text
