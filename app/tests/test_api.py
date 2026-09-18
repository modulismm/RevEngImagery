"""Backend tests. Run inside the image: see app/README.md."""
import io
import json
import os
import tempfile

import pytest

os.environ.setdefault("IMAGERY_SECURE_COOKIE", "0")


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("IMAGERY_DB", str(tmp_path / "t.db"))
    monkeypatch.setenv("IMAGERY_UPLOADS", str(tmp_path / "up"))
    monkeypatch.setenv("IMAGERY_SECRET_FILE", str(tmp_path / "key"))
    monkeypatch.setenv("IMAGERY_SECURE_COOKIE", "0")
    monkeypatch.setenv("IMAGERY_ADMIN", "bear")
    monkeypatch.setenv("IMAGERY_ADMIN_PASSPHRASE", "the blue kettle sings")
    import importlib
    from server import db, app as appmod
    importlib.reload(db)
    importlib.reload(appmod)
    application = appmod.create_app()
    application.config.update(TESTING=True)
    with application.test_client() as c:
        yield c


def login(c, name="bear", phrase="the blue kettle sings"):
    r = c.post("/api/login", json={"name": name, "passphrase": phrase})
    assert r.status_code == 200, r.get_json()
    return r.get_json()["csrf"]


# ------------------------------------------------------------------ auth --
def test_login_and_me(client):
    csrf = login(client)
    assert csrf
    me = client.get("/api/me").get_json()
    assert me["user"]["name"] == "bear"
    assert me["user"]["role"] == "admin"


def test_wrong_passphrase_is_rejected(client):
    r = client.post("/api/login", json={"name": "bear", "passphrase": "nope nope nope"})
    assert r.status_code == 401


def test_unknown_and_known_user_give_the_same_message(client):
    a = client.post("/api/login", json={"name": "bear", "passphrase": "wrong wrong wrong"})
    b = client.post("/api/login", json={"name": "ghost", "passphrase": "wrong wrong wrong"})
    assert a.get_json()["error"] == b.get_json()["error"]


def test_anonymous_cannot_list(client):
    assert client.get("/api/canvases").status_code == 401


def test_mutation_without_csrf_is_refused(client):
    login(client)
    r = client.post("/api/canvases", json={"name": "x"})   # no X-CSRF-Token
    assert r.status_code == 403


def test_logout_clears_session(client):
    csrf = login(client)
    client.post("/api/logout", headers={"X-CSRF-Token": csrf})
    assert client.get("/api/canvases").status_code == 401


# --------------------------------------------------------------- canvases --
def test_canvas_roundtrip(client):
    csrf = login(client)
    h = {"X-CSRF-Token": csrf}
    r = client.post("/api/canvases", json={"name": "Pioupiou"}, headers=h)
    assert r.status_code == 201
    cid = r.get_json()["canvas"]["id"]

    zones = [{"id": "1", "sound_name": "Son 1", "x": 40.19, "y": 24.94,
              "radius": 225.94, "volume": 0.7, "startTime": 0, "endTime": 2.1,
              "type": "custom", "url": "/media/audio/a.webm",
              "effects": {"reverbLevel": 31, "pitch": 0, "highFreq": 2.5,
                          "lowFreq": 2.5, "midFreq": 0, "isReversed": False}}]
    r = client.put(f"/api/canvases/{cid}", json={"zones": zones}, headers=h)
    got = r.get_json()["canvas"]["zones"][0]
    assert got["x"] == pytest.approx(40.19)
    assert got["radius"] == pytest.approx(225.94)
    assert got["effects"]["reverbLevel"] == pytest.approx(31)
    assert got["effects"]["isReversed"] is False


def test_zone_values_are_clamped(client):
    csrf = login(client)
    h = {"X-CSRF-Token": csrf}
    cid = client.post("/api/canvases", json={"name": "c"}, headers=h).get_json()["canvas"]["id"]
    bad = [{"x": 9999, "y": -50, "radius": 1, "volume": 40,
            "effects": {"pitch": 99, "reverbLevel": -10}}]
    z = client.put(f"/api/canvases/{cid}", json={"zones": bad},
                   headers=h).get_json()["canvas"]["zones"][0]
    assert z["x"] == 100 and z["y"] == 0
    assert z["volume"] == 1 and z["radius"] == 20
    assert z["effects"]["pitch"] == 12 and z["effects"]["reverbLevel"] == 0


