"""Viewer accounts: a username and hashed password mapped to a set of blocks.

Accounts live in config.json under "accounts", each a record
{"username": str, "hash": str, "blocks": [str], "enabled": bool}. Passwords are
stored only as a self-describing PBKDF2-HMAC-SHA256 string (see hashPassword),
never in the clear. Blocks are referenced by name; see ADR 0001 for the model.
"""
import base64
import hashlib
import hmac
import secrets

ALGORITHM = "pbkdf2_sha256"
ITERATIONS = 600000
SALT_BYTES = 16


def hashPassword(password, iterations=ITERATIONS):
    """A self-describing hash: pbkdf2_sha256$<iters>$<salt_b64>$<hash_b64>."""
    salt = secrets.token_bytes(SALT_BYTES)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return "{}${}${}${}".format(
        ALGORITHM,
        iterations,
        base64.b64encode(salt).decode("ascii"),
        base64.b64encode(digest).decode("ascii"),
    )


def verifyPassword(password, stored):
    """True if password matches the stored hash. A malformed hash is simply wrong."""
    try:
        algorithm, iterations, salt, digest = stored.split("$")
        if algorithm != ALGORITHM:
            return False
        salt = base64.b64decode(salt, validate=True)
        digest = base64.b64decode(digest, validate=True)
        iterations = int(iterations)
    except (AttributeError, TypeError, ValueError):
        return False
    computed = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(computed, digest)


def normaliseAccounts(value):
    """Only well-formed records, so a hand-edited config can't break the page."""
    records = []
    if not isinstance(value, list):
        return records
    for record in value:
        if not isinstance(record, dict):
            continue
        username = record.get("username")
        if not isinstance(username, str) or not username:
            continue
        blocks = record.get("blocks")
        records.append({
            "username": username,
            "hash": record.get("hash", ""),
            "blocks": [name for name in blocks if isinstance(name, str)] if isinstance(blocks, list) else [],
            "enabled": bool(record.get("enabled", True)),
        })
    return records


def findAccount(records, username):
    for record in records:
        if record["username"] == username:
            return record
    return None


def renameBlock(records, old, new):
    """Put block new in place of old in every account's list, in place."""
    for record in records:
        record["blocks"] = [new if name == old else name for name in record["blocks"]]


def pruneBlocks(records, names):
    """Drop block names that no block uses any more, in place."""
    for record in records:
        record["blocks"] = [name for name in record["blocks"] if name in names]
