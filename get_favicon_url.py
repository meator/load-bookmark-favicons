"""Module for retrieving the location of a website's favicon.

This module provides a logger (which is set to NullHandler by default) with the
same name as the module."""

import html.parser
import urllib.parse
import requests
import logging
from base_types import *
import typing

import magic

# Get a silenced logger. The main program can change verbosity with the -v flag
# which modifies this logger.
_log = logging.getLogger(__name__)
_log.addHandler(logging.NullHandler())


class _StopSearch(Exception):
    """Exception used by _IconHTMLParser to signal end of favicons."""

    pass


class _IconHTMLParser(html.parser.HTMLParser):
    """HTML parser which searches for favicon URLs with their attributes.

    When the parser will reach the end tag of head, it will raise _StopSearch
    to signal that further parsing is unnecessary because no favicons can
    follow after the end of head.

    It also looks for the base tag to know the base URL of all links.

    Attributes:
        favicons (list[dict[str, str | None]]): A list of dictionaries
          containing all found favicon URLs with their attributes. The
          dictionary contains all XML attributes of the link tag. This means
          that if _IconHTMLParser finds a link tag
          <link rel="shortcut icon" href="https://example.com/myicon.ico">, its
          favicons attribute will be [{"rel": "shortcut icon",
          "href": "https://example.com/myicon.ico"}].
        base_url (str | None): The base URL of the page. Set if the base tag is
          present. Otherwise it's set to None.
    """

    def __init__(self) -> None:
        """Initialize _IconHTMLParser."""

        super().__init__()
        self.favicons: list[dict[str, str | None]] = []
        self.base_url: str | None = None
        # Used in handle_endtag.
        self._ended = False

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        """Search for link tags containing favicon URLs with their attributes.

        This function looks for link and base tags. When it encounters other
        tags, it ignores them. If the link tag contains a valid reference to a
        favicon it appends it to self.favicons.

        Args:
            tag: Current tag.
            attrs: List of XML attributes of the tag.
        """

        if tag == "base":
            attributes = dict(attrs)
            if "href" not in attributes:
                # A base tag doesn't have to contain the base URL
                return
            assert attributes["href"]
            self.base_url = attributes["href"]
            return

        if tag != "link":
            return

        attributes = dict(attrs)
        # The "sizes" attribute could be useful for picking icons. Not all
        # websites use it. But now get_favicon_url() just picks the first
        # favicon found.

        if "rel" not in attributes or (
            attributes["rel"] != "icon" and attributes["rel"] != "shortcut icon"
        ):
            # Not a favicon.
            return

        self.favicons.append(attributes)

    def handle_endtag(self, tag: str) -> None:
        """Handle end tags.

        In particular, this method looks for </head> to then raise
        StopIteration as described earlier.

        Args:
            tag: Name of the ending tag.

        Raises:
            _StopSearch: If </head> is encountered.
        """

        # self._ended is needed because _IconHTMLParser shouldn't throw
        # StopIteration multiple times. HTMLParser.close() can call this method
        # which could result in the second raise of StopIteration.
        if not self._ended:
            if tag == "head":
                self._ended = True
                raise _StopSearch("No favicons can proceed.")


class UnknownSchemeError(Exception):
    """Exception used by get_favicon_url."""


class TimedOutError(Exception):
    """Exception used by get_favicon_url."""


class _RetrievalError(Exception):
    """Exception that signals failed retrieval of resource."""


def _get_local_file(file_path: str, buffer_size: int) -> _IconHTMLParser | None:
    """Try to query all favicons of a local web page.

    Args:
        file_path: Path to file (doesn't have to exist).
        buffer_size: Size of the buffer which is used for reading the local
          file.

    Raises:
        _RetrievalError: If file doesn't exist or some other error occured.

    Returns:
        A _IconHTMLParser containing all relevant favicon data parsed from file
        or None if file isn't in (X)HTML format.
    """

    # This isn't really necessary but it makes unbound warnings go away.
    parser = None

    try:
        filetype = magic.from_file(file_path, True)
        if filetype != "application/xhtml+xml" and filetype != "text/html":
            return None

        parser = _IconHTMLParser()

        with open(file_path, "r") as f:
            while chunk := f.read(buffer_size):
                parser.feed(chunk)
    except _StopSearch:
        # No favicons can follow, abort parsing.
        pass
    except OSError as exc:
        raise _RetrievalError("Couldn't access file: " + str(exc)) from exc

    # Just checking that the None from the first line hasn't stayed in parser
    # just to be sure.
    assert parser is not None

    return parser


