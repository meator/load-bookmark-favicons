#!/usr/bin/env python3
"""Tool for checking the validity of Favicons database.

This tool is meant for debugging load-bookmark-favicons. It can be used to
check if the database was corrupted by load_bookmark_favicons.py (which
hopefully shouldn't happen).
"""

import argparse
import sqlite3
import os
import sys
import logging
from collections.abc import Collection
import math

log = logging.getLogger(__name__)
log.addHandler(logging.NullHandler())

# Helper functions


def _print_list(entries: Collection) -> None:
    """Print a list nicely.

    args:
        entries: The list to print.
    """

    if len(entries) < 1:
        return
    # Get the maximum length of size. Add two to count for the ending ")" and
    # for the last number.
    alignment = int(math.log10(len(entries))) + 2
    for num, i in enumerate(entries, 1):
        log.info("%s %s", (str(num) + ")").ljust(alignment), i)


def _check_uniqueness(cur: sqlite3.Cursor, table: str, field: str) -> bool:
    """Check whether all entries in field in table are unique.

    Args:
        cur: sqlite3 cursor to use for checking.
        table: Table whose field should be checked.
        field: Field to check.

    Returns:
        True if field is unique, False otherwise.
    """

    # Please don't do SQL injection attacks here. (It's impossible to use ?
    # substitution in this context.)
    cur.execute(f"SELECT * FROM {table} GROUP BY {field} HAVING COUNT(*) > 1")

    entries = cur.fetchall()
    if entries:
        log.error(
            "Database has %d duplicate records in '%s'!", len(entries), table
        )

        log.info("Listing defective entries:")
        _print_list(entries)
        return False
    return True


def _check_null_in_table(cur: sqlite3.Cursor, table: str) -> bool:
    """Check that table don't contain NULL.

    Args:
        cur: sqlite3 cursor to use for checking.
        table: Table to check.

    Returns:
        True if all entries don't contain NULL, False otherwise.
    """

    # Get all columns in table.
    cur.execute("SELECT name FROM pragma_table_info(?)", (table,))
    columns = [column[0] for column in cur.fetchall()]

    # Again please don't do an SQL injection attack here.
    # This should look like this:
    # column1 IS NULL OR column2 IS NULL OR column3 IS NULL
    condition = " OR ".join([column + " IS NULL" for column in columns])

    cur.execute(f"SELECT * FROM {table} WHERE {condition}")
    entries = cur.fetchall()
    if entries:
        log.error(
            "Found %s records containing NULL in table %s!", len(entries), table
        )
        log.info("Listing defective entries:")
        _print_list(entries)
        return False
    return True


# All these functions return true when no errors are found and false otherwise.


def _check_tables(cur: sqlite3.Cursor) -> bool:
    """Check that the database contains all tables."""

    cur.execute("SELECT name FROM sqlite_schema WHERE type = 'table'")
    found_tables = {x[0] for x in cur.fetchall()}
    check_tables = {"meta", "icon_mapping", "favicons", "favicon_bitmaps"}
    if found_tables != check_tables:
        log.error("Database is missing tables!")
        log.info("Expected: %s", check_tables)
        log.info("Found: %s", found_tables)
        return False
    return True


def _check_nulls(cur: sqlite3.Cursor) -> bool:
    """Check that no record contains NULL."""

    for table in ("meta", "icon_mapping", "favicons", "favicon_bitmaps"):
        if not _check_null_in_table(cur, table):
            return False
    return True


def _check_meta_validity(cur: sqlite3.Cursor) -> bool:
    """Check the meta table.

    Check that the meta table has all expected records and that records that
    should contain numbers actually contain numbers and that versions are
    non-negative.
    """

    cur.execute("SELECT * FROM meta")
    meta = {key: value for key, value in cur}
    found_meta = meta.keys()
    check_meta = {"mmap_status", "version", "last_compatible_version"}
    if found_meta != check_meta:
        log.error("The table meta has invalid records!")
        log.info("Expected: %s", check_meta)
        log.info("Found: %s", found_meta)
        return False

    # Check that the version are numbers.
    try:
        version = int(meta["version"])
        last_compatible_version = int(meta["last_compatible_version"])
    except ValueError:
        log.error("The table meta has invalid values!")
        log.info("meta.version: %s", meta["version"])
        log.info(
            "meta.last_compatible_version: %s", meta["last_compatible_version"]
        )
        return False

    # Versions should be non-negative.
    if version < 0 or last_compatible_version < 0:
        log.error("The table meta has invalid values!")
        log.info("meta.version: %d", version)
        log.info("meta.last_compatible_version: %d", last_compatible_version)
        return False
    return True


