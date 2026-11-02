"""Model fields stored encrypted. They can't be filtered or ordered on, so only use them for personal data."""

import json
from typing import Any

from django.db import models

from common.crypto import decrypt, encrypt


class EncryptedTextField(models.TextField):
    def from_db_value(self, value: str | None, expression, connection) -> str | None:
        if value is None:
            return None
        return decrypt(value.encode()).decode()

    def get_prep_value(self, value: Any) -> str | None:
        if value is None:
            return None
        return encrypt(str(value).encode()).decode()


class EncryptedJSONField(models.TextField):
    def from_db_value(self, value: str | None, expression, connection) -> Any:
        if value is None:
            return None
        return json.loads(decrypt(value.encode()))

    def to_python(self, value: Any) -> Any:
        return value

    def get_prep_value(self, value: Any) -> str | None:
        if value is None:
            return None
        return encrypt(json.dumps(value, default=str).encode()).decode()
