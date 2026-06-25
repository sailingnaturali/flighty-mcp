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


from flighty_mcp.animator import apply_shortening


def test_apply_shortening_replaces_urls_when_enabled():
    result = {"status": "ok", "url": "L1", "round_trip_url": "L2"}
    out = apply_shortening(result, enabled=True, shorten=lambda u: f"short:{u}")
    assert out["url"] == "short:L1"
    assert out["round_trip_url"] == "short:L2"


def test_apply_shortening_noop_when_disabled():
    result = {"status": "ok", "url": "L1", "round_trip_url": None}
    out = apply_shortening(result, enabled=False, shorten=lambda u: "NOPE")
    assert out["url"] == "L1"


def test_apply_shortening_skips_non_ok_status():
    result = {"status": "confirm_home", "inferred_home": "YVR"}
    out = apply_shortening(result, enabled=True, shorten=lambda u: "NOPE")
    assert out == {"status": "confirm_home", "inferred_home": "YVR"}
