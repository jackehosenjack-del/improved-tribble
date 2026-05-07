from dataclasses import dataclass
from urllib.parse import urlparse


@dataclass
class ParsedQR:
    raw: str
    type: str
    value: str
    is_empty: bool


def parse_qr_payload(payload: str) -> ParsedQR:
    if payload is None or not str(payload).strip():
        return ParsedQR(raw="", type="empty", value="", is_empty=True)

    raw = str(payload).strip()
    lower = raw.lower()

    if lower.startswith(("http://", "https://")):
        parsed = urlparse(raw)
        return ParsedQR(raw=raw, type="url", value=parsed.geturl(), is_empty=False)

    if lower.startswith("mailto:"):
        return ParsedQR(raw=raw, type="email", value=raw[7:], is_empty=False)

    if lower.startswith("tel:"):
        return ParsedQR(raw=raw, type="phone", value=raw[4:], is_empty=False)

    if lower.startswith("wifi:"):
        return ParsedQR(raw=raw, type="wifi", value=raw, is_empty=False)

    if lower.startswith("smsto:") or lower.startswith("sms:"):
        return ParsedQR(raw=raw, type="sms", value=raw, is_empty=False)

    return ParsedQR(raw=raw, type="text", value=raw, is_empty=False)
