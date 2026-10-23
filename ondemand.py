"""The On Demand index: each enabled portal's catalogue, crawled into SQLite (ADR 0003).

The index lives in `ondemand.sqlite` beside `config.json`. It is a disposable cache: a
missing, corrupt or outdated file is recreated empty and crawled again. Resume points and
Watched markers must never live in it (ADR 0006).

Two parts:

- `Index`: the SQLite file. One row per (portal, item id) holding the portal's raw JSON
  plus the indexed columns, the portals' On Demand categories, and each portal's index
  status. `categories()` answers the merged category list with exact counts.
- `Crawler`: one background thread that indexes portals one at a time, at one request a
  second, newest first, committing each page as it goes. It only runs while some Account
  has On Demand switched on.

Portal access is behind a small "catalogue" object, so tests use a fake portal:

    catalogue.portals()          -> {portal id: portal name}, the enabled portals
    catalogue.wanted()           -> True while any Account has On Demand on
    catalogue.categories(portal) -> [{id, title, alias, censored}] or None
    catalogue.page(portal, p)    -> {"total", "pageSize", "items"} or None (p is 1-based)
"""
import json
import logging
import os
import re
import sqlite3
import threading
import time

logger = logging.getLogger("STB-Proxy")

# Bump to make every existing index file be thrown away and crawled again.
SCHEMA_VERSION = 1
# SQLite's page cache, in KiB (a negative cache_size is KiB): about 8 MB of RAM.
CACHE_KIB = 8192
# Category ids that are not real categories: the portal's "All", and Infomir's synthetic
# "Coming soon" whose items can't be played (research 01).
NOT_CATEGORIES = ("*", "coming_soon")
# Seconds between portal requests while crawling.
CRAWL_INTERVAL = 1.0

SCHEMA = """
CREATE TABLE items (
    portal TEXT NOT NULL,
    id TEXT NOT NULL,
    kind TEXT NOT NULL,              -- "movie" or "series"
    name TEXT NOT NULL,
    original_name TEXT NOT NULL,
    year INTEGER,
    added TEXT NOT NULL,             -- the portal's "Y-m-d H:i:s", sorts as text
    rating REAL,
    category_0 TEXT NOT NULL,        -- the portal's category_id, category_id_1, category_id_2
    category_1 TEXT NOT NULL,        -- ("0" when unused)
    category_2 TEXT NOT NULL,
    adult INTEGER NOT NULL,          -- the item is flagged censored or lock
    json TEXT NOT NULL,              -- the portal's row as it came
    PRIMARY KEY (portal, id)
);
CREATE INDEX items_added ON items (portal, added);
CREATE INDEX items_category_0 ON items (portal, category_0);
CREATE INDEX items_category_1 ON items (portal, category_1);
CREATE INDEX items_category_2 ON items (portal, category_2);

-- Title search (name and original name only), kept in step with items by triggers.
CREATE VIRTUAL TABLE items_search USING fts5 (
    name, original_name,
    content = 'items',
    tokenize = 'unicode61 remove_diacritics 2'
);
CREATE TRIGGER items_search_insert AFTER INSERT ON items BEGIN
    INSERT INTO items_search (rowid, name, original_name)
    VALUES (new.rowid, new.name, new.original_name);
END;
CREATE TRIGGER items_search_delete AFTER DELETE ON items BEGIN
    INSERT INTO items_search (items_search, rowid, name, original_name)
    VALUES ('delete', old.rowid, old.name, old.original_name);
END;
CREATE TRIGGER items_search_update AFTER UPDATE ON items BEGIN
    INSERT INTO items_search (items_search, rowid, name, original_name)
    VALUES ('delete', old.rowid, old.name, old.original_name);
    INSERT INTO items_search (rowid, name, original_name)
    VALUES (new.rowid, new.name, new.original_name);
END;

CREATE TABLE categories (
    portal TEXT NOT NULL,
    id TEXT NOT NULL,
    title TEXT NOT NULL,
    merged TEXT NOT NULL,            -- normalisedName(title): same-named categories are one
    censored INTEGER NOT NULL,
    position INTEGER NOT NULL,       -- the portal's order
    PRIMARY KEY (portal, id)
);
CREATE INDEX categories_merged ON categories (merged);

CREATE TABLE portals (
    portal TEXT PRIMARY KEY,
    status TEXT NOT NULL,            -- "indexing", "ready" or "failed"
    pages_done INTEGER NOT NULL DEFAULT 0,
    pages_total INTEGER,
    last_refresh INTEGER             -- epoch seconds of the last complete crawl
);
"""


