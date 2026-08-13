from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class PIIType(str, Enum):
    PERSON = "PERSON"
    EMAIL_ADDRESS = "EMAIL_ADDRESS"
    PHONE_NUMBER = "PHONE_NUMBER"
    ORGANIZATION = "ORGANIZATION"
    LOCATION = "LOCATION"
    ADDRESS = "ADDRESS"
    US_SSN = "US_SSN"
    CREDIT_CARD = "CREDIT_CARD"
    DATE_OF_BIRTH = "DATE_OF_BIRTH"
    IP_ADDRESS = "IP_ADDRESS"
    DATE_TIME = "DATE_TIME"
    URL = "URL"
    IN_PAN = "IN_PAN"
    IN_AADHAAR = "IN_AADHAAR"


class DetectionSource(str, Enum):
    REGEX = "regex"
    SPACY = "spacy"
    PRESIDIO = "presidio"


@dataclass(frozen=True, slots=True)
class PageContent:
    page_number: int
    text: str

    def __post_init__(self) -> None:
        if self.page_number < 1:
            raise ValueError(f"page_number must be >= 1, got {self.page_number}")


@dataclass(frozen=True, slots=True)
class ExtractedDocument:
    source_path: Path
    pages: tuple[PageContent, ...]

    @property
    def page_count(self) -> int:
        return len(self.pages)

    @property
    def full_text(self) -> str:
        return "\n\n".join(page.text for page in self.pages)


@dataclass(frozen=True, slots=True)
class PIIEntity:
    text: str
    entity_type: PIIType
    start: int
    end: int
    page_number: int
    score: float
    detector: DetectionSource
    context: str = ""

    def __post_init__(self) -> None:
        if self.start < 0 or self.end < self.start:
            raise ValueError(f"Invalid span: start={self.start}, end={self.end}")
        if not 0.0 <= self.score <= 1.0:
            raise ValueError(f"score must be in [0.0, 1.0], got {self.score}")
        if self.page_number < 1:
            raise ValueError(f"page_number must be >= 1, got {self.page_number}")

    @property
    def span_length(self) -> int:
        return self.end - self.start

    def overlaps(self, other: PIIEntity) -> bool:
        if self.page_number != other.page_number:
            return False
        return self.start < other.end and other.start < self.end


@dataclass(frozen=True, slots=True)
class Replacement:
    original: str
    fake: str
    entity_type: PIIType


@dataclass
class ReplacementMap:
    _store: dict[tuple[str, PIIType], Replacement] = field(default_factory=dict)

    def __len__(self) -> int:
        return len(self._store)

    def get(self, original: str, entity_type: PIIType) -> Replacement | None:
        return self._store.get((self._normalize(original), entity_type))

    def put(self, replacement: Replacement) -> Replacement:
        key = (self._normalize(replacement.original), replacement.entity_type)
        existing = self._store.get(key)
        if existing is not None:
            return existing
        self._store[key] = replacement
        return replacement

    def items(self) -> list[Replacement]:
        return list(self._store.values())

    def as_dict(self) -> dict[str, str]:
        return {item.original: item.fake for item in self._store.values()}

    @staticmethod
    def _normalize(value: str) -> str:
        return " ".join(value.split()).casefold()


@dataclass(frozen=True, slots=True)
class AnonymizedPage:
    page_number: int
    text: str
    entity_count: int


@dataclass(frozen=True, slots=True)
class AnonymizedDocument:
    source_path: Path
    pages: tuple[AnonymizedPage, ...]
    replacements: ReplacementMap
    entities: tuple[PIIEntity, ...]
