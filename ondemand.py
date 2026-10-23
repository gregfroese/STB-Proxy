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
  has On Demand switched on. After the first crawl it keeps each portal fresh: an
  incremental pull every 2 h, a full re-crawl weekly at about 04:00 local that drops what
  the portal no longer lists, and a retry 5 min after a failure (the portal reads stale
  and keeps its last good index meanwhile).

Portal access is behind a small "catalogue" object, so tests use a fake portal:

    catalogue.portals()          -> {portal id: portal name}, the enabled portals
    catalogue.wanted()           -> True while any Account has On Demand on
    catalogue.categories(portal, source="vod") -> [{id, title, alias, censored}] or None
    catalogue.page(portal, p, source="vod")    -> {"total", "pageSize", "items"} or None

`p` is 1-based. `source` is the portal's `type=`: "vod" (every portal), or "series", which
only Xtream-family portals answer (research 01). Series from `type=series` are indexed with
their ids, and their category ids, prefixed `series:` (SERIES), because Xtream numbers them
apart from the Movies: the Series 7 of a portal is the item "series:7". Its raw row keeps
the portal's own ids.
"""
import collections
import datetime
import json
import logging
import os
import re
import sqlite3
import threading
import time

logger = logging.getLogger("STB-Proxy")

# Bump to make every existing index file be thrown away and crawled again.
SCHEMA_VERSION = 2
# SQLite's page cache, in KiB (a negative cache_size is KiB): about 8 MB of RAM.
CACHE_KIB = 8192
# Category ids that are not real categories: the portal's "All", and Infomir's synthetic
# "Coming soon" whose items can't be played (research 01).
NOT_CATEGORIES = ("*", "coming_soon")
# The id prefix of what an Xtream portal lists under type=series, items and categories.
SERIES = "series:"
# Seconds between portal requests while crawling.
CRAWL_INTERVAL = 1.0
# The viewer sorts (ADR 0003): Recently added, A-Z, Year and Rating, newest first, with
# unknown years and ratings last. Ties go to the most recently added.
NEWEST = "i.added DESC, i.name COLLATE NOCASE, i.portal, i.id"
SORTS = {
    "added": NEWEST,
    "name": "i.name COLLATE NOCASE, " + NEWEST,
    "year": "i.year IS NULL, i.year DESC, " + NEWEST,
    "rating": "i.rating IS NULL, i.rating DESC, " + NEWEST,
}

# An incremental pull (newest first, up to the first page with nothing new) this often.
REFRESH_AGE = 2 * 3600
# After a failed crawl or refresh, try again this much later (as the Guide does).
RETRY_AGE = 300
# A full re-crawl, which drops what the portal no longer lists, at the first FULL_HOUR
# (local time) at least FULL_AGE after the last one ended: weekly, at about 04:00 (6.5 days
# on, so a crawl ending just after 04:00 still waits a week, not six days).
FULL_AGE = int(6.5 * 24 * 3600)
FULL_HOUR = 4

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
    status TEXT NOT NULL,            -- "indexing", "ready", "stale", "partial" or "failed"
    pages_done INTEGER NOT NULL DEFAULT 0,
    pages_total INTEGER,
    last_refresh INTEGER,            -- epoch seconds of the last good refresh of any kind
    last_full INTEGER,               -- epoch seconds of the last complete full crawl
    partial INTEGER NOT NULL DEFAULT 0  -- the Xtream type=series paging bug cut the index short
);
"""


def nextFull(lastFull):
    """When the full re-crawl after one at `lastFull` (epoch seconds) is due."""
    after = datetime.datetime.fromtimestamp(lastFull + FULL_AGE)
    due = after.replace(hour=FULL_HOUR, minute=0, second=0, microsecond=0)
    if due < after:
        due += datetime.timedelta(days=1)
    return due.timestamp()


def damaged(error):
    """Whether a sqlite3 error means the file itself is bad (not busy, locked or a
    constraint): a plain DatabaseError, as "database disk image is malformed" is."""
    return type(error) is sqlite3.DatabaseError or isinstance(error, sqlite3.InternalError)


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


def indexId(id, source):
    """The id an item or category of the portal's `type=source` listing is indexed by."""
    return SERIES + str(id) if source == "series" else str(id)