def normalisedName(title):
    """The merged key of an On Demand category: case-folded, whitespace collapsed."""
    return " ".join(str(title).split()).casefold()


def isSeries(row):
    # Infomir flags Series inside the Movie catalogue (Shape 2); accept 1, "1" and true.
    return str(row.get("is_series", "")).strip().lower() in ("1", "true")


def number(value, kind):
    try:
        result = kind(str(value).strip())
    except (TypeError, ValueError):
        return None
    return result if result else None


def flag(value):
    return str(value or "").strip().lower() in ("1", "true")


def itemRow(portal, row):
    name = str(row.get("name") or "").strip()
    year = re.match(r"\d{4}", str(row.get("year") or ""))
    return (
        portal,
        str(row["id"]),
        "series" if isSeries(row) else "movie",
        name,
        str(row.get("o_name") or "").strip() or name,
        int(year.group(0)) if year else None,
        str(row.get("added") or ""),
        number(row.get("rating_kinopoisk"), float),
        str(row.get("category_id") or "0"),
        str(row.get("category_id_1") or "0"),
        str(row.get("category_id_2") or "0"),
        1 if flag(row.get("censored")) or flag(row.get("lock")) else 0,
        json.dumps(row, separators=(",", ":")),
    )


class Index:
    """The SQLite index file. Safe to share across threads: one connection, one lock."""

    def __init__(self, path):
        self.path = path
        self.lock = threading.RLock()
        self.db = None
        try:
            self.open()
        except sqlite3.DatabaseError as e:
            logger.warning("On Demand index {} unreadable ({}), starting it again".format(path, e))
            self.recreate()

    def open(self):
        self.db = sqlite3.connect(self.path, check_same_thread=False, isolation_level=None)
        self.db.execute("PRAGMA cache_size = -{}".format(CACHE_KIB))
        self.db.execute("PRAGMA journal_mode = WAL")
        self.db.execute("PRAGMA synchronous = NORMAL")
        version = self.db.execute("PRAGMA user_version").fetchone()[0]
        if version != SCHEMA_VERSION:
            if version != 0 or self.db.execute(
                    "SELECT count(*) FROM sqlite_master").fetchone()[0]:
                raise sqlite3.DatabaseError("schema version {}".format(version))
            self.db.executescript("BEGIN;" + SCHEMA + "PRAGMA user_version = {};COMMIT;".format(
                SCHEMA_VERSION))
        # A file that is not a database, or a damaged one, fails here (DatabaseError).
        self.db.execute("SELECT count(*) FROM portals").fetchone()

    def recreate(self):
        with self.lock:
            if self.db is not None:
                try:
                    self.db.close()
                except sqlite3.Error:
                    pass
            for suffix in ("", "-wal", "-shm", "-journal"):
                try:
                    os.remove(self.path + suffix)
                except FileNotFoundError:
                    pass
            self.open()

    def close(self):
        with self.lock:
            if self.db is not None:
                self.db.close()
                self.db = None

    def transaction(self):
        return Transaction(self)

    # Writes (the crawler's).

    def setCategories(self, portal, categories):
        rows = [
            (portal, str(c["id"]), str(c.get("title") or ""), normalisedName(c.get("title") or ""),
             1 if flag(c.get("censored")) else 0, position)
            for position, c in enumerate(categories)
            if str(c.get("id")) not in NOT_CATEGORIES and str(c.get("title") or "").strip()
        ]
        with self.transaction() as db:
            db.execute("DELETE FROM categories WHERE portal = ?", (portal,))
            db.executemany("INSERT INTO categories VALUES (?, ?, ?, ?, ?, ?)", rows)

    def addItems(self, portal, items):
        """Insert or update items, given as the portal's rows."""
        rows = [itemRow(portal, row) for row in items if row.get("id") not in (None, "")]
        with self.transaction() as db:
            db.executemany(
                "INSERT INTO items VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT (portal, id) DO UPDATE SET kind = excluded.kind, "
                "name = excluded.name, original_name = excluded.original_name, "
                "year = excluded.year, added = excluded.added, rating = excluded.rating, "
                "category_0 = excluded.category_0, category_1 = excluded.category_1, "
                "category_2 = excluded.category_2, adult = excluded.adult, json = excluded.json",
                rows,
            )

    def setStatus(self, portal, status, pagesDone=None, pagesTotal=None, lastRefresh=None):
        with self.transaction() as db:
            db.execute(
                "INSERT INTO portals (portal, status, pages_done, pages_total, last_refresh) "
                "VALUES (?, ?, coalesce(?, 0), ?, ?) "
                "ON CONFLICT (portal) DO UPDATE SET status = excluded.status, "
                "pages_done = coalesce(?, pages_done), pages_total = coalesce(?, pages_total), "
                "last_refresh = coalesce(?, last_refresh)",
                (portal, status, pagesDone, pagesTotal, lastRefresh, pagesDone, pagesTotal, lastRefresh),
            )

    # Reads.

    def status(self, portal):
        """{status, progress, lastRefresh} for one portal. A portal never crawled reads
        "failed" (it has no index), as does one whose first crawl failed."""
        with self.lock:
            row = self.db.execute(
                "SELECT status, pages_done, pages_total, last_refresh FROM portals WHERE portal = ?",
                (portal,),
            ).fetchone()
        if row is None:
            return {"status": "failed", "progress": None, "lastRefresh": None}
        status, done, total, lastRefresh = row
        progress = None
        if status == "indexing":
            progress = min(99, int(100 * done / total)) if total else 0
        return {"status": status, "progress": progress, "lastRefresh": lastRefresh}

    def item(self, portal, id):
        """One indexed item, or None: its indexed columns plus the portal's row as `raw`."""
        with self.lock:
            row = self.db.execute(
                "SELECT kind, name, original_name, year, added, rating, category_0, category_1, "
                "category_2, adult, json FROM items WHERE portal = ? AND id = ?",
                (portal, str(id)),
            ).fetchone()
        if row is None:
            return None
        kind, name, originalName, year, added, rating, c0, c1, c2, adult, raw = row
        return {
            "portal": portal, "id": str(id), "kind": kind, "name": name,
            "originalName": originalName, "year": year, "added": added, "rating": rating,
            "categories": [c for c in (c0, c1, c2) if c != "0"], "adult": bool(adult),
            "raw": json.loads(raw),
        }

    def categories(self, portals):
        """The On Demand categories of these portals, merged by normalised name.

        [{id, name, count}] in name order. `id` is the merged name, `name` takes its casing
        from the first of `portals` that has the category, and `count` is the exact number
        of items in it (an item counts once however many of its slots match). Categories
        with no items are left out.
        """
        portals = list(portals)
        if not portals:
            return []
        marks = ",".join("?" * len(portals))
        with self.lock:
            counts = dict(self.db.execute(
                "SELECT c.merged, count(DISTINCT i.rowid) FROM items i JOIN categories c "
                "ON c.portal = i.portal AND c.id IN (i.category_0, i.category_1, i.category_2) "
                "WHERE i.portal IN ({}) GROUP BY c.merged".format(marks), portals
            ).fetchall())
            titles = self.db.execute(
                "SELECT portal, merged, title FROM categories WHERE portal IN ({}) "
                "ORDER BY position".format(marks), portals
            ).fetchall()
        names = {}
        for portal in portals:
            for owner, merged, title in titles:
                if owner == portal:
                    names.setdefault(merged, title)
        return sorted(
            ({"id": merged, "name": names[merged], "count": count}
             for merged, count in counts.items() if count and merged in names),
            key=lambda c: c["id"],
        )


