import pytest

from app.domain.validation import mask, validate_licence_number, validate_share_code
from app.logging_config import redact


@pytest.mark.parametrize("raw", ["W12 3AB C45", "w123abc45", "W12-3AB-C45", " W123ABC45 "])
def test_share_code_is_normalised(raw):
    assert validate_share_code(raw) == "W123ABC45"


@pytest.mark.parametrize(
    "raw, message",
    [
        ("W12 3AB C4", "9 characters"),
        ("R12 3AB C45", "start with W"),
        ("W12 3AB C4!", "letters and numbers"),
    ],
)
def test_share_code_errors_explain_the_problem(raw, message):
    with pytest.raises(ValueError, match=message):
        validate_share_code(raw)


def test_licence_number_accepts_padded_and_spaced_input():
    assert validate_licence_number("nowak 803147 t99ab") == "NOWAK803147T99AB"
    assert validate_licence_number("LI999606170AB9CD") == "LI999606170AB9CD"


@pytest.mark.parametrize("raw", ["NOWAK803147T99A", "N0WAK803147T99AB", "NOWAKX03147T99AB"])
def test_licence_number_rejects_bad_formats(raw):
    with pytest.raises(ValueError):
        validate_licence_number(raw)


def test_mask_keeps_prefix_only():
    assert mask("NOWAK803147T99AB") == "NOW" + "*" * 13
    assert mask(None) == ""


def test_logs_never_contain_share_codes_or_licence_numbers():
    line = "driver sent W12 3AB C45 and licence NOWAK803147T99AB"
    assert redact(line) == "driver sent [REDACTED] and licence [REDACTED]"
