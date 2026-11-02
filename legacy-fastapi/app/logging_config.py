import logging
import re

# Share codes (W + 8) and UK licence numbers must never reach the logs.
_SENSITIVE = [
    re.compile(r"\bW[A-Z0-9]{2}[\s-]?[A-Z0-9]{3}[\s-]?[A-Z0-9]{3}\b"),
    re.compile(r"\b[A-Z9]{5}\d{6}[A-Z9]{2}\d[A-Z0-9]{2}\b"),
]


def redact(text: str) -> str:
    for pattern in _SENSITIVE:
        text = pattern.sub("[REDACTED]", text)
    return text


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        cleaned = redact(message)
        if cleaned != message:
            record.msg = cleaned
            record.args = None
        return True


def configure_logging(level: int = logging.INFO) -> None:
    root = logging.getLogger()
    if not root.handlers:
        logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    for handler in root.handlers:
        if not any(isinstance(f, RedactingFilter) for f in handler.filters):
            handler.addFilter(RedactingFilter())
