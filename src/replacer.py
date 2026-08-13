from __future__ import annotations

import re

from .faker_utils import FakeValueFactory
from .models import (
    AnonymizedDocument,
    AnonymizedPage,
    ExtractedDocument,
    PIIEntity,
    Replacement,
    ReplacementMap,
)
from .utils import get_logger, normalize_for_match

logger = get_logger(__name__)


class ReplacementEngine:
    def __init__(self, factory: FakeValueFactory | None = None) -> None:
        self._factory = factory or FakeValueFactory()
        self.mapping = ReplacementMap()

    def build_mapping(self, entities: list[PIIEntity]) -> ReplacementMap:
        for entity in entities:
            original = " ".join(entity.text.split())
            if not original:
                continue
            stored = self.mapping.get(original, entity.entity_type)
            if stored is None:
                fake = self._factory.fake_for(original, entity.entity_type)
                stored = self.mapping.put(
                    Replacement(original=original, fake=fake, entity_type=entity.entity_type)
                )
            logger.debug("%s -> %s (%s)", original, stored.fake, entity.entity_type.value)
        return self.mapping

    def anonymize(
        self,
        document: ExtractedDocument,
        entities: list[PIIEntity],
    ) -> AnonymizedDocument:
        self.build_mapping(entities)
        counts = {page.page_number: 0 for page in document.pages}
        for entity in entities:
            counts[entity.page_number] = counts.get(entity.page_number, 0) + 1

        pages = []
        for page in document.pages:
            pages.append(
                AnonymizedPage(
                    page_number=page.page_number,
                    text=self.replace_text(page.text),
                    entity_count=counts.get(page.page_number, 0),
                )
            )

        logger.info("Built %s consistent replacements", len(self.mapping))
        return AnonymizedDocument(
            source_path=document.source_path,
            pages=tuple(pages),
            replacements=self.mapping,
            entities=tuple(entities),
        )

    def replace_text(self, text: str) -> str:
        replacements = sorted(
            self.mapping.items(),
            key=lambda item: len(item.original),
            reverse=True,
        )
        redacted = text
        for item in replacements:
            pattern = _flex_pattern(item.original)
            redacted = pattern.sub(item.fake, redacted)
        return redacted


def _flex_pattern(original: str) -> re.Pattern[str]:
    tokens = [re.escape(token) for token in original.split() if token]
    if not tokens:
        return re.compile(re.escape(original), re.IGNORECASE)
    return re.compile(r"\s+".join(tokens), re.IGNORECASE)


def same_value(left: str, right: str) -> bool:
    return normalize_for_match(left) == normalize_for_match(right)
