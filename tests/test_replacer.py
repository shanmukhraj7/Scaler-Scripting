from pathlib import Path

from src.config import FakerConfig
from src.faker_utils import FakeValueFactory
from src.models import (
    DetectionSource,
    ExtractedDocument,
    PageContent,
    PIIEntity,
    PIIType,
    Replacement,
    ReplacementMap,
)
from src.replacer import ReplacementEngine


def test_fake_values_are_realistic_and_typed():
    factory = FakeValueFactory(FakerConfig(locale="en_IN", seed=42))
    person = factory.fake_for("John Smith", PIIType.PERSON)
    email = factory.fake_for("john@gmail.com", PIIType.EMAIL_ADDRESS)
    phone = factory.fake_for("+91 9876543210", PIIType.PHONE_NUMBER)

    assert person and person != "John Smith"
    assert "@" in email and email != "john@gmail.com"
    assert phone.startswith("+91")


def test_mapping_stays_consistent_across_case_and_spacing():
    mapping = ReplacementMap()
    first = mapping.put(Replacement("John Smith", "Rahul Sharma", PIIType.PERSON))
    second = mapping.put(Replacement("JOHN  SMITH", "Peter Parker", PIIType.PERSON))
    assert first.fake == "Rahul Sharma"
    assert second.fake == "Rahul Sharma"
    assert len(mapping) == 1


def test_same_name_always_replaced_the_same_way():
    factory = FakeValueFactory(FakerConfig(seed=7))
    engine = ReplacementEngine(factory)
    entities = [
        PIIEntity("Rashi Patil", PIIType.PERSON, 0, 11, 1, 0.9, DetectionSource.REGEX),
        PIIEntity("Rashi Patil", PIIType.PERSON, 40, 51, 2, 0.9, DetectionSource.SPACY),
        PIIEntity("RASHI PATIL", PIIType.PERSON, 5, 16, 3, 0.8, DetectionSource.PRESIDIO),
    ]
    document = ExtractedDocument(
        source_path=Path("dummy.pdf"),
        pages=(
            PageContent(1, "Ticket opened by Rashi Patil."),
            PageContent(2, "Follow up with Rashi Patil tomorrow."),
            PageContent(3, "Signed, RASHI PATIL"),
        ),
    )
    result = engine.anonymize(document, entities)
    fake = engine.mapping.get("Rashi Patil", PIIType.PERSON).fake
    assert fake not in {"Rashi Patil", "RASHI PATIL"}
    assert fake in result.pages[0].text
    assert fake in result.pages[1].text
    assert fake in result.pages[2].text
    assert "Rashi Patil" not in result.pages[0].text
    assert "RASHI PATIL" not in result.pages[2].text
