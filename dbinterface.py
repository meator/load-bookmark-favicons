"""Interface between Chromium's sqlite database and the python program.

DBInterface's methods should be used in this order:
1)   Call get_icon_mappings() to get all website URLs which are already saved
     and which do not require further action.
1.5) Get all website URLs and filter out mappings that we got in the previous
     step. Query favicon URLs of filtered website URLs.
2)   Call merge_existing_icons() with the filtered mapping we got from the
     previous step. Save the return value and use it in next steps.
2.5) Fetch favicon images of links we got in the previous step.
3)   Call add_new_icons() with mapping we got in the previous step.
4)   Call merge_existing_icons() with the rest of the website and favicon URLs.
     merge_existing_icons() should now return an empty list because all
     favicons should already be present in the database.

Following these instructions will guarantee that no data which is already saved
in the database would have to be fetched again. Almost every step filters out
some links.

The step 1.5 (filtering website URLs using get_icon_mappings()) is also
important because merge_existing_icons() mustn't be provided with website URLs
that are in the list.
"""

import sqlite3
import contextlib
from collections import abc

from base_types import *
import icon

_database_version = 8


def get_database_version() -> int:
    """Get the version od Favicon database required by DBInterface."""
    return _database_version


class IncompatibleVersionError(Exception):
    """Exception raised by DBInterface.

    This is raised when working with a database whose version doesn't match
    get_database_version().
    """


class LockedDatabaseError(Exception):
    """Exception raised by DBInterface.

    This is raised when the database file is locked and can't be accessed. This
    happens when Favicons file is accessed while Chromium is running.
    """


def _populate_temporary_table(
    cur: sqlite3.Cursor, icon_map: dict[website_url, favicon_url]
) -> None:
    """Create a temporary table favicon_query containing new entries."""

    cur.execute(
        "CREATE TEMPORARY TABLE favicon_query(favicon_url TEXT NOT NULL, "
        "website_url TEXT NOT NULL)"
    )
    # This swaps key and value and inserts it into the temporary table.
    cur.executemany(
        "INSERT INTO favicon_query VALUES(?, ?)",
        ((v, k) for k, v in icon_map.items()),
    )


def _check_icon_mapping_collision(cur: sqlite3.Cursor) -> None:
    """Check that new entries don't contain entries in icon_mapping.

    This ensures that no new entry (in favicon_query) contains an URL that is
    already in icon_mapping (or in get_icon_mappings()). URLs in icon_mapping
    are already fully handled and require no further action.
    """

    check = cur.execute(
        "SELECT COUNT(*) FROM icon_mapping AS map INNER JOIN favicon_query "
        "AS search ON map.page_url = search.website_url"
    )
    if check.fetchone()[0] != 0:
        raise ValueError(
            "Tried to merge website URL which is already in the database."
        )


def _get_id(cur: sqlite3.Cursor, id: str, table: str) -> int:
    """Get the next id from table.

    Args:
        cur: Databse cursor.
        id: Column containing id.
        table: Table to get id from.

    Returns:
        Id.
    """

    # Don't do SQL injection attacks here.
    data = cur.execute(f"SELECT MAX({id}) FROM {table}").fetchone()[0]
    if data is None:
        return 1
    else:
        # We don't want to overwrite the last entry.
        return data + 1


def _add_saved_icon_mappings(
    readcur: sqlite3.Cursor, writecur: sqlite3.Cursor
) -> None:
    """Add all mappings which have a saved icon into the database."""

    idnum = _get_id(readcur, "id", "icon_mapping")

    # Select all website URLs whose favicon is already marked in the
    # favicons table. url in favicons must be unique so all mathing entries
    # will be selected only once.
    found = readcur.execute(
        "SELECT search.website_url, fav.id FROM favicons AS fav "
        "INNER JOIN favicon_query AS search ON fav.url = search.favicon_url"
    )

    # This makes the type checker happy.
    url: str
    id: int
    # Add mappings from website URLs to favicon URLs which are already
    # present in the database.
    record: tuple[str, int]
    for record in iter(found.fetchone, None):
        # This makes the type checker happy.
        assert record is not None
        url, id = record
        writecur.execute(
            "INSERT INTO icon_mapping VALUES(?, ?, ?)", (idnum, url, id)
        )
        idnum += 1


def _return_unsaved_entries(cur: sqlite3.Cursor) -> list[website_url]:
    """Return all new favicon mappings which don't have a saved favicon."""

    not_found = cur.execute(
        "SELECT website_url, favicon_url FROM favicon_query "
        "WHERE favicon_url NOT IN (SELECT url FROM favicons)"
    )

    return [row[0] for row in not_found.fetchall()]


# Chromium stores all relevant data in the Favicons SQLite database. It
# contains three important things: website URL, corresponding favicon URL and
# the favicon image itself.


