import urllib.parse

from connectors.registry import list_connectors, get_connector


def test_box_registered():
    names = list_connectors()
    assert "box" in names


def test_box_authorize_url_building(monkeypatch):
    box = get_connector("box")
    url = box.build_authorize_url(
        client_id="abc",
        redirect_uri="http://localhost:8000/auth/box/callback",
        state="xyz",
    )
    # Basic assertions on URL
    parsed = urllib.parse.urlparse(url)
    qs = urllib.parse.parse_qs(parsed.query)
    assert qs["response_type"] == ["code"]
    assert qs["client_id"] == ["abc"]
    assert qs["redirect_uri"] == ["http://localhost:8000/auth/box/callback"]
    assert qs["state"] == ["xyz"]
