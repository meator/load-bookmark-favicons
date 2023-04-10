import unittest
import os.path
import requests

import get_favicon_url


def get_file_url(path: str) -> str:
    """Convert path to file URL."""

    return "file://" + os.path.abspath(path)


class GetFaviconUrlTest(unittest.TestCase):
    """Test various hand-picked websites and search for their favicon."""

    def test_nonexistant_file(self):
        self.assertIsNone(
            get_favicon_url.get_favicon_url("file:///invalid/file", None)
        )

    def test_example_com(self):
        # This favicon doesn't exist but it isn't get_favicon_url's job to find
        # that out.
        self.assertEqual(
            get_favicon_url.get_favicon_url("https://example.com/", None),
            "https://example.com/favicon.ico",
        )

    def test_python_documentation(self):
        path = get_file_url("tests/sample-data/website1/index.html")
        result = get_favicon_url.get_favicon_url(path, None)
        real_icon_path = get_file_url(
            "tests/sample-data/website1/_static/py.svg"
        )
        self.assertEqual(result, real_icon_path)

    def test_archwiki(self):
        path = get_file_url("tests/sample-data/website2/index.html")
        result = get_favicon_url.get_favicon_url(path, None)
        # This doesn't actually exit but it doesn't have to.
        real_icon_path = get_file_url("tests/sample-data/website2/favicon.ico")
        self.assertEqual(result, real_icon_path)

    def test_empty_base_tag(self):
        # The fact that a website has a base tag doesn't have to mean that the
        # base URL is different. get_favicon_url() should ignore this.
        path = get_file_url("tests/sample-data/website4/index.html")
        result = get_favicon_url.get_favicon_url(path, None)

        real_icon_path = get_file_url("tests/sample-data/website4/data/favicon.svg")
        self.assertEqual(result, real_icon_path)

    def test_base_tag(self):
        path = get_file_url("tests/sample-data/website5/index.html")
        result = get_favicon_url.get_favicon_url(path, None)

        real_icon_path = get_file_url("tests/sample-data/website5/data/favicon.svg")
        self.assertEqual(result, real_icon_path)

    def test_data_link(self):
        path = get_file_url("tests/sample-data/website3/index.html")
        result = get_favicon_url.get_favicon_url(path, None)

        with open("tests/sample-data/website3/link.txt", "r") as f:
            # This is the link specified in index.html (it's more practical to
            # put the link itself into a file rather than putting it here as
            # a string literal).
            link = f.read()

        self.assertEqual(result, link)

    def test_redirection(self):
        # It's difficult to write tests using remote pages because there is no
        # guarantee that the website will exist or behave same as it does now.
        # This does some sanity checking just to be sure.
        try:
            with requests.get("https://btrfs.wiki.kernel.org/index.php") as data:
                data.raise_for_status()
                if (
                    data.url
                    != "https://archive.kernel.org/oldwiki/btrfs.wiki.kernel.org/"
                ):
                    self.skipTest(
                        "Tested website has changed since this unit "
                        "test was made. Test results can't be reliable."
                    )
        except requests.ConnectionError | requests.HTTPError:
            self.skipTest("Couldn't reach tested website.")

        result = get_favicon_url.get_favicon_url(
            "https://btrfs.wiki.kernel.org/index.php", None
        )
        # The request should be redirected to archive.kernel.org. The favicon
        # should be relative to the final link, not to the original link.
        self.assertNotEqual(result, "https://btrfs.wiki.kernel.org/favicon.ico")
