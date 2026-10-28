"""T10: secret masking (Appendix E.1, principle 13). Written before capture/secrets.py."""

import string

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from moira.capture.secrets import detect, mask


def j(*parts: str) -> str:
    """Join fake-secret fixtures at runtime so secret scanners never see a whole one."""
    return "".join(parts)


GHP = j("ghp", "_", "aB3dE5fG7hJ9kL1mN3pQ5rS7tU9vW1xY3zA5")
APPENDIX_E1 = [
    ("wifi password: blue-otter-77", "wifi password: [hidden password]"),
    ("my card 4242 4242 4242 4242 exp 12/28", "my card [hidden card •••• 4242] exp 12/28"),
    ("123456 is your Instagram code", "[hidden code] is your Instagram code"),
    ("call me at 9841234567", "call me at 9841234567"),
    ("I'll pass on that", "I'll pass on that"),
    (GHP, "[hidden key]"),
    (
        "commit 9fceb02d0ae598e95dc970b74767f19372d61af8",
        "commit 9fceb02d0ae598e95dc970b74767f19372d61af8",
    ),
    (
        j("https://site.example/reset?to", "ken=abcDEF", "123456"),
        "https://site.example/reset?token=[hidden key]",
    ),
]

OWN_CASES = [
    # S1 private key block
    (
        j(
            "key:\n-----BEGIN OPENSSH ",
            "PRIVATE KEY-----\nb3BlbnNzaC1rZXktdjEA\n",
            "-----END OPENSSH ",
            "PRIVATE KEY-----",
        ),
        "key:\n[hidden private key]",
    ),
    # S2 known keys
    (j("openai sk", "-proj-", "abcdefghijklmnopqrstuvwxyz123"), "openai [hidden key]"),
    (j("slack xo", "xb-1234567890-abcdefghij"), "slack [hidden key]"),
    (j("aws AK", "IAIOSFODNN7EXAMPLE"), "aws [hidden key]"),
    (j("maps AI", "zaSyD-abcdefghijklmnopqrstuvwxyz12345"), "maps [hidden key]"),
    (j("stripe sk", "_live_", "abcdefghijklmnop1234"), "stripe [hidden key]"),
    (j("bot 123456789:", "AAEhBP0av18AbCdEfGhIjKlMnOpQrStUvWx"), "bot [hidden key]"),
    (
        j(
            "jwt eyJhbGciOiJIUzI1NiJ9",
            ".eyJzdWIiOiIxMjM0NTY3ODkwIn0",
            ".dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U",
        ),
        "jwt [hidden key]",
    ),
    (j("github", "_pat_", "A1b2C3d4E5" * 7), "[hidden key]"),
    # S3 URL parameters
    ("https://x.example/cb?code=abcdef1&state=1", "https://x.example/cb?code=[hidden key]&state=1"),
    ("https://x.example/cb?code=12345", "https://x.example/cb?code=12345"),
    ("https://api.example/v1?api_key=ZZZZZZZZ", "https://api.example/v1?api_key=[hidden key]"),
    # S4 cards
    ("amex 3782 822463 10005", "amex [hidden card •••• 0005]"),
    ("visa 4111-1111-1111-1111", "visa [hidden card •••• 1111]"),
    ("order 4242424242424241", "order 4242424242424241"),  # not Luhn-valid
    ("id 1234567890123456", "id 1234567890123456"),  # no known prefix, not Luhn
    # S5 security code
    ("cvv 123", "cvv [hidden code]"),
    ("CVC: 4567", "CVC: [hidden code]"),
    # S6 one-time codes
    ("your verification code is 482913", "your verification code is [hidden code]"),
    ("OTP: 9921", "OTP: [hidden code]"),
    ("2fa code 112233", "2fa code [hidden code]"),
    ("889900 is your login code", "[hidden code] is your login code"),
    # S7 passwords and PINs
    ("netflix password is Hunter22", "netflix password is [hidden password]"),
    ("pwd=letmein", "pwd=[hidden password]"),
    ("door pin: 4321", "door pin: [hidden password]"),
    ("pin code 7788", "pin code [hidden password]"),
    ("I need to change my password soon", "I need to change my password soon"),
    ("put a pin in it", "put a pin in it"),
    ("pw: s3cret!", "pw: [hidden password]"),
    # S8 high entropy
    ("token Zx9Qw3Er7Ty1Ui5Op2As8Df4Gh6", "token [hidden key]"),
    ("uuid 123e4567-e89b-12d3-a456-426614174000", "uuid 123e4567-e89b-12d3-a456-426614174000"),
    (
        "https://www.youtube.com/watch?v=Qm8vR2xLk4E",
        "https://www.youtube.com/watch?v=Qm8vR2xLk4E",
    ),
    ("mail josh.r@example.com", "mail josh.r@example.com"),
    ("just some ordinary words here", "just some ordinary words here"),
]


@pytest.mark.parametrize(("text", "expected"), APPENDIX_E1 + OWN_CASES)
def test_masking_table(text: str, expected: str) -> None:
    masked, found = mask(text)
    assert masked == expected
    assert found == (masked != text)


def test_has_masked_secret_flag() -> None:
    assert mask("wifi password: blue-otter-77")[1] is True
    assert mask("no secrets")[1] is False


ALNUM = string.ascii_letters + string.digits


@settings(max_examples=200)
@given(
    prefix=st.text(alphabet=string.ascii_lowercase + " ", max_size=20),
    secret=st.sampled_from(
        [
            GHP,
            j("sk", "-", "a1B2c3D4e5F6g7H8i9J0k1"),
            "4242 4242 4242 4242",
            "password: blue-otter-77",
            "Zx9Qw3Er7Ty1Ui5Op2As8Df4Gh6",
        ]
    ),
    suffix=st.text(alphabet=string.ascii_lowercase + " ", max_size=20),
)
def test_no_detected_secret_survives_masking(prefix: str, secret: str, suffix: str) -> None:
    text = f"{prefix} {secret} {suffix}"
    assert detect(text), "the planted secret must be detected"
    masked, found = mask(text)
    assert found
    assert not detect(masked)
    for part in ("ghp_aB3", "a1B2c3D4", "4242 4242", "blue-otter", "Zx9Qw3"):
        assert part not in masked


@given(st.text(max_size=300))
def test_masking_is_idempotent(text: str) -> None:
    once, _ = mask(text)
    assert mask(once)[0] == once