def test_zone_url_must_be_local(client):
    csrf = login(client)
    h = {"X-CSRF-Token": csrf}
    cid = client.post("/api/canvases", json={"name": "c"}, headers=h).get_json()["canvas"]["id"]
    z = client.put(f"/api/canvases/{cid}",
                   json={"zones": [{"url": "https://evil.example/x.webm"}]},
                   headers=h).get_json()["canvas"]["zones"][0]
    assert z["url"] is None


# ------------------------------------------------------------------ roles --
def test_admin_sees_all_and_user_sees_own(client):
    csrf = login(client)
    h = {"X-CSRF-Token": csrf}
    client.post("/api/canvases", json={"name": "admin one"}, headers=h)
    setup_url = client.post("/api/users", json={"name": "mamie"},
                            headers=h).get_json()["setup_url"]
    client.post("/api/logout", headers=h)

    token = setup_url.rsplit("/", 1)[-1]
    r = client.post(f"/api/setup/{token}", json={"passphrase": "les oiseaux chantent"})
    assert r.status_code == 200
    csrf2 = r.get_json()["csrf"]
    client.post("/api/canvases", json={"name": "mamie one"},
                headers={"X-CSRF-Token": csrf2})
    mine = client.get("/api/canvases").get_json()
    assert [c["name"] for c in mine["canvases"]] == ["mamie one"]
    # A non-admin asking for everything still only gets their own.
    assert client.get("/api/canvases?all=1").get_json()["scope"] == "mine"
    assert client.get("/api/users").status_code == 403

    client.post("/api/logout", headers={"X-CSRF-Token": csrf2})
    login(client)
    all_ = client.get("/api/canvases?all=1").get_json()
    assert all_["scope"] == "all"
    assert {c["name"] for c in all_["canvases"]} == {"admin one", "mamie one"}


def test_user_cannot_edit_another_persons_canvas(client):
    csrf = login(client)
    h = {"X-CSRF-Token": csrf}
    cid = client.post("/api/canvases", json={"name": "admins"}, headers=h).get_json()["canvas"]["id"]
    token = client.post("/api/users", json={"name": "mamie"},
                        headers=h).get_json()["setup_url"].rsplit("/", 1)[-1]
    client.post("/api/logout", headers=h)
    csrf2 = client.post(f"/api/setup/{token}",
                        json={"passphrase": "les oiseaux chantent"}).get_json()["csrf"]
    r = client.put(f"/api/canvases/{cid}", json={"name": "hijacked"},
                   headers={"X-CSRF-Token": csrf2})
    assert r.status_code == 403


# --------------------------------------------------------------- uploads --
PNG = (b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)
WEBM = (b"\x1a\x45\xdf\xa3" + b"\x00" * 64)


def test_upload_accepts_real_types(client):
    csrf = login(client)
    h = {"X-CSRF-Token": csrf}
    r = client.post("/api/upload/image", headers=h,
                    data={"file": (io.BytesIO(PNG), "x.png")},
                    content_type="multipart/form-data")
    assert r.status_code == 201 and r.get_json()["path"].startswith("image/")
    r = client.post("/api/upload/audio", headers=h,
                    data={"file": (io.BytesIO(WEBM), "x.webm")},
                    content_type="multipart/form-data")
    assert r.status_code == 201 and r.get_json()["mime"] == "audio/webm"


def test_upload_rejects_disguised_file(client):
    """A script renamed .png must not be stored as an image."""
    csrf = login(client)
    r = client.post("/api/upload/image", headers={"X-CSRF-Token": csrf},
                    data={"file": (io.BytesIO(b"<?php system($_GET[0]); ?>"), "shell.png")},
                    content_type="multipart/form-data")
    assert r.status_code == 400


def test_media_path_traversal_is_refused(client):
    assert client.get("/media/../../etc/passwd").status_code in (404, 308, 400)


