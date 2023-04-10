#!/usr/bin/env python3

"""A program for fetching all favicons of all bookmakrs.

This program is compatible with Chromium and Google Chrome. It finds all
bookmarks which don't have a saved favicon and then downloads it.
"""

import argparse
import tqdm
import tqdm.contrib.logging
import tqdm.contrib
import logging
import sys
import os
import requests
import urllib.parse
from collections.abc import Iterable
import contextlib

import magic

import bookmarks
import dbinterface
import get_favicon_url
import icon
from base_types import *


class NullStream:
    """Helper class to provide a null stream."""

    def write(self, s):
        pass


def query_favicons(
    bookmarks: Iterable[website_url], timeout: float | None, interactive: bool
) -> dict[website_url, favicon_url]:
    """Try to query all favicon URLs with a nice progress bar.

    Args:
        bookmarks: List of links to retrieve favicon URLs for.
        timeout: Request timeout.
        interactive: If True use tqdm.

    Returns:
        A dictionary whose keys are bookmarks and whose values are their
        favicon links and their type.
    """

    result = {}
    iterator: Iterable[website_url] | tqdm.tqdm[website_url]
    log: tqdm.tqdm[website_url] | NullStream
    if interactive:
        iterator = tqdm.tqdm(bookmarks, "Querying favicons")
        log = iterator
    else:
        iterator = bookmarks
        log = NullStream()

    for link in iterator:
        try:
            favicon = get_favicon_url.get_favicon_url(link, timeout)
        except get_favicon_url.UnknownSchemeError:
            log.write(f"warning: {link}: Unknown scheme, skipping...")
        except get_favicon_url.TimedOutError:
            log.write(f"warning: {link}: Timed out, skipping...")
        else:
            if favicon is None:
                log.write(f"info: {link}: No favicon found, skipping...")
            else:
                result[link] = favicon
    return result


def fetch_favicons(
    favicons: Iterable[favicon_url], timeout: float | None, interactive: bool
) -> list[tuple[favicon_url, bytes]]:
    """Fetch favicons with a nice progress bar.

    Args:
        favicons: An iterable of favicon URLs to try to fetch.
        timeout: Request timeout.
        interactive: If True use tqdm.

    Returns:
        It returns favicon URLs with their favicon. Not all favicons have to
        be processed. The returned list can be shorter than the input iterable.
        This is mainly caused by trying to download nonexistant favicons.
    """

    result = []
    iterator: Iterable[favicon_url] | tqdm.tqdm[favicon_url]
    log: tqdm.tqdm[favicon_url] | NullStream
    if interactive:
        iterator = tqdm.tqdm(favicons, "Fetching favicons")
        log = iterator
    else:
        iterator = favicons
        log = NullStream()

    for link in iterator:
        url = urllib.parse.urlparse(link)
        if url.scheme == "file":
            try:
                with open(url.path, "rb") as f:
                    image = f.read()
            except OSError:
                log.write(f"info: {link}: Couldn't access file, skipping...")
            else:
                result.append((link, image))
        else:
            try:
                with requests.get(link, timeout=timeout) as req:
                    req.raise_for_status()
                    image = req.content
            except requests.Timeout:
                log.write(f"info: {link}: Request timed out, skipping...")
            except (requests.ConnectionError, requests.HTTPError):
                log.write(f"info: {link}: Request failed, skipping...")
            else:
                result.append((link, image))
    return result


favicon_data_type = tuple[favicon_url, bytes]


def convert_favicon_images(
    favicons: Iterable[favicon_data_type], interactive: bool
) -> list[tuple[favicon_url, icon.IconPair]]:
    """Convert all raw favicon images to icon.IconPair

    Args:
        favicons: Dict of website links, favicon links and the raw images.
        interactive: If True use tqdm.

    Returns:
        A copy of favicons iterable with bytes converted to icon.IconPair.
    """

    result = []
    iterator: Iterable[favicon_data_type] | tqdm.tqdm[favicon_data_type]
    log: tqdm.tqdm[favicon_data_type] | NullStream
    if interactive:
        iterator = tqdm.tqdm(favicons, "Converting favicons")
        log = iterator
    else:
        iterator = favicons
        log = NullStream()

    for website, raw_image in favicons:
        filetype = magic.from_buffer(raw_image, True)
        # MIME type might contain additional information after ;. This check
        # might not be necessary. Checking if favicon_url ends in .ico is
        # possible but using magic should be bullet proof.
        filetype = filetype.split(";", 1)[0]
        try:
            match filetype:
                case "image/vnd.microsoft.icon" | "image/x-icon":
                    result.append(
                        (website, icon.IconPair.create_from_ico(raw_image))
                    )
                case "image/svg+xml":
                    result.append(
                        (website, icon.IconPair.create_from_svg(raw_image))
                    )
                case _:
                    result.append(
                        (website, icon.IconPair.create_from_image(raw_image))
                    )
        except icon.UnidentifiedImageError:
            log.write(
                f"warning: {website}: Couldn't identify image, skipping..."
            )
    return result


