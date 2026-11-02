import pytest

from onboarding.validation import (
    mask,
    validate_dvla_check_code,
    validate_licence_number,
    validate_share_code,
    validate_uk_mobile,
)


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


def test_sandbox_codes_allowed_without_w_prefix():
    assert validate_share_code("AA1 AA1 AA1", require_w_prefix=False) == "AA1AA1AA1"


def test_licence_number_accepts_padded_and_spaced_input():
    assert validate_licence_number("nowak 803147 t99ab") == "NOWAK803147T99AB"
    assert validate_licence_number("LI999606170AB9CD") == "LI999606170AB9CD"


@pytest.mark.parametrize("raw", ["NOWAK803147T99A", "N0WAK803147T99AB", "NOWAKX03147T99AB"])
def test_licence_number_rejects_bad_formats(raw):
    with pytest.raises(ValueError):
        validate_licence_number(raw)


def test_check_code_keeps_case_and_drops_spaces():
    assert validate_dvla_check_code("Hb Rh fp 7g") == "HbRhfp7g"
    with pytest.raises(ValueError):
        validate_dvla_check_code("short")


@pytest.mark.parametrize("raw", ["07700 900123", "+447700900123", "(07700) 900-123"])
def test_uk_mobile(raw):
    assert validate_uk_mobile(raw).endswith("7700900123")


def test_uk_mobile_rejects_landlines():
    with pytest.raises(ValueError):
        validate_uk_mobile("020 7946 0000")


def test_mask_keeps_prefix_only():
    assert mask("NOWAK803147T99AB") == "NOW" + "*" * 13
    assert mask(None) == ""
