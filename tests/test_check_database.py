import unittest
import sqlite3

import check_database


class DBCheckTest(unittest.TestCase):
    def test_correct_database(self):
        db = sqlite3.connect("tests/sample-data/Valid_favicon_database.db")
        self.assertTrue(check_database.checkdb(db))
        db.close()

    def test_faulty_databases(self):
        # Each of these SQL expressions should break the database in some way.
        corrupt_database = [
            # Drop an entire table
            "DROP TABLE icon_mapping",
            # Overwrite meta records with junk
            "UPDATE meta SET value = -5 WHERE key = 'version'",
            "UPDATE meta SET value = 'Not a number.' WHERE key = 'last_compatible_version'",
            # Sneak in NULLs in random places
            "UPDATE favicon_bitmaps SET image_data = NULL WHERE id = 11",
            "UPDATE favicons SET icon_type = NULL WHERE id = 2",
            "UPDATE icon_mapping SET icon_id = NULL",
            "UPDATE meta SET value = NULL WHERE key = 'last_compatible_version'",
            # Break the parity of favicon_bitmaps + favocons + icon_mapping
            "DELETE FROM favicons WHERE id = 2",
            "INSERT INTO favicons VALUES(7, 'https://example.com/', 1)",
            "DELETE FROM favicon_bitmaps WHERE id = 10",
            "INSERT INTO favicon_bitmaps VALUES(13, 5, 0, 0, 16, 16, 0)",
            "INSERT INTO favicon_bitmaps VALUES(13, 7, 0, 0, 16, 16, 0)",
            "DELETE FROM favicon_bitmaps WHERE icon_id = 4",
            "INSERT INTO icon_mapping VALUES(9, 'https://example.com/', 7)",
            # Make favicons with wrong dimensions
            [
                "INSERT INTO favicon_bitmaps VALUES(13, 7, 0, 0, 15, 15, 0)",
                "INSERT INTO favicon_bitmaps VALUES(14, 7, 0, 0, 31, 31, 0)",
            ],
            "UPDATE favicon_bitmaps SET height = 33 WHERE id = 8",
            "UPDATE favicon_bitmaps SET width = 8565648546 WHERE id = 4",
        ]

        orig = sqlite3.connect("tests/sample-data/Valid_favicon_database.db")
        for line in corrupt_database:
            # Start with a fresh copy of orig for each statement in
            # corrupt_database
            db = sqlite3.connect(":memory:")
            orig.backup(db)

            # Some tests must execute multiple SQL statements to thoroughly break
            # the database.
            if isinstance(line, list):
                for command in line:
                    db.execute(command)
            else:
                db.execute(line)
            self.assertFalse(check_database.checkdb(db))
            db.close()
        orig.close()