class Transaction:
    def __init__(self, index):
        self.index = index

    def __enter__(self):
        self.index.lock.acquire()
        self.index.db.execute("BEGIN")
        return self.index.db

    def __exit__(self, kind, value, traceback):
        try:
            self.index.db.execute("COMMIT" if kind is None else "ROLLBACK")
        finally:
            self.index.lock.release()


class Crawler:
    """Indexes portals not yet indexed, one at a time, in one background thread."""

    def __init__(self, index, catalogue, sleep=time.sleep, interval=CRAWL_INTERVAL, clock=time.time,
                 background=True):
        self.index = index
        self.catalogue = catalogue
        self.sleep = sleep
        self.interval = interval
        self.clock = clock
        # False runs wake()'s crawl in the caller, for tests of what uses the crawler.
        self.background = background
        self.thread = None
        self.lock = threading.Lock()
        self.again = False
        self.requests = 0

    def wake(self):
        """Start crawling in the background if some Account wants On Demand and no crawl is
        running. Safe to call often: on boot and whenever a switch is turned on."""
        with self.lock:
            if self.thread is not None and self.thread.is_alive():
                self.again = True
                return self.thread
            if not self.catalogue.wanted():
                return None
            self.again = False
            if not self.background:
                self.crawl()
                return None
            self.thread = threading.Thread(target=self.run, name="On Demand crawl", daemon=True)
            self.thread.start()
            return self.thread

    def run(self):
        while True:
            try:
                self.crawl()
            except Exception:
                logger.exception("On Demand crawl stopped")
            with self.lock:
                if not self.again or not self.catalogue.wanted():
                    self.thread = None
                    return
                self.again = False

    def crawl(self):
        """Index every enabled portal that isn't indexed yet, in turn. Stops early (keeping
        what it has) when every Account's On Demand is switched off."""
        self.requests = 0
        if not self.catalogue.wanted():
            return
        queue = {portal: name for portal, name in self.catalogue.portals().items()
                 if self.index.status(portal)["status"] != "ready"}
        # A portal waiting its turn is indexing too (at 0%), not failed.
        for portal in queue:
            self.index.setStatus(portal, "indexing")
        for portal, name in queue.items():
            if not self.catalogue.wanted():
                return
            self.crawlPortal(portal, name)

    def request(self, call, *args):
        if self.requests:
            self.sleep(self.interval)
        self.requests += 1
        return call(*args)

    def crawlPortal(self, portal, name):
        logger.info("On Demand: indexing {}".format(name))
        self.index.setStatus(portal, "indexing", pagesDone=0)
        categories = self.request(self.catalogue.categories, portal)
        if categories is None:
            return self.fail(portal, name, "no categories")
        self.index.setCategories(portal, categories)
        page, pages, previous = 1, None, None
        while True:
            if not self.catalogue.wanted():
                logger.info("On Demand: indexing {} paused, no Account has On Demand on".format(name))
                return
            result = self.request(self.catalogue.page, portal, page)
            if result is None:
                return self.fail(portal, name, "page {} failed".format(page))
            ids = [str(row.get("id")) for row in result["items"]]
            # An empty page, or a repeat of the last one (a portal ignoring p=), is the end.
            if not ids or ids == previous:
                break
            if result["pageSize"] and result["total"]:
                pages = -(-result["total"] // result["pageSize"])
            self.index.addItems(portal, result["items"])
            self.index.setStatus(portal, "indexing", pagesDone=page, pagesTotal=pages)
            if pages is not None and page >= pages:
                break
            page, previous = page + 1, ids
        self.index.setStatus(portal, "ready", lastRefresh=int(self.clock()))
        logger.info("On Demand: {} indexed".format(name))

    def fail(self, portal, name, why):
        logger.error("On Demand: couldn't index {} ({})".format(name, why))
        self.index.setStatus(portal, "failed")