def _check_valid_icon_size(cur: sqlite3.Cursor) -> bool:
    """Check icon sizes of all icons."""

    cur.execute("SELECT * FROM favicon_bitmaps WHERE width != height")
    width_height_mismatch = cur.fetchall()
    if width_height_mismatch:
        log.error(
            "%d record(s) in favicon_bitmaps have non-matching width and "
            "height!",
            len(width_height_mismatch),
        )
        log.info("Listing defective entries:")
        _print_list(width_height_mismatch)
        return False

    cur.execute("SELECT * FROM favicon_bitmaps WHERE width NOT IN (16, 32);")
    wrong_width = cur.fetchall()
    if wrong_width:
        log.error(
            "%d record(s) in favicon_bitmaps have nonstandard dimensions!",
            len(wrong_width),
        )
        log.info("Listing defective entries:")
        _print_list(wrong_width)
        return False
    return True


def _check_correct_number_of_icons_per_entry(cur: sqlite3.Cursor) -> bool:
    """Check that each icon has exactly two favicon bitmaps."""

    cur.execute(
        "SELECT * FROM favicon_bitmaps GROUP BY icon_id HAVING COUNT(*) != 2"
    )
    icon_id_dup = cur.fetchall()
    if icon_id_dup:
        log.error(
            "%d record(s) in favicon_bitmaps have wrong number of icon "
            "mappings!",
            len(icon_id_dup),
        )
        log.info("Listing defective entries:")
        _print_list(icon_id_dup)
        return False
    return True


def _check_favicons_to_favicon_bitmaps_mapping(cur: sqlite3.Cursor) -> bool:
    """Check that each entry in favicons has its entries in favicon_bitmaps."""

    # Check that every favicon has two favicon bitmap entries.
    cur.execute("SELECT COUNT(*) FROM favicons")
    favicon_count = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM favicon_bitmaps")
    favicon_bitmaps_count = cur.fetchone()[0]

    if favicon_count * 2 != favicon_bitmaps_count:
        log.error("Count mismatch between favicons and favicon_bitmaps!")
        log.info("Number of records in favicons: %d", favicon_count)
        log.info(
            "Number of records in favicon_bitmaps: %d", favicon_bitmaps_count
        )
        return False

    # This checks that each favicon entry has two matching favicon bitmap
    # entries. If this is true, the number of joint records should be equal to
    # favicon_bitmaps_count.
    cur.execute(
        "SELECT COUNT(*) FROM (SELECT * FROM favicons INNER JOIN "
        "favicon_bitmaps ON favicon_bitmaps.icon_id = favicons.id)"
    )
    join_count = cur.fetchone()[0]

    if join_count != favicon_bitmaps_count:
        log.error("Unbound favicons are present in database!")
        return False

    cur.execute(
        "SELECT * FROM icon_mapping WHERE "
        "icon_id NOT IN (SELECT id FROM favicons)"
    )
    icon_mapping_unmatched = cur.fetchall()
    if icon_mapping_unmatched:
        log.error(
            "%d icon mapping(s) point to nonexistant favicon!",
            len(icon_mapping_unmatched),
        )
        log.info("Listing defective records:")
        _print_list(icon_mapping_unmatched)
        return False
    return True


def checkdb(db: sqlite3.Connection) -> bool:
    """Perform sanity checking on database.

    This function checks that the Favicon database is not corrupted. It can
    have false negatives.

    This function uses the logger modult to return diagnostics. Error summary
    is reported as ERROR and detailed descriptions are reported as INFO.

    Args:
        db: Database to check.

    Returns:
        True if the database is valid, False otherwise.
    """

    cur = db.cursor()

    if not _check_tables(cur):
        return False

    if not _check_nulls(cur):
        return False

    if not _check_meta_validity(cur):
        return False

    if not _check_uniqueness(cur, "icon_mapping", "page_url"):
        return False
    if not _check_uniqueness(cur, "favicons", "url"):
        return False

    if not _check_valid_icon_size(cur):
        return False

    if not _check_correct_number_of_icons_per_entry(cur):
        return False

    if not _check_favicons_to_favicon_bitmaps_mapping(cur):
        return False
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("FILENAME")
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Produce more verbose output (show actual "
        "corrupted parts of the favicon database)",
    )
    args = parser.parse_args()

    if not os.access(args.FILENAME, os.R_OK):
        print(f"Database '{args.FILENAME}' doesn't exist!", file=sys.stderr)
        sys.exit(1)

    log.addHandler(logging.StreamHandler(sys.stdout))
    if args.verbose:
        log.setLevel(logging.INFO)

    db = sqlite3.connect(args.FILENAME)

    sys.exit(0 if checkdb(db) else 1)

__all__ = ["checkdb"]
