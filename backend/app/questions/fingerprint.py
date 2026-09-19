import hashlib
import re
import unicodedata


_WHITESPACE = re.compile(r"\s+")


def normalize_question_content(content: str) -> str:
    normalized = unicodedata.normalize("NFKC", content)
    return _WHITESPACE.sub(" ", normalized).strip().casefold()


def question_content_hash(content: str) -> str:
    normalized = normalize_question_content(content)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
