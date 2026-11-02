"""Format checks for driver-supplied identifiers. These catch typos, not fraud."""

import re

SHARE_CODE_RE = re.compile(r"^[A-Z0-9]{9}$")
# 5 surname chars (padded with 9), 6 DOB digits, 2 initials (padded with 9), 1 digit, 2 check chars.
LICENCE_NUMBER_RE = re.compile(r"^[A-Z9]{5}\d{6}[A-Z9]{2}\d[A-Z0-9]{2}$")
DVLA_CHECK_CODE_RE = re.compile(r"^[A-Za-z0-9]{8}$")


def normalise_share_code(raw: str) -> str:
    return re.sub(r"[\s-]", "", raw).upper()


def validate_share_code(raw: str, require_w_prefix: bool = True) -> str:
    """Real right to work codes start with W; provider sandbox test codes (e.g. AA1AA1AA1) don't."""
    code = normalise_share_code(raw)
    if len(code) != 9:
        raise ValueError("A share code has 9 characters, for example W12 3AB C45.")
    if require_w_prefix and not code.startswith("W"):
        raise ValueError(
            "Right to work share codes start with W. Ask the driver for a code made for "
            "'prove your right to work', not one for renting or other purposes."
        )
    if not SHARE_CODE_RE.match(code):
        raise ValueError("A share code can only contain letters and numbers.")
    return code


def normalise_licence_number(raw: str) -> str:
    return re.sub(r"\s", "", raw).upper()


def validate_licence_number(raw: str) -> str:
    number = normalise_licence_number(raw)
    if len(number) != 16:
        raise ValueError("A UK driving licence number has 16 characters (section 5 of the photocard).")
    if not LICENCE_NUMBER_RE.match(number):
        raise ValueError("That doesn't look like a UK driving licence number. Check section 5 of the photocard.")
    return number


def validate_dvla_check_code(raw: str) -> str:
    """DVLA check codes are 8 letters and digits, case-sensitive, shown in pairs like 'Hb Rh fp 7g'."""
    code = re.sub(r"\s", "", raw)
    if not DVLA_CHECK_CODE_RE.match(code):
        raise ValueError("A DVLA check code has 8 letters and numbers, for example Hb Rh fp 7g.")
    return code


def mask(value: str | None, keep: int = 3) -> str:
    if not value:
        return ""
    return value[:keep] + "*" * max(len(value) - keep, 0)