def _setup_logger(
    name: str, level: int, handler: logging.Handler
) -> logging.Logger:
    """Set up a logger."""

    log = logging.getLogger(name)
    log.addHandler(handler)
    log.setLevel(level)
    return log


def setup_logging(verbosity: int) -> list[logging.Logger]:
    """Set up logging for submodules."""

    errhandler: logging.FileHandler | logging.StreamHandler
    if verbosity > 0:
        errhandler = logging.StreamHandler(sys.stderr)

        level = logging.INFO if verbosity == 1 else logging.DEBUG

        bookmarks_log = _setup_logger("bookmarks", level, errhandler)
        get_favicon_url_log = _setup_logger(
            "get_favicon_url", level, errhandler
        )
        return [bookmarks_log, get_favicon_url_log]
    else:
        return []


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "-v",
        "--verbose",
        action="count",
        help="Be more verbose (can be specified multiple times)",
        default=0,
    )
    group.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Surpress informational output",
    )
    parser.add_argument(
        "-t",
        "--timeout",
        type=float,
        help="Timeout of remote requests in seconds. Set to 0 to disable "
        "timeout. (default: %(default)s)",
        default=10,
    )
    parser.add_argument("BOOKMARKS_FILE", help="Path to the Bookmarks file.")
    parser.add_argument("FAVICONS_FILE", help="Path to the Favicons file.")
    args = parser.parse_args()

    if not os.access(args.BOOKMARKS_FILE, os.F_OK):
        print(
            f"Bookmarks file '{args.BOOKMARKS_FILE}' isn't accessible!",
            file=sys.stderr,
        )
        sys.exit(1)
    if not os.access(args.FAVICONS_FILE, os.F_OK):
        print(
            f"Favicons file '{args.FAVICONS_FILE}' isn't accessible!",
            file=sys.stderr,
        )
        sys.exit(1)

    timeout = None if args.timeout == 0 else args.timeout
    interactive = not args.quiet

    loggers = setup_logging(args.verbose)

    try:
        with open(args.BOOKMARKS_FILE) as f:
            bookmark_links = bookmarks.get_all_bookmarks(f)
    except OSError:
        print(
            f"Couldn't access bookmarks file '{args.BOOKMARKS_FILE}'!",
            file=sys.stderr,
        )
        sys.exit(1)
    except bookmarks.IncompatibleBookmarksError:
        print(
            "Your browser's bookmarks are incompatible with "
            "load_bookmark_favicons!",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        with dbinterface.DBInterface(
            args.FAVICONS_FILE
        ) as db, tqdm.contrib.logging.logging_redirect_tqdm(
            loggers
        ) if interactive else contextlib.nullcontext():
            # These are all website URLs that aren't already in db.
            filtered_bookmarks = set(bookmark_links) - db.get_icon_mappings()

            # This dict maps website URL to its favicon URL (and its type).
            favicon_mapping = query_favicons(
                filtered_bookmarks, timeout, interactive
            )

            # List of website URLs that aren't in the db.
            filtered_links = set(db.merge_existing_icons(favicon_mapping))
            # This contains all favicon links with their data that aren't
            # already present in the database. We must fetch these favicons.
            filtered_mapping = {
                k: v for k, v in favicon_mapping.items() if k in filtered_links
            }

            favicon_raw_images = fetch_favicons(
                set(filtered_mapping.values()), timeout, interactive
            )

            favicon_images = convert_favicon_images(
                favicon_raw_images, interactive
            )
            db.add_new_icons(favicon_images)
            db.merge_existing_icons(filtered_mapping)
    except dbinterface.LockedDatabaseError:
        print(
            "Couldn't access the database. load_bookmark_favicons can not run "
            "at the same time as the browser. Please close the browser.",
            file=sys.stderr,
        )
        sys.exit(1)
    except dbinterface.IncompatibleVersionError:
        print(
            "Your browser is too old! load_bookmark_favicons can not function.",
            file=sys.stderr,
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
