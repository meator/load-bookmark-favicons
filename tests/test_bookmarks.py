import unittest

import bookmarks


class BookmarksTest(unittest.TestCase):
    def test_bookmarks_version(self):
        result = bookmarks.get_bookmarks_version()
        # This only tests that the version is valid, it doesn't make any
        # assumptions about the current version.
        self.assertIsInstance(result, int)
        self.assertGreater(result, 0)

    def test_bookmark_retrieve(self):
        with open("tests/sample-data/Bookmarks") as f:
            result = bookmarks.get_all_bookmarks(f)
        self.assertCountEqual(
            result,
            [
                "https://twitter.com/",
                "https://www.facebook.com/",
                "https://github.com/",
                "https://stackoverflow.com/",
                "https://example.com/",
            ],
        )

    def test_mismatching_bookmark_version(self):
        # This file isn't actually using another format, it just simulates
        # a potential version bump of the Bookmarks file.
        with open("tests/sample-data/Bookmarks-new") as f:
            self.assertRaises(
                bookmarks.IncompatibleBookmarksError,
                bookmarks.get_all_bookmarks,
                f,
            )