def itemRow(portal, row, source="vod"):
    name = str(row.get("name") or "").strip()
    year = re.match(r"\d{4}", str(row.get("year") or ""))

    def slot(key):
        value = str(row.get(key) or "0")
        return value if value == "0" else indexId(value, source)

    return (
        portal,
        indexId(row["id"], source),
        "series" if source == "series" or isSeries(row) else "movie",
        name,
        str(row.get("o_name") or "").strip() or name,
        int(year.group(0)) if year else None,
        str(row.get("added") or ""),
        number(row.get("rating_kinopoisk"), float),
        slot("category_id"),
        slot("category_id_1"),
        slot("category_id_2"),
        1 if flag(row.get("censored")) or flag(row.get("lock")) else 0,
        json.dumps(row, separators=(",", ":")),
    )


# What portals send for "nothing here" (research 01): Xtream's "N/A"/"N/a", a dash.
PLACEHOLDERS = ("", "n/a", "-")


def present(value):
    """A portal field as text, or None for a placeholder (or a missing or false one)."""
    if value is None or value is False:
        return None
    text = str(value).strip()
    return None if text.lower() in PLACEHOLDERS else text


def searchQuery(text):
    """A viewer's search as an FTS5 query: every word, as a prefix. "" when it has no words."""
    return " ".join('"{}"*'.format(word) for word in re.findall(r"\w+", text))


class Filter(collections.namedtuple("Filter", "hidden adult")):
    """What one viewer may see of the catalogue (ADR 0004).

    - `hidden`: merged category names (normalisedName) no viewer sees.
    - `adult`: whether adult content is allowed. When it isn't, categories the portal flags
      censored and items flagged censored or lock are removed too.

    Hiding is strict: an item with a removed category in any of its 3 slots is gone.
    Filter() removes nothing (the operator's view).
    """

    def __new__(cls, hidden=(), adult=True):
        return super().__new__(cls, frozenset(normalisedName(name) for name in hidden), bool(adult))

    def where(self, alias="i"):
        """(SQL condition on the items row `alias`, args): true for an item this viewer may
        see, or None when nothing is removed. The one place the filter is applied."""
        removed, args = [], []
        if self.hidden:
            removed.append("hc.merged IN ({})".format(",".join("?" * len(self.hidden))))
            args.extend(sorted(self.hidden))
        if not self.adult:
            removed.append("hc.censored = 1")
        if not removed:
            return None
        sql = ("NOT EXISTS (SELECT 1 FROM categories hc WHERE hc.portal = {0}.portal "
               "AND hc.id IN ({0}.category_0, {0}.category_1, {0}.category_2) AND ({1}))").format(
            alias, " OR ".join(removed))
        if not self.adult:
            sql = "{}.adult = 0 AND {}".format(alias, sql)
        return sql, args


def visibleWhere(where, args, visible, alias="i"):
    """A list of SQL conditions and their args, joined with AND, plus the Filter's."""
    extra = visible.where(alias)
    if extra is not None:
        where = list(where) + [extra[0]]
        args = list(args) + extra[1]
    return " AND ".join(where), args


