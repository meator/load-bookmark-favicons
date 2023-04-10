import unittest
import sqlite3

import icon
import dbinterface
import check_database


def get_icon(path: str) -> bytes:
    """Read and return data in path."""
    with open(path, "rb") as f:
        return f.read()


class DBInterfaceTest(unittest.TestCase):
    def test_db_state(self):
        db = dbinterface.DBInterface("tests/sample-data/Favicons")
        self.assertCountEqual(
            db.get_icon_mappings(),
            ["https://github.com/", "https://stackoverflow.com/"],
        )
        db.close()

    def test_empty_database(self):
        db = dbinterface.DBInterface("tests/sample-data/Favicons-empty", True)

        self.assertEqual(db.get_icon_mappings(), set())
        new_mappings = {
            "https://facebook.com/": "https://static.xx.fbcdn.net/rsrc.php/yb/r/hLRJ1GG_y0J.ico",
            "https://www.youtube.com/": "https://www.youtube.com/s/desktop/b95ddd88/img/favicon_32x32.png",
        }
        self.assertCountEqual(
            db.merge_existing_icons(new_mappings), new_mappings.keys()
        )

        x16 = get_icon("tests/sample-data/facebook16.png")
        x32 = get_icon("tests/sample-data/facebook32.png")

        new_icon = icon.IconPair(x16, x32)

        db.add_new_icons(
            [
                (
                    "https://static.xx.fbcdn.net/rsrc.php/yb/r/hLRJ1GG_y0J.ico",
                    new_icon,
                )
            ]
        )
        self.assertCountEqual(
            db.merge_existing_icons(new_mappings), ["https://www.youtube.com/"]
        )
        self.assertCountEqual(db.get_icon_mappings(), ["https://facebook.com/"])
        db.close()

    def test_merging_icons(self):
        db = dbinterface.DBInterface("tests/sample-data/Favicons", True)
        # Add some nonexisting icons and newgithub.com which has the same icon
        # as github.com and therefore should be added to the mapping.
        new_mappings = {
            "https://newgithub.com/": "https://github.githubassets.com/favicons/favicon-dark.svg",
            "https://facebook.com/": "https://static.xx.fbcdn.net/rsrc.php/yb/r/hLRJ1GG_y0J.ico",
            "https://www.youtube.com/": "https://www.youtube.com/s/desktop/b95ddd88/img/favicon_32x32.png",
        }
        result = db.merge_existing_icons(new_mappings)
        self.assertCountEqual(
            result, ["https://facebook.com/", "https://www.youtube.com/"]
        )
        updated = db.get_icon_mappings()
        self.assertCountEqual(
            updated,
            [
                "https://github.com/",
                "https://stackoverflow.com/",
                "https://newgithub.com/",
            ],
        )
        db.close()

    def test_complete_merge(self):
        # Test that merging entries that all have a corresponding favicon in
        # the database works.
        db = dbinterface.DBInterface("tests/sample-data/Favicons", True)

        new_mappings = {
            "https://newgithub.com/": "https://github.githubassets.com/favicons/favicon-dark.svg",
        }
        self.assertEqual(db.merge_existing_icons(new_mappings), [])
        self.assertCountEqual(
            db.get_icon_mappings(),
            [
                "https://github.com/",
                "https://stackoverflow.com/",
                "https://newgithub.com/",
            ],
        )
        db.close()

    def test_adding_icons(self):
        db = dbinterface.DBInterface("tests/sample-data/Favicons", True)

        x16 = get_icon("tests/sample-data/facebook16.png")
        x32 = get_icon("tests/sample-data/facebook32.png")

        new_icon = icon.IconPair(x16, x32)
        new_mappings = {
            "https://facebook.com/": "https://static.xx.fbcdn.net/rsrc.php/yb/r/hLRJ1GG_y0J.ico"
        }

        old_mapping = db.get_icon_mappings()

        # Here we want to add facebook to mappings but there isn't an actual
        # icon saved in the database so it should just skip it and return it.
        not_handled = db.merge_existing_icons(new_mappings)
        self.assertCountEqual(not_handled, ["https://facebook.com/"])
        # The mapping should be the same since nothing should have changed.
        self.assertEqual(old_mapping, db.get_icon_mappings())

        db.add_new_icons(
            (
                (
                    "https://static.xx.fbcdn.net/rsrc.php/yb/r/hLRJ1GG_y0J.ico",
                    new_icon,
                ),
            )
        )

        # We have a icon for facebook.com, merge should return no leftovers.
        not_handled = db.merge_existing_icons(new_mappings)
        self.assertEqual(not_handled, [])
        updated_mapping = db.get_icon_mappings()
        self.assertCountEqual(
            updated_mapping,
            [
                "https://github.com/",
                "https://stackoverflow.com/",
                "https://facebook.com/",
            ],
        )

        db.close()

    def test_adding_duplicate_icons(self):
        db = dbinterface.DBInterface("tests/sample-data/Favicons", True)

        x16 = get_icon("tests/sample-data/facebook16.png")
        x32 = get_icon("tests/sample-data/facebook32.png")

        new_icon = icon.IconPair(x16, x32)

        to_add = [
            ("https://example.com/", new_icon),
            ("https://example.com/", new_icon),
        ]
        self.assertRaises(ValueError, db.add_new_icons, to_add)

        db.close()

    def test_old_db(self):
        # This database hasn't been actually created by an older version of
        # chromium, the database's version isn't actually 7, it is just faked
        # for testing purposes.
        self.assertRaises(
            dbinterface.IncompatibleVersionError,
            dbinterface.DBInterface,
            "tests/sample-data/Favicons-old",
        )

    def test_correct_database_version(self):
        result = dbinterface.get_database_version()
        self.assertIsInstance(result, int)
        self.assertGreater(result, 0)

    def test_concurrent_access(self):
        # This simulates a situation where DBInterface tries to work with
        # Favicons but Chromium is running and has locked the database.
        chromium = sqlite3.connect(
            "tests/sample-data/Favicons", isolation_level="EXCLUSIVE"
        )
        # Lock the database in here.
        con = chromium.execute("BEGIN EXCLUSIVE")

        self.assertRaises(
            dbinterface.LockedDatabaseError,
            dbinterface.DBInterface,
            "tests/sample-data/Favicons",
        )
        con.close()
        chromium.close()

    def test_merging_present_entries(self):
        # stackoverflow is in get_icon_mappings() and therefore merge is invalid.
        new_mappings = {
            "https://newgithub.com/": "https://github.githubassets.com/favicons/favicon-dark.svg",
            "https://stackoverflow.com/": "https://static.xx.fbcdn.net/rsrc.php/yb/r/hLRJ1GG_y0J.ico",
        }

        db = dbinterface.DBInterface("tests/sample-data/Favicons", True)
        self.assertRaises(ValueError, db.merge_existing_icons, new_mappings)
        db.close()

    def test_adding_multiple_entries_with_same_favicon(self):
        db = dbinterface.DBInterface("tests/sample-data/Favicons", True)

        # Two new entries with same favicon will be added.
        new = {
            "https://githubone.com/": "https://github.githubassets.com/favicons/favicon-dark.svg",
            "https://githubtwo.com/": "https://github.githubassets.com/favicons/favicon-dark.svg",
        }
        result = db.merge_existing_icons(new)
        self.assertEqual(result, [])
        self.assertCountEqual(
            db.get_icon_mappings(),
            [
                "https://github.com/",
                "https://stackoverflow.com/",
                "https://githubone.com/",
                "https://githubtwo.com/",
            ],
        )
        db.close()