# ------------------------------------------------------------ passphrases --
@pytest.mark.parametrize("bad", ["short", "password", "aaaaaaaaaaaa"])
def test_weak_passphrases_rejected_at_setup(client, bad):
    csrf = login(client)
    token = client.post("/api/users", json={"name": "mamie"},
                        headers={"X-CSRF-Token": csrf}).get_json()["setup_url"].rsplit("/", 1)[-1]
    r = client.post(f"/api/setup/{token}", json={"passphrase": bad})
    assert r.status_code == 400
    assert "error" in r.get_json()


def test_setup_token_is_single_use(client):
    csrf = login(client)
    token = client.post("/api/users", json={"name": "mamie"},
                        headers={"X-CSRF-Token": csrf}).get_json()["setup_url"].rsplit("/", 1)[-1]
    assert client.post(f"/api/setup/{token}", json={"passphrase": "les oiseaux chantent"}).status_code == 200
    assert client.post(f"/api/setup/{token}", json={"passphrase": "les oiseaux chantent"}).status_code == 404


def test_generated_zone_keeps_its_preset_and_drops_url(client):
    """A built-in tone is synthesised from its name, so it carries no media."""
    csrf = login(client)
    h = {"X-CSRF-Token": csrf}
    cid = client.post("/api/canvases", json={"name": "c"}, headers=h).get_json()["canvas"]["id"]
    z = client.put(f"/api/canvases/{cid}", json={"zones": [
        {"type": "generated", "sound_name": "Bell Ding",
         "url": "/media/audio/leftover.webm", "radius": 200}]},
        headers=h).get_json()["canvas"]["zones"][0]
    assert z["type"] == "generated"
    assert z["sound_name"] == "Bell Ding"
    assert z["url"] is None


def test_unknown_zone_type_falls_back_to_custom(client):
    csrf = login(client)
    h = {"X-CSRF-Token": csrf}
    cid = client.post("/api/canvases", json={"name": "c"}, headers=h).get_json()["canvas"]["id"]
    z = client.put(f"/api/canvases/{cid}",
                   json={"zones": [{"type": "something-else", "radius": 200}]},
                   headers=h).get_json()["canvas"]["zones"][0]
    assert z["type"] == "custom"


@pytest.mark.parametrize("url,kept", [
    ("/media/audio/a.webm", True),
    ("/static/sounds/rain.mp3", True),
    ("https://evil.example/x.webm", False),
    ("//evil.example/x.webm", False),
    ("/media/../../etc/passwd", False),
    ("/etc/passwd", False),
    ("", False),
])
def test_zone_url_allowlist(client, url, kept):
    csrf = login(client)
    h = {"X-CSRF-Token": csrf}
    cid = client.post("/api/canvases", json={"name": "c"}, headers=h).get_json()["canvas"]["id"]
    z = client.put(f"/api/canvases/{cid}", json={"zones": [{"url": url, "radius": 200}]},
                   headers=h).get_json()["canvas"]["zones"][0]
    assert (z["url"] == url) is kept


# ------------------------------------------------------------- galleries --

def make_gallery(client, csrf, title="Groupe A", pin="4817"):
    return client.post("/api/galleries", json={"title": title, "pin": pin},
                       headers={"X-CSRF-Token": csrf})


def test_gallery_create_and_slug(client):
    csrf = login(client)
    r = make_gallery(client, csrf, "Un portrait — Groupe A")
    assert r.status_code == 201, r.get_json()
    g = r.get_json()["gallery"]
    assert g["slug"] and " " not in g["slug"]
    assert g["has_pin"] is True


@pytest.mark.parametrize("pin", ["123", "0000", "1234", "abcd", "111111", "9" * 9])
def test_weak_pins_refused(client, pin):
    csrf = login(client)
    r = make_gallery(client, csrf, "G", pin)
    assert r.status_code == 400, f"{pin} was accepted"


def test_gallery_needs_the_pin(client):
    csrf = login(client)
    slug = make_gallery(client, csrf).get_json()["gallery"]["slug"]
    client.post("/api/logout", headers={"X-CSRF-Token": csrf})

    # The name is public; the contents are not.
    pub = client.get(f"/api/g/{slug}")
    assert pub.status_code == 200
    assert pub.get_json()["unlocked"] is False
    assert "canvases" not in pub.get_json()

    assert client.get(f"/api/g/{slug}/canvases").status_code == 403
    assert client.post(f"/api/g/{slug}/unlock", json={"pin": "9999"}).status_code == 401
    assert client.post(f"/api/g/{slug}/unlock", json={"pin": "4817"}).status_code == 200
    assert client.get(f"/api/g/{slug}/canvases").status_code == 200


