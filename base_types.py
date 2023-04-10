"""Module providing helper types.

Types defined here are defined just for clarity. They are all typing.NewType
of str.
"""

import typing

# Example: https://duckduckgo.com/
website_url = typing.NewType("website_url", str)
# Example: https://duckduckgo.com/favicon.ico
favicon_url = typing.NewType("favicon_url", str)