def _get_remote_filetype(
    data: requests.Response, iter: typing.Iterator[str]
) -> tuple[str | None, str | None]:
    """Try to guess the filetype of remote resource.

    iter is necessary because _get_remote_filetype might need to fetch the first
    chunk of the resource to determine the filetype. In that case, the chunk
    will be returned to make sure no information is lost.

    This isn't the best approach, websites can lie in Content-Type, magic isn't
    really meant for this. The correct way would probably be to use mime
    sniffing.

    Args:
        data: Request response.
        iter: iter_content of the response (Unicode encoded).

    Returns:
        A tuple containing filetype and the first chunk of the resource.
        Filetype can be None if it couldn't be detected and chunk can be None
        if fetching the beginning of the resource wasn't necessary for filetype
        guessing.
    """

    if "Content-Type" in data.headers:
        return (data.headers["Content-Type"], None)
    else:
        # If we don't know the Content-Type, fetch the beginning of the
        # data and use magic to identify it.
        chunk = next(iter, None)
        if chunk is None:
            return (None, None)
        # chunk can apparently sometimes not be str (even when decode_unicode
        # has been set to True).
        return (magic.from_buffer(chunk, True), str(chunk))


def _get_remote_file(
    url: website_url, timeout: float | None, buffer_size: int
) -> tuple[_IconHTMLParser | None, website_url | None]:
    """Try to query all favicons of a remote web page.

    Args:
        url: URL pointing to the resource.
        timeout: Timeout of request. Can be set to None to disable timeout.
        buffer_size: Size of the buffer which is used for reading the remote
          file. Must be >= 2048.

    Raises:
        _RetrievalError: If remote file couldn't be accessed.
        TimedOutError: If request timed out.

    Returns:
        A _IconHTMLParser containing all relevant favicon data parsed from web
        page or None if the resource isn't in (X)HTML format. If redirection
        occured during resolving of url, the returned url will contain the final
        url.
    """

    # magic needs at least 2048 bits to work.
    if buffer_size < 2048:
        raise ValueError("buffer_size must be >= 2048.")

    parser = _IconHTMLParser()

    redirected_url = None

    try:
        with requests.get(url, timeout=timeout, stream=True) as data:
            data.raise_for_status()

            # Overwrite the url with the redirected one.
            if data.url != url:
                redirected_url = website_url(data.url)

            data_iter = data.iter_content(buffer_size, decode_unicode=True)

            filetype, first_chunk = _get_remote_filetype(data, data_iter)

            # No type means wrong type.
            if filetype is None:
                return (None, redirected_url)

            # Using startswith just to be sure. MIME can sometimes append some
            # data to the MIME string. This might not be necessary.
            if not filetype.startswith(
                "application/xhtml+xml"
            ) and not filetype.startswith("text/html"):
                return (None, redirected_url)

            if first_chunk is not None:
                parser.feed(first_chunk)

            for chunk in data_iter:
                # Beware, chunk can sometimes be a bytes object.
                parser.feed(str(chunk))
    except requests.Timeout as exc:
        raise TimedOutError(f"Request to '{url}' timed out.") from exc
    except _StopSearch:
        # No favicons can follow, abort parsing.
        pass
    except (requests.ConnectionError, requests.HTTPError) as exc:
        raise _RetrievalError("Couldn't access resource: " + str(exc)) from exc

    return (parser, redirected_url)


class _ResourceFaviconData(typing.NamedTuple):
    """Tuple containing all raw info about a resource.

    The resource can be local and remote.
    """

    parser: _IconHTMLParser | None
    new_url: website_url | None


def _get_favicon_data(
    is_local: bool, url: str, buffer_size: int, timeout: float | None
) -> _ResourceFaviconData:
    """Query local or remote web page for favicon URLs and their attributes.

    Args:
        is_local: Is the resource local or remote?
        url: URL of resource if it is remote, path to resource if it is local.
        buffer_size: Size of buffer.
        timeout: Timeout of request. Can be set to None to disable timeout.

    Raises:
        _RetrievalError: If web page file couldn't be accessed.

    Returns:
        _ResourceFaviconData containing information about the resource. Its
        parser contains the _IconHTMLParser containing all favicon URLs and
        their attributes or None if the resource isn't (X)HTML. Its new_url
        contains a redirected url to the original website if reirection occured
        or None otherwise.
    """

    link = None
    # Let _RetrievalError propagate.
    if is_local:
        parser = _get_local_file(url, buffer_size)
    else:
        parser, link = _get_remote_file(website_url(url), timeout, buffer_size)
    if parser is None:
        # Not (X)HTML.
        return _ResourceFaviconData(None, link)
    return _ResourceFaviconData(parser, link)


