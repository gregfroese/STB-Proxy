from bff import config as config_module
from bff.sessions import SessionStore, build_fernet


def make_store(tmp_path):
    return SessionStore(str(tmp_path / "sessions.db"), fernet=build_fernet())


def test_create_get_and_delete(tmp_path):
    store = make_store(tmp_path)
    token, csrf = store.create("katie", "katie", "s3cret", "ua", "127.0.0.1")
    assert token and csrf

    session = store.get(token)
    assert session is not None
    assert session.username == "katie"
    assert session.account == "katie"
    assert session.basic(store.fernet) == ("katie", "s3cret")

    store.delete(token)
    assert store.get(token) is None


def test_only_the_token_hash_is_stored(tmp_path):
    store = make_store(tmp_path)
    token, _ = store.create("katie", "katie", "s3cret", None, None)
    with store._connect() as conn:  # noqa: SLF001 - white-box store assertion
        rows = conn.execute("SELECT token_hash FROM sessions").fetchall()
    assert len(rows) == 1
    assert rows[0]["token_hash"] != token


def test_idle_expiry_is_enforced(tmp_path, monkeypatch):
    store = make_store(tmp_path)
    token, _ = store.create("katie", "katie", "s3cret", None, None)
    monkeypatch.setattr(config_module.config, "idle", 0)
    assert store.get(token) is None


def test_password_is_not_stored_in_plaintext(tmp_path):
    store = make_store(tmp_path)
    store.create("katie", "katie", "s3cret", None, None)
    with store._connect() as conn:  # noqa: SLF001
        blob = conn.execute("SELECT basic_enc FROM sessions").fetchone()["basic_enc"]
    assert b"s3cret" not in bytes(blob)
