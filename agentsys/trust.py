"""Tamper-evident event chain and human-action provenance (not unbreakable on same-user shell)."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import subprocess
from pathlib import Path

GENESIS = "GENESIS"
CHAIN_META = "chain_prev_hash"
LEGACY_MARKER = "legacy_chain_anchor"


class HumanActionRefused(Exception):
    pass


def agentsys_dir() -> Path:
    return Path(os.environ.get("AGENTSYS_HOME", Path.home() / ".agentsys")).expanduser()


def install_key_path() -> Path:
    return agentsys_dir() / "install.key"


def approver_path() -> Path:
    return agentsys_dir() / "approver.json"


def load_install_key() -> bytes:
    p = install_key_path()
    p.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if p.exists():
        return p.read_bytes()
    key = os.urandom(32)
    p.write_bytes(key)
    try:
        os.chmod(p, 0o600)
    except OSError:
        pass
    return key


def legacy_anchor(key: bytes, last_legacy_id: int) -> str:
    return hmac.new(key, f"{LEGACY_MARKER}:{last_legacy_id}".encode(), hashlib.sha256).hexdigest()


def event_canonical(ts: float, actor: str, task_id, kind: str, payload: dict) -> str:
    body = {"ts": ts, "actor": actor, "task_id": task_id, "kind": kind, "payload": payload}
    return json.dumps(body, sort_keys=True, separators=(",", ":"))


def chain_hash(key: bytes, prev_hash: str, canonical: str) -> str:
    return hmac.new(key, f"{prev_hash}\n{canonical}".encode(), hashlib.sha256).hexdigest()


def collect_provenance() -> dict:
    prov = {
        "stdin_tty": False,
        "stdout_tty": False,
        "controlling_tty": False,
        "dispatched": os.environ.get("AGENTSYS_DISPATCHED") == "1",
        "dashboard": os.environ.get("AGENTSYS_DASHBOARD_OK") == "1",
        "parents": [],
    }
    try:
        prov["stdin_tty"] = os.isatty(0)
        prov["stdout_tty"] = os.isatty(1)
        prov["controlling_tty"] = os.isatty(os.open("/dev/tty", os.O_RDWR | os.O_NOCTTY))
    except OSError:
        pass
    try:
        out = subprocess.run(["ps", "-o", "comm="], capture_output=True, text=True, timeout=2)
        if out.returncode == 0:
            prov["parents"] = [l.strip() for l in out.stdout.splitlines() if l.strip()][:8]
    except (OSError, subprocess.SubprocessError):
        pass
    return prov


def assert_human_actor(actor: str, action: str, *, dashboard_ok: bool = False):
    if not actor.startswith("human:"):
        raise HumanActionRefused(f"{action} requires a human: actor, not {actor}")
    if os.environ.get("AGENTSYS_DISPATCHED") == "1":
        raise HumanActionRefused("refused: human actions are blocked inside a dispatched agent run")
    prov = collect_provenance()
    if os.environ.get("AGENTSYS_TEST_SUITE") == "1":
        return prov
    if os.environ.get("AGENTSYS_DEMO") == "1":
        return prov
    if dashboard_ok or os.environ.get("AGENTSYS_DASHBOARD_OK") == "1":
        return prov
    if not (prov["stdin_tty"] or prov["controlling_tty"]):
        raise HumanActionRefused(
            "refused: human actions need an interactive terminal or the dashboard (with a valid session token)")
    return prov


def confirm_on_tty(prompt: str) -> bool:
    if os.environ.get("AGENTSYS_SKIP_TTY_CONFIRM") == "1":
        return True
    try:
        tty = open("/dev/tty", "r+")
    except OSError:
        return False
    try:
        tty.write(prompt)
        tty.flush()
        line = tty.readline().strip().lower()
        return line in ("yes", "y")
    finally:
        tty.close()


def approver_configured() -> bool:
    return approver_path().is_file()


def init_approver(passphrase: str) -> None:
    salt = os.urandom(16)
    verifier = hashlib.scrypt(passphrase.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
    p = approver_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"salt": salt.hex(), "verifier": verifier.hex()}), encoding="utf-8")
    try:
        os.chmod(p, 0o600)
    except OSError:
        pass


def verify_passphrase(passphrase: str) -> bool:
    if not approver_configured():
        return True
    data = json.loads(approver_path().read_text(encoding="utf-8"))
    salt = bytes.fromhex(data["salt"])
    want = bytes.fromhex(data["verifier"])
    got = hashlib.scrypt(passphrase.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return got == want


def approval_signature(passphrase: str, message: str) -> str:
    if not approver_configured():
        return ""
    data = json.loads(approver_path().read_text(encoding="utf-8"))
    salt = bytes.fromhex(data["salt"])
    key = hashlib.scrypt(passphrase.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return hmac.new(key, message.encode(), hashlib.sha256).hexdigest()


def verify_approval_signature(sig: str, passphrase: str, message: str) -> bool:
    if not approver_configured():
        return not sig
    if not sig:
        return False
    return hmac.compare_digest(sig, approval_signature(passphrase, message))


def verify_event_chain(db, key: bytes, strict: bool = False) -> list:
    """Return list of problem strings; empty if clean."""
    problems = []
    rows = db.execute("SELECT * FROM events ORDER BY id").fetchall()
    expected_prev = None
    last_chained_hash = None
    for row in rows:
        status = row["chain_status"] if "chain_status" in row.keys() else "legacy"
        if status == "legacy" or not row["event_hash"]:
            continue
        if expected_prev is None:
            expected_prev = row["prev_hash"]
        canonical = event_canonical(row["ts"], row["actor"], row["task_id"], row["kind"],
                                    json.loads(row["payload"]))
        if row["prev_hash"] != expected_prev:
            problems.append(f"event {row['id']}: prev_hash mismatch (expected {expected_prev[:12]}…)")
        want = chain_hash(key, row["prev_hash"], canonical)
        if row["event_hash"] != want:
            problems.append(f"event {row['id']}: hash mismatch (tampered or corrupted)")
        sig = json.loads(row["payload"]).get("approval_signature")
        if sig and row["kind"] in ("approval.granted", "approval.denied"):
            problems.append(f"event {row['id']}: approval signature present but cannot verify without passphrase")
            if strict:
                problems[-1] += " [strict: FAIL]"
        expected_prev = row["event_hash"]
        last_chained_hash = row["event_hash"]
    meta_prev = db.execute("SELECT value FROM meta WHERE key=?", (CHAIN_META,)).fetchone()
    if last_chained_hash and meta_prev and meta_prev["value"] != last_chained_hash:
        problems.append("meta chain_prev_hash does not match last chained event")
    return problems