class DBInterface(contextlib.AbstractContextManager):
    """Interface between Chromium's Favicon database and Python."""

    def __init__(self, path: str, in_memory: bool = False):
        """Initialize DBInterface.

        Args:
            path: Path to the Favicon file.
            in_memory: If true, load the database path into memory. All changes
              will be done in memory and will not be saved to path. Useful for
              unit testing.

        Raises:
            IncompatibleVersionError: If path's and DBInterface's database
              version mismatch. DBInterface's supported database version can
              be queried using get_database_version().
            LockedDatabaseError: If the database is locked.
        """

        if in_memory:
            origdb = sqlite3.connect(path)
            newdb = sqlite3.connect(":memory:")
            origdb.backup(newdb)
            origdb.close()

            self._db = newdb
        else:
            self._db = sqlite3.connect(path, isolation_level="EXCLUSIVE")

        # This cursor is intended for all write operations to the database (and
        # for basic querying). It is committed at the very end of DBInterface's
        # operation.
        cur = self._db.cursor()
        self._cur = cur

        # Try to make a request. This should fail if Chromium is running.
        try:
            res = cur.execute("SELECT value FROM meta WHERE key = 'version'")
        except sqlite3.OperationalError as exc:
            raise LockedDatabaseError("Database is locked.") from exc
        version = int(res.fetchone()[0])

        compatible_version = get_database_version()
        if version != compatible_version:
            raise IncompatibleVersionError(
                f"Database version {version} is incompatible with "
                f"{compatible_version}"
            )

    def get_icon_mappings(self) -> set[website_url]:
        """Get all saved icon mappings.

        This returns all website URLs which are already saved in the database.
        There is no need to do any operations (querying and fetching their
        favicon) on these URLs.

        Returns:
            All icon mappings that are already saved in the database.
        """

        cur = self._cur
        res = cur.execute("SELECT page_url FROM icon_mapping")
        return {x[0] for x in res.fetchall()}

    def merge_existing_icons(
        self, icon_map: dict[website_url, favicon_url]
    ) -> list[website_url]:
        """Merge all favicon mappings into the database.

        This method adds all website URLs which already have a favicon image
        saved in the database and returns the rest of website URLs.

        Website URLs present in get_icon_mappings() must not be in icon_map.

        Args:
            icon_map: A dictionary whose key is website URL and whose value is
              key's favicon URL.

        Raises:
            ValueError: If icon_map.keys() contains url listed in
              get_icon_mappings().

        Returns:
            URLs of websites in icon_map which do not have a saved icon in the
            database. It returns all the entries merge_existing_icons() didn't
            merge.
        """

        cur = self._cur
        _populate_temporary_table(cur, icon_map)
        _check_icon_mapping_collision(cur)

        # We need a second cursor to both read and write to the database at
        # once.
        readcur = self._db.cursor()
        _add_saved_icon_mappings(readcur, cur)
        readcur.close()

        not_found = _return_unsaved_entries(cur)
        cur.execute("DROP TABLE favicon_query")
        return not_found

    def add_new_icons(
        self, icons: abc.Iterable[tuple[favicon_url, icon.IconPair]]
    ) -> None:
        """Add new icons to the database.

        This adds favicon bitmaps to the database. It doesn't change
        icon_mapping, merge_existing_icons() should be called after this
        function.

        icons musn't contain duplicate favicon URLs.

        Args:
            icons: An iterable of tuples. The first member of the tuple should
              contain the URL of the favicon. The second member should contain
              favicons themselves.

        Raises:
            ValueError: If icons contain duplicate entries.
        """

        if len(list(icons)) != len({item[0] for item in icons}):
            raise ValueError("Tried to add an icon more than once.")

        cur = self._cur
        # Get next IDs.
        favicons_id = _get_id(cur, "id", "favicons")
        bitmaps_id = _get_id(cur, "id", "favicon_bitmaps")
        # Insert an entry into favicons and insert two icons per entry.
        for url, icon in icons:
            cur.execute(
                "INSERT INTO favicons VALUES(?, ?, 1)", (favicons_id, url)
            )
            cur.execute(
                "INSERT INTO favicon_bitmaps VALUES(?, ?, 0, ?, 16, 16, 0)",
                (bitmaps_id, favicons_id, icon.x16),
            )
            bitmaps_id += 1
            cur.execute(
                "INSERT INTO favicon_bitmaps VALUES(?, ?, 0, ?, 32, 32, 0)",
                (bitmaps_id, favicons_id, icon.x32),
            )
            bitmaps_id += 1
            favicons_id += 1

    def close(self) -> None:
        """Close the database connection.

        Do not use DBInterface's methods after close() has been called.
        """

        self._cur.close()
        self._db.commit()
        self._db.close()

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Deinitialize DBInterface.

        Calls self.close(). All arguments are ignored.

        Returns:
            False.
        """

        self.close()
        return None
