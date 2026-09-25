"""Taking URLs out of a string before it leaves the process."""

from __future__ import annotations

import re

URL_RE = re.compile(r"\bhttps?://\S+", re.IGNORECASE)
WITHHELD_URL = "<url withheld>"


def withhold_urls(text: str) -> str:
    """Replace every URL-shaped run with `<url withheld>`, whole.

    Deliberately blunt: a URL can carry an identifier, a signed query string or a token, and it
    can come back truncated or re-encoded inside somebody else's error message, so it is not
    matched against a known secret. A URL in a message a human reads adds nothing they could act
    on anyway.
    """
    return URL_RE.sub(WITHHELD_URL, text)
