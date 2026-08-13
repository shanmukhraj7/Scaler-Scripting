from __future__ import annotations

import json
import logging
import re
from collections.abc import Mapping, Set
from pathlib import Path
from typing import Any

from .config import LoggingConfig

_HYPHEN_BREAK = re.compile(r"([A-Za-z])-\n([A-Za-z])")
_MULTI_SPACE = re.compile(r"[^\S\n]+")
_MULTI_NEWLINE = re.compile(r"\n{3,}")
_BROKEN_EMAIL = re.compile(
    r"([A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.co)\n(m)\b",
    re.IGNORECASE,
)
_BROKEN_WWW = re.compile(
    r"(www\.[A-Za-z0-9.\-]+)\n\.\s*com\b",
    re.IGNORECASE,
)
_BROKEN_WWW_SPACE = re.compile(
    r"(www\.[A-Za-z0-9.\-]+)\.\s+com\b",
    re.IGNORECASE,
)

_LOGGER_FLAG = "_pii_pipeline_configured"


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def configure_logging(config: LoggingConfig) -> None:
    root = logging.getLogger()
    if getattr(root, _LOGGER_FLAG, False):
        root.setLevel(config.level)
        return

    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(fmt=config.fmt, datefmt=config.datefmt))
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(config.level)
    setattr(root, _LOGGER_FLAG, True)


def normalize_whitespace(text: str) -> str:
    collapsed = _MULTI_SPACE.sub(" ", text)
    collapsed = _MULTI_NEWLINE.sub("\n\n", collapsed)
    return collapsed.strip()


def normalize_for_match(value: str) -> str:
    text = " ".join(value.split()).casefold()
    if text.startswith("the "):
        text = text[4:]
    return text


def is_allowlisted(value: str, allowlist: Set[str]) -> bool:
    return normalize_for_match(value) in allowlist


def token_count(value: str) -> int:
    return len(value.split())


def clip_context(text: str, start: int, end: int, window: int) -> str:
    if window <= 0:
        return ""
    left = max(0, start - window)
    right = min(len(text), end + window)
    return text[left:right]


def join_hyphenated_linebreaks(text: str) -> str:
    return _HYPHEN_BREAK.sub(r"\1\2", text)


def repair_pdf_artifacts(text: str) -> str:
    text = _BROKEN_EMAIL.sub(r"\1\2", text)
    text = _BROKEN_WWW.sub(r"\1.com", text)
    text = _BROKEN_WWW_SPACE.sub(r"\1.com", text)
    return text


def ensure_directory(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def dump_json(path: str | Path, payload: Mapping[str, Any] | list[Any]) -> None:
    path = Path(path)
    ensure_directory(path.parent)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def load_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))
