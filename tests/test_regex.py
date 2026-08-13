from src.detector import (
    AADHAAR_RE,
    CREDIT_CARD_RE,
    EMAIL_RE,
    IPV4_RE,
    IPV6_RE,
    PAN_RE,
    PHONE_RE,
    SSN_RE,
    luhn_ok,
    looks_like_phone,
)
from src.models import PageContent
from src.utils import repair_pdf_artifacts


def test_email_detection():
    text = "Write to rashhi.patil@gmail.com or cs.connect@kshinternational.com today."
    found = [match.group(0) for match in EMAIL_RE.finditer(text)]
    assert "rashhi.patil@gmail.com" in found
    assert "cs.connect@kshinternational.com" in found


def test_broken_email_is_repaired():
    raw = "cs.connect@kshinternational.co\nm Telephone: + 91 20 45053237"
    fixed = repair_pdf_artifacts(raw)
    found = [match.group(0) for match in EMAIL_RE.finditer(fixed)]
    assert "cs.connect@kshinternational.com" in found


def test_phone_detection():
    samples = [
        "+91 9876543210",
        "+ 91 20 45053237",
        "+91 22 4009 4400",
        "9876543210",
    ]
    for sample in samples:
        assert PHONE_RE.search(sample), sample
        assert looks_like_phone(sample), sample


def test_phone_skips_short_or_year_like_numbers():
    assert not looks_like_phone("2025")
    assert not looks_like_phone("410501")
    assert PHONE_RE.search("Offer size 4200 million") is None or not looks_like_phone(
        PHONE_RE.search("Offer size 4200 million").group(0)
    )


def test_ip_detection():
    text = "VPN 192.168.10.24 and 2001:0db8:85a3:0000:0000:8a2e:0370:7334"
    assert IPV4_RE.search(text).group(0) == "192.168.10.24"
    assert IPV6_RE.search(text)


def test_ssn_and_pan_and_aadhaar():
    assert SSN_RE.search("SSN 123-45-6789").group(0) == "123-45-6789"
    assert PAN_RE.search("PAN ABCDE1234F").group(0) == "ABCDE1234F"
    assert AADHAAR_RE.search("Aadhaar 2345 6789 0123").group(0) == "2345 6789 0123"


def test_credit_card_luhn():
    valid = "4111 1111 1111 1111"
    invalid = "4111 1111 1111 1112"
    assert luhn_ok(valid)
    assert not luhn_ok(invalid)
    assert CREDIT_CARD_RE.search(valid)
