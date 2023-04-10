"""Module for querying all bookmarks from a bookmark file.

This module provides a logger (which is set to NullHandler by default) with the
same name as the module."""

import json
import typing
import logging
from typing import *

from base_types import *

_log = logging.getLogger(__name__)
_log.addHandler(logging.NullHandler())

# Chromium's bookmarks file provides a version number in its "version" key. I
# assume that it will be incremented if any backwards incompatible changes
# occur in the future. This module raises an exception if the version doesn't
# match this module's version just to be sure.
_supported_version = 1


def get_bookmarks_version() -> int:
    """Get the supported version of bookmarks file.

    Returns:
        The version.
    """

    return _supported_version


class IncompatibleBookmarksError(Exception):
    """Exception raised by get_all_bookmarks().

    It is raised when Bookmark file's version doesn't match expected version.
    """


def _list_all_bookmarks(json_input: dict) -> list[website_url]:
    """List all bookmark URLs recursively."""

    result = []
    # Start with the top directories.
    bm_stack = list(json_input["roots"].values())
    # This iterates over all bookmark entries. If it find a folder, it puts it
    # into bm_stack and it will be searced in a next iteration. Else it adds it
    # to the final result.
    while bm_stack:
        current = bm_stack.pop()
        for entry in current["children"]:
            if entry["type"] == "folder":
                bm_stack.append(entry)
            elif entry["type"] == "url":
                result.append(website_url(entry["url"]))
            else:
                # There shouldn't really be any other bookmark types but this
                # can report it just to be sure.
                _log.warn("Unknown bookmark type '%s'.", entry["type"])
    return result


def get_all_bookmarks(bookmark_fp: typing.TextIO) -> list[website_url]:
    """Return URLs of all bookmarks in bookmark_fp.

    Args:
        bookmark_fp: A text IO stream containing Chromium's JSON bookmark data.
          This should correspond to chromium's 'Bookmarks' file.

    Returns:
        A list of bookmark URLs.

    Raises:
        IncompatibleBookmarksError: If bookmark_fp's bookmarks version doesn't
          match get_bookmark_version().
    """

    data = json.load(bookmark_fp)
    supported_version = get_bookmarks_version()
    if data["version"] != supported_version:
        raise IncompatibleBookmarksError(
            f"Bookmark version {data['version']} doesn't match supported "
            f"version {supported_version}."
        )
    return _list_all_bookmarks(data)