def test_groups_cannot_see_each_others_galleries(client):
    csrf = login(client)
    h = {"X-CSRF-Token": csrf}
    a = make_gallery(client, csrf, "Groupe A", "4817").get_json()["gallery"]
    b = make_gallery(client, csrf, "Groupe B", "5293").get_json()["gallery"]
    ca = client.post("/api/canvases", json={"name": "A1"}, headers=h).get_json()["canvas"]["id"]
    cb = client.post("/api/canvases", json={"name": "B1"}, headers=h).get_json()["canvas"]["id"]
    client.put(f"/api/canvases/{ca}", json={"room_id": a["id"]}, headers=h)
    client.put(f"/api/canvases/{cb}", json={"room_id": b["id"]}, headers=h)
    client.post("/api/logout", headers=h)

    client.post(f"/api/g/{a['slug']}/unlock", json={"pin": "4817"})
    names = [c["name"] for c in client.get(f"/api/g/{a['slug']}/canvases").get_json()["canvases"]]
    assert names == ["A1"]
    # Unlocking A must not unlock B.
    assert client.get(f"/api/g/{b['slug']}/canvases").status_code == 403
    # Nor read B's canvas directly.
    assert client.get(f"/api/canvases/{cb}").status_code == 404


def test_a_canvas_in_no_gallery_is_not_readable_anonymously(client):
    csrf = login(client)
    cid = client.post("/api/canvases", json={"name": "private"},
                      headers={"X-CSRF-Token": csrf}).get_json()["canvas"]["id"]
    client.post("/api/logout", headers={"X-CSRF-Token": csrf})
    assert client.get(f"/api/canvases/{cid}").status_code == 404


def test_unlocked_visitor_can_read_that_gallerys_canvas(client):
    csrf = login(client)
    h = {"X-CSRF-Token": csrf}
    g = make_gallery(client, csrf).get_json()["gallery"]
    cid = client.post("/api/canvases", json={"name": "A1"}, headers=h).get_json()["canvas"]["id"]
    client.put(f"/api/canvases/{cid}", json={"room_id": g["id"]}, headers=h)
    client.post("/api/logout", headers=h)

    assert client.get(f"/api/canvases/{cid}").status_code == 404
    client.post(f"/api/g/{g['slug']}/unlock", json={"pin": "4817"})
    assert client.get(f"/api/canvases/{cid}").status_code == 200


def test_changing_the_pin_locks_everyone_out_again(client):
    csrf = login(client)
    h = {"X-CSRF-Token": csrf}
    g = make_gallery(client, csrf).get_json()["gallery"]
    client.post("/api/logout", headers=h)
    client.post(f"/api/g/{g['slug']}/unlock", json={"pin": "4817"})
    assert client.get(f"/api/g/{g['slug']}/canvases").status_code == 200

    csrf = login(client)
    client.put(f"/api/galleries/{g['id']}", json={"pin": "7361"},
               headers={"X-CSRF-Token": csrf})
    client.post("/api/logout", headers={"X-CSRF-Token": csrf})
    assert client.get(f"/api/g/{g['slug']}/canvases").status_code == 403
    assert client.post(f"/api/g/{g['slug']}/unlock", json={"pin": "7361"}).status_code == 200


def test_non_owner_cannot_manage_a_gallery(client):
    csrf = login(client)
    h = {"X-CSRF-Token": csrf}
    g = make_gallery(client, csrf).get_json()["gallery"]
    token = client.post("/api/users", json={"name": "mamie"},
                        headers=h).get_json()["setup_url"].rsplit("/", 1)[-1]
    client.post("/api/logout", headers=h)
    csrf2 = client.post(f"/api/setup/{token}",
                        json={"passphrase": "les oiseaux chantent"}).get_json()["csrf"]
    h2 = {"X-CSRF-Token": csrf2}
    assert client.put(f"/api/galleries/{g['id']}", json={"title": "mine"}, headers=h2).status_code == 403
    assert client.delete(f"/api/galleries/{g['id']}", headers=h2).status_code == 403
    assert client.get("/api/galleries").get_json()["galleries"] == []
