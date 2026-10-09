import re


_PHONE_FORMATTING = re.compile(r"[\s().-]")
_E164 = re.compile(r"^\+[1-9][0-9]{7,14}$")


def normalize_phone_number(value: str) -> str:
    normalized = _PHONE_FORMATTING.sub("", value)
    if not _E164.fullmatch(normalized):
        raise ValueError("Phone number must include its country code in E.164 format.")
    return normalized
