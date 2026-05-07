from parser import parse_qr_payload


def test_parse_empty():
    result = parse_qr_payload("")
    assert result.type == "empty"


def test_parse_url():
    result = parse_qr_payload("https://example.com")
    assert result.type == "url"
