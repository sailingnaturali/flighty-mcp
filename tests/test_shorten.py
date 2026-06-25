import json
from unittest.mock import patch, MagicMock

from flighty_mcp.animator import shorten_url

LONG = "https://flights.sailingnaturali.com/?d=eyJ2IjoxfQ"


def _resp(status, body):
    m = MagicMock()
    m.status = status
    m.read.return_value = json.dumps(body).encode()
    m.__enter__.return_value = m
    m.__exit__.return_value = False
    return m


def test_returns_short_url_on_success():
    short = "https://flights.sailingnaturali.com/t/abc123def456"
    with patch("urllib.request.urlopen", return_value=_resp(200, {"url": short})):
        assert shorten_url(LONG) == short


def test_falls_back_on_non_200():
    with patch("urllib.request.urlopen", return_value=_resp(500, {})):
        assert shorten_url(LONG) == LONG


def test_falls_back_on_exception():
    with patch("urllib.request.urlopen", side_effect=OSError("offline")):
        assert shorten_url(LONG) == LONG


def test_passes_through_url_without_d():
    plain = "https://flights.sailingnaturali.com/?r=sfo-lhr"
    with patch("urllib.request.urlopen") as m:
        assert shorten_url(plain) == plain
        m.assert_not_called()