def _get_root_favicon(is_local: bool, url: str):
    """Return the root /favicon.ico of link.

    Args:
        is_local: Is the resource local?
        link: The website URL.

    Returns:
        The URL of the root favicon. This function doesn't check if that icon
        exists.
    """

    if is_local:
        # A slash for local files would overwrite the entire path.
        root_favicon = favicon_url(urllib.parse.urljoin(url, "favicon.ico"))
    else:
        root_favicon = favicon_url(urllib.parse.urljoin(url, "/favicon.ico"))

    _log.info("Found no favicon links in '%s', using '%s'.", url, root_favicon)
    return root_favicon


def _get_absolute_link(
    is_local: bool, base_url: str | None, url: str, favicon: str
) -> favicon_url:
    """Construct the final absolute favicon URL from relevant URLs.

    Args:
        is_local: Is the favicon a local file?
        base_url: HTML <base> URL (possibly relative) to which all links are
          relative to.
        url: The URL of the originating website. This doesn't have to match
          the original website URL because redirection might have occured.
        favicon: Favicon URL (possibly relative).

    Returns:
        Absolute favicon URL.
    """

    if is_local:
        # Let's say we have a local website file:///web/index.html which refers
        # to a favicon at /favicon.ico. joining these two would result in
        # file:///favicon.ico which is wrong. Doing this correctly would
        # require knowing the website root which isn't that clear for local
        # files. One solution would be to crawl all directories in the path
        # and check whether selected_url is there somewhere but for now we just
        # hope that the favicon is in the same directory.
        favicon = favicon.removeprefix("/")

    if base_url:
        # base_url can be relative.
        base = urllib.parse.urljoin(url, base_url)
        return favicon_url(urllib.parse.urljoin(base, favicon))
    else:
        return favicon_url(urllib.parse.urljoin(url, favicon))


def get_favicon_url(
    url: website_url, timeout: float | None
) -> favicon_url | None:
    """Get an URL pointing to link's favicon.

    The fact that this function didn't return None doesn't have to mean that
    a favicon actually exists. In some circumstances the returned favicon can
    point to a nonexistent resource.

    Args:
        url: An URL of the resource. Can be both local (file://) and remote
          (http://, https://).
        timeout: Timeout of remote requests. Can be set to None to disable
          timeout.

    Raises:
        UnknownSchemeError: If link's scheme is not recognised.
        TimedOutError: If the remote request timed out.

    Returns:
        favicon_url of url or None if it couldn't be located.
    """

    buffer_size = 2048

    _log.info("Processing link '%s'.", url)
    url_parsed = urllib.parse.urlparse(url)

    match url_parsed.scheme:
        case "file":
            _log.info("Link points to a local file.")
            is_local = True
        case "http" | "https":
            _log.info("Link points to a remote file.")
            is_local = False
        case _:
            raise UnknownSchemeError(f"Unknown scheme '{url_parsed.scheme}'.")

    # If the request failed, return None. If it failed because it isn't HTML,
    # try /favicon.ico (even non-(X)HTML files can have a favicon). If it
    # succeeded and found no favicons, try /favicon.ico.
    try:
        response = _get_favicon_data(
            is_local, url_parsed.path if is_local else url, buffer_size, timeout
        )
    except _RetrievalError as exc:
        _log.info("%s", str(exc))
        return None

    if response.parser is not None:
        if response.parser.base_url:
            _log.debug("URLs are relative to '%s'.", response.parser.base_url)
        _log.info("Found %d favicon(s).", len(response.parser.favicons))

    # We could have been redirected.
    if response.new_url is not None:
        _log.debug(
            "URL '%s' has been redirected to '%s'.", url, response.new_url
        )
        url = response.new_url
        url_parsed = urllib.parse.urlparse(url)

    if response.parser is None or not response.parser.favicons:
        return _get_root_favicon(is_local, url)

    # As noted in the readme, this program's purpose is not to produce same
    # results as the browser would. Browsers have their rules for this, but
    # this program picks the first favicon it finds.

    icon_data = response.parser.favicons[0]

    selected_url = icon_data["href"]
    assert selected_url is not None
    result_link = _get_absolute_link(
        is_local, response.parser.base_url, url, selected_url
    )

    _log.info("Found favicon '%s'.", result_link)
    return result_link