def listItem(portal, id, kind, name, year, rating, added, raw):
    """A list item for the viewer API, placeholders read None. `poster` is the portal's
    own poster URL here; the caller adds `portalName` and swaps in its proxied poster."""
    return {
        "portal": portal, "id": id, "kind": kind, "name": name, "year": year,
        "rating": rating, "added": present(added),
        "poster": present(raw.get("screenshot_uri")),
    }


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

    def setCategories(self, portal, categories, source="vod"):
        """Replace the portal's categories of its `type=source` listing."""
        offset = 1000000 if source == "series" else 0  # after the Movies' in portal order
        rows = [
            (portal, indexId(c["id"], source), str(c.get("title") or ""), normalisedName(c.get("title") or ""),
             1 if flag(c.get("censored")) else 0, offset + position)
            for position, c in enumerate(categories)
            if str(c.get("id")) not in NOT_CATEGORIES and str(c.get("title") or "").strip()
        ]
        with self.transaction() as db:
            db.execute("DELETE FROM categories WHERE portal = ? AND (substr(id, 1, ?) = ?) = ?",
                       (portal, len(SERIES), SERIES, source == "series"))
            db.executemany("INSERT INTO categories VALUES (?, ?, ?, ?, ?, ?)", rows)

    def addItems(self, portal, items, source="vod"):
        """Insert or update items, given as the portal's rows of its `type=source` listing."""
        rows = [itemRow(portal, row, source) for row in items if row.get("id") not in (None, "")]
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

    def keepOnly(self, portal, ids, source="vod"):
        """Drop this portal's items of its `type=source` listing whose (indexed) ids aren't
        in `ids`: what a full crawl no longer found."""
        with self.transaction() as db:
            gone = [(portal, id) for (id,) in db.execute(
                "SELECT id FROM items WHERE portal = ? AND (substr(id, 1, ?) = ?) = ?",
                (portal, len(SERIES), SERIES, source == "series"),
            ) if id not in ids]
            db.executemany("DELETE FROM items WHERE portal = ? AND id = ?", gone)
        return len(gone)

    def purge(self, portal):
        """Forget a deleted portal: its items, categories and status."""
        with self.transaction() as db:
            for table in ("items", "categories", "portals"):
                db.execute("DELETE FROM {} WHERE portal = ?".format(table), (portal,))

    def setStatus(self, portal, status, pagesDone=None, pagesTotal=None, lastRefresh=None, lastFull=None,
                  partial=None):
        """Set a portal's status. Every other value left as None keeps what it was."""
        partial = None if partial is None else int(bool(partial))
        with self.transaction() as db:
            db.execute(
                "INSERT INTO portals (portal, status, pages_done, pages_total, last_refresh, last_full, partial) "
                "VALUES (?, ?, coalesce(?, 0), ?, ?, ?, coalesce(?, 0)) "
                "ON CONFLICT (portal) DO UPDATE SET status = excluded.status, "
                "pages_done = coalesce(?, pages_done), pages_total = coalesce(?, pages_total), "
                "last_refresh = coalesce(?, last_refresh), last_full = coalesce(?, last_full), "
                "partial = coalesce(?, partial)",
                (portal, status, pagesDone, pagesTotal, lastRefresh, lastFull, partial,
                 pagesDone, pagesTotal, lastRefresh, lastFull, partial),
            )

    # Reads.

    def addedOf(self, portal, ids):
        """{id: added} of those of these item ids already indexed."""
        ids = list(ids)
        if not ids:
            return {}
        with self.lock:
            return dict(self.db.execute(
                "SELECT id, added FROM items WHERE portal = ? AND id IN ({})".format(",".join("?" * len(ids))),
                [portal, *ids],
            ).fetchall())

    def refreshState(self, portal):
        """What the crawler needs to know to schedule a portal, or None if never crawled."""
        with self.lock:
            row = self.db.execute(
                "SELECT status, last_refresh, last_full, partial, pages_done FROM portals WHERE portal = ?",
                (portal,),
            ).fetchone()
        if row is None:
            return None
        status, lastRefresh, lastFull, partial, pagesDone = row
        return {"status": status, "lastRefresh": lastRefresh, "lastFull": lastFull, "partial": bool(partial),
                "pagesDone": pagesDone}

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

    def item(self, portal, id, visible=Filter()):
        """One indexed item `visible` (a Filter) lets through, or None: its indexed columns
        plus the portal's row as `raw`."""
        where, args = visibleWhere(["i.portal = ?", "i.id = ?"], [portal, str(id)], visible)
        with self.lock:
            row = self.db.execute(
                "SELECT kind, name, original_name, year, added, rating, category_0, category_1, "
                "category_2, adult, json FROM items i WHERE " + where, args,
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

    def detail(self, portal, id, visible=Filter()):
        """A Movie's or Series' detail for the viewer API, or None (also when `visible`, a
        Filter, removes it): its list item plus the portal's facts, placeholders None,
        `categories` as merged ids."""
        item = self.item(portal, id, visible)
        if item is None:
            return None
        raw = item["raw"]
        with self.lock:
            merged = dict(self.db.execute(
                "SELECT id, merged FROM categories WHERE portal = ? AND id IN ({})".format(
                    ",".join("?" * len(item["categories"]))), [portal] + item["categories"],
            ).fetchall())
        detail = listItem(portal, item["id"], item["kind"], item["name"], item["year"],
                          item["rating"], item["added"], raw)
        if item["originalName"] != item["name"]:
            detail["originalName"] = item["originalName"]
        detail.update(
            description=present(raw.get("description")),
            genres=present(raw.get("genres_str")),
            director=present(raw.get("director")),
            actors=present(raw.get("actors")),
            country=present(raw.get("country")),
            durationMin=number(raw.get("time"), int),
            ageRating=present(raw.get("rating_mpaa")),
            categories=list(dict.fromkeys(merged[c] for c in item["categories"] if c in merged)),
        )
        return detail

    def items(self, portals, category=None, q=None, sort=None, offset=0, limit=60, visible=Filter()):
        """A page of the items of these portals that `visible` (a Filter) lets through:
        (exact total, [list item]).

        - `category` is a merged category id; None is "All", where an item in several
          categories is still one item.
        - `q` searches titles (name and original name, not actors): each word is a prefix,
          accents and case are ignored. Results rank by relevance, then Recently added.
        - `sort` is one of SORTS. It defaults to Recently added, or relevance for a search.
        """
        portals = list(portals)
        match = searchQuery(q) if q is not None else None
        if not portals or match == "":
            return 0, []
        tables = "items i"
        where = ["i.portal IN ({})".format(",".join("?" * len(portals)))]
        args = portals
        if match is not None:
            # CROSS JOIN keeps the search the outer loop; else SQLite may re-run it per row.
            tables = "items_search CROSS JOIN items i ON i.rowid = items_search.rowid"
            where.insert(0, "items_search MATCH ?")
            args = [match] + args
        if category is not None:
            where.append("EXISTS (SELECT 1 FROM categories c WHERE c.portal = i.portal "
                         "AND c.merged = ? AND c.id IN (i.category_0, i.category_1, i.category_2))")
            args = args + [category]
        where, args = visibleWhere(where, args, visible)
        if sort:
            order = SORTS[sort]
        else:
            order = "bm25(items_search), " + NEWEST if match else NEWEST
        with self.lock:
            total = self.db.execute(
                "SELECT count(*) FROM {} WHERE {}".format(tables, where), args).fetchone()[0]
            rows = self.db.execute(
                "SELECT i.portal, i.id, i.kind, i.name, i.year, i.rating, i.added, i.json "
                "FROM {} WHERE {} ORDER BY {} LIMIT ? OFFSET ?".format(tables, where, order),
                args + [limit, offset]).fetchall()
        return total, [listItem(*row[:-1], json.loads(row[-1])) for row in rows]

    def categories(self, portals, visible=Filter()):
        """The On Demand categories of these portals, merged by normalised name, counting
        only the items `visible` (a Filter) lets through.

        [{id, name, count}] in name order. `id` is the merged name, `name` takes its casing
        from the first of `portals` that has the category, and `count` is the exact number
        of items in it (an item counts once however many of its slots match). Categories
        with no items are left out.
        """
        portals = list(portals)
        if not portals:
            return []
        marks = ",".join("?" * len(portals))
        where, args = visibleWhere(["i.portal IN ({})".format(marks)], portals, visible)
        with self.lock:
            counts = dict(self.db.execute(
                "SELECT c.merged, count(DISTINCT i.rowid) FROM items i JOIN categories c "
                "ON c.portal = i.portal AND c.id IN (i.category_0, i.category_1, i.category_2) "
                "WHERE {} GROUP BY c.merged".format(where), args
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

    def catalogue(self, portals):
        """The operator's view of the merged categories of these portals, nothing filtered:
        [{id, name, portals, count, adult}] by id, empty categories included. `portals` lists
        the portals carrying the category (in the order given) and `adult` is whether any of
        them flags it censored.
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
            rows = self.db.execute(
                "SELECT portal, merged, title, censored FROM categories WHERE portal IN ({}) "
                "ORDER BY position".format(marks), portals
            ).fetchall()
        merged = {}
        for portal in portals:
            for owner, id, title, censored in rows:
                if owner != portal:
                    continue
                category = merged.setdefault(
                    id, {"id": id, "name": title, "portals": [], "count": counts.get(id, 0), "adult": False})
                if portal not in category["portals"]:
                    category["portals"].append(portal)
                category["adult"] = category["adult"] or bool(censored)
        return sorted(merged.values(), key=lambda c: c["id"])

    def itemCounts(self, portals):
        """{portal: number of indexed items} for these portals, nothing filtered."""
        portals = list(portals)
        if not portals:
            return {}
        with self.lock:
            counts = dict(self.db.execute(
                "SELECT portal, count(*) FROM items WHERE portal IN ({}) GROUP BY portal".format(
                    ",".join("?" * len(portals))), portals).fetchall())
        return {portal: counts.get(portal, 0) for portal in portals}


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
    """Keeps every enabled portal's index fresh, one portal at a time, in one background
    thread: a first crawl for a portal never indexed, then an incremental pull every
    REFRESH_AGE and a full re-crawl weekly (nextFull)."""

    def __init__(self, index, catalogue, sleep=time.sleep, interval=CRAWL_INTERVAL, clock=time.time,
                 background=True, timer=threading.Timer):
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
        # {portal: epoch seconds}: after a failure, nothing is tried before then.
        self.retryAt = {}
        # The background thread's wake-up for the next refresh due (a threading.Timer).
        self.timer = timer
        self.armed = None

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
            crashed = False
            try:
                self.crawl()
            except Exception:
                logger.exception("On Demand crawl stopped")
                crashed = True
            with self.lock:
                if not self.again or not self.catalogue.wanted():
                    self.thread = None
                    # After a crash, don't come straight back to whatever broke.
                    self.schedule(RETRY_AGE if crashed else 0)
                    return
                self.again = False

    def schedule(self, atLeast=0):
        """Arm one wake() for when the next refresh is due. Nothing is armed while every
        Account is off: refreshes pause until a switch is turned on again."""
        if self.armed is not None:
            self.armed.cancel()
            self.armed = None
        if not self.catalogue.wanted():
            return
        self.armed = self.timer(max(atLeast, self.nextDue()), self.wake)
        self.armed.daemon = True
        self.armed.start()

    def nextDue(self):
        """Seconds until some enabled portal is due a crawl or refresh (at least 1)."""
        now = self.clock()
        waits = [REFRESH_AGE]
        for portal in self.catalogue.portals():
            if now < self.retryAt.get(portal, 0):
                waits.append(self.retryAt[portal] - now)
                continue
            state = self.index.refreshState(portal)
            if state is None or state["lastRefresh"] is None:
                waits.append(0)
            else:
                waits.append(state["lastRefresh"] + REFRESH_AGE - now)
                waits.append(nextFull(state["lastFull"] or state["lastRefresh"]) - now)
        return max(1, min(waits))

    def due(self, portal):
        """What a portal needs now: "first" (never indexed), "full", "incremental", or None."""
        if self.clock() < self.retryAt.get(portal, 0):
            return None
        state = self.index.refreshState(portal)
        if state is None or state["lastRefresh"] is None:
            return "first"
        if self.clock() >= nextFull(state["lastFull"] or state["lastRefresh"]):
            return "full"
        if self.clock() - state["lastRefresh"] >= REFRESH_AGE:
            return "incremental"
        return None

    def crawl(self):
        """Do whatever each enabled portal is due, one portal at a time. Stops early
        (keeping what it has) when every Account's On Demand is switched off."""
        self.requests = 0
        if not self.catalogue.wanted():
            return
        jobs = {}
        for portal, name in self.catalogue.portals().items():
            job = self.due(portal)
            if job:
                jobs[portal] = (name, job)
        # A portal waiting its turn for its first crawl is indexing too, not failed. A first
        # crawl that was paused (every Account off, or a restart) keeps its place.
        for portal, (name, job) in jobs.items():
            if job == "first":
                state = self.index.refreshState(portal)
                paused = state is not None and state["status"] == "indexing"
                self.index.setStatus(portal, "indexing", pagesDone=None if paused else 0)
        for portal, (name, job) in jobs.items():
            if not self.catalogue.wanted():
                return
            try:
                self.refresh(portal, name, job)
            except sqlite3.DatabaseError as e:
                if not damaged(e):
                    raise
                # The file is a disposable cache: start it again, and crawl it afresh.
                logger.error("On Demand index damaged ({}), starting it again".format(e))
                self.index.recreate()
                self.retryAt.clear()
                return

    def request(self, call, *args):
        if self.requests:
            self.sleep(self.interval)
        self.requests += 1
        return call(*args)

    def refresh(self, portal, name, job):
        first, full = job == "first", job != "incremental"
        logger.info("On Demand: {} {}".format("indexing" if first else "refreshing", name))
        state = self.index.refreshState(portal)
        # A paused first crawl goes on from its last page (again: new items push pages down).
        start = max(1, state["pagesDone"]) if first and state is not None else 1
        movies = self.listing(portal, "vod", first, full, start)
        if movies in ("failed", "paused", "gone"):
            return self.stopped(portal, name, movies, "the Movie listing failed")
        # Only Xtream-family portals answer type=series; on Infomir it's no categories.
        series = self.listing(portal, "series", False, full)
        if series in ("failed", "paused", "gone"):
            return self.stopped(portal, name, series, "the Series listing failed")
        # The Xtream paging bug (type=series page 2 repeats page 1) leaves the index short.
        # A full crawl finds out afresh; an incremental pull rarely reaches page 2.
        partial = series == "repeated" or (not full and state is not None and state["partial"])
        now = int(self.clock())
        self.retryAt.pop(portal, None)
        self.index.setStatus(portal, "partial" if partial else "ready", lastRefresh=now,
                             lastFull=now if full else None, partial=partial)
        logger.info("On Demand: {} {}{}".format(name, "indexed" if first else "refreshed",
                                                 " (Series cut short by the portal)" if partial else ""))

    def stopped(self, portal, name, why, failure):
        if why == "failed":
            self.fail(portal, name, failure)
        elif why == "paused":
            logger.info("On Demand: {} paused, no Account has On Demand on".format(name))
        else:
            logger.info("On Demand: {} stopped, the portal is gone or switched off".format(name))

    def listing(self, portal, source, first, full, start=1):
        """Pull one of the portal's listings (type=source), newest first, into the index.

        A full pull walks every page, then drops what it no longer lists; an incremental
        one ends at the first page with nothing new or changed. A pull from a `start` past
        page 1 (a paused first crawl going on) drops nothing. Returns "done",
        "repeated" (a page repeated the last, so the walk stopped there), "skipped"
        (type=series not answered), "paused", "gone" (the portal was deleted or switched
        off meanwhile: nothing more is written for it) or "failed".
        """
        categories = self.request(self.catalogue.categories, portal, source)
        if portal not in self.catalogue.portals():
            return "gone"
        if categories is None:
            return "skipped" if source == "series" else "failed"
        self.index.setCategories(portal, categories, source)
        page, pages, previous = start, None, None
        seen, end = set(), "done"
        while True:
            if not self.catalogue.wanted():
                return "paused"
            result = self.request(self.catalogue.page, portal, page, source)
            if portal not in self.catalogue.portals():
                return "gone"
            if result is None:
                return "failed"
            ids = [str(row.get("id")) for row in result["items"]]
            if not ids:
                break
            # A repeat of the last page is a portal ignoring p=: stop there.
            if ids == previous:
                end = "repeated"
                break
            if result["pageSize"] and result["total"]:
                pages = -(-result["total"] // result["pageSize"])
            indexIds = [indexId(id, source) for id in ids]
            seen.update(indexIds)
            known = {} if full else self.index.addedOf(portal, indexIds)
            fresh = [row for id, row in zip(indexIds, result["items"])
                     if known.get(id) != str(row.get("added") or "")]
            self.index.addItems(portal, result["items"], source)
            if first:
                self.index.setStatus(portal, "indexing", pagesDone=page, pagesTotal=pages)
            # A Series' added moves when it gains an Episode, so it counts as changed.
            if not full and not fresh:
                break
            if pages is not None and page >= pages:
                break
            page, previous = page + 1, ids
        if full and end == "done" and start == 1:
            dropped = self.index.keepOnly(portal, seen, source)
            if dropped:
                logger.info("On Demand: {} no longer lists {} items".format(portal, dropped))
        return end

    def fail(self, portal, name, why):
        """A portal never indexed reads failed; one indexed before keeps its last good index
        and reads stale. Either way it is tried again after RETRY_AGE."""
        state = self.index.refreshState(portal)
        stale = state is not None and state["lastRefresh"] is not None
        logger.error("On Demand: couldn't {} {} ({}), retrying in {} s".format(
            "refresh" if stale else "index", name, why, RETRY_AGE))
        self.index.setStatus(portal, "stale" if stale else "failed")
        self.retryAt[portal] = self.clock() + RETRY_AGE
