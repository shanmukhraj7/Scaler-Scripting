from __future__ import annotations

import re
from collections import defaultdict

import spacy
from presidio_analyzer import AnalyzerEngine
from presidio_analyzer.nlp_engine import NlpEngineProvider
from spacy.language import Language

from .config import DEFAULT_CONFIG, AppConfig, DetectorConfig, PrecisionPolicyConfig
from .models import DetectionSource, ExtractedDocument, PageContent, PIIEntity, PIIType
from .utils import clip_context, get_logger, is_allowlisted, normalize_for_match, token_count

logger = get_logger(__name__)

EMAIL_RE = re.compile(
    r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b",
    re.IGNORECASE,
)
PHONE_RE = re.compile(
    r"(?:\+\s*91[\s\-]*\d{2,5}[\s\-]*\d{4,10}|\+?\s*91[\s\-]*[6-9]\d{9}|\b[6-9]\d{9}\b)"
)
SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
CREDIT_CARD_RE = re.compile(r"\b(?:\d[ \-]*?){13,19}\b")
IPV4_RE = re.compile(r"\b(?:(?:25[0-5]|2[0-4]\d|1?\d{1,2})\.){3}(?:25[0-5]|2[0-4]\d|1?\d{1,2})\b")
IPV6_RE = re.compile(
    r"\b(?:[0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}\b"
    r"|\b(?:[0-9a-fA-F]{1,4}:){1,7}:\b"
)
PAN_RE = re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b")
AADHAAR_RE = re.compile(r"\b\d{4}\s\d{4}\s\d{4}\b")
DATE_RE = re.compile(
    r"\b(?:\d{1,2}(?:st|nd|rd|th)?[\s\-](?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|"
    r"Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|"
    r"Nov(?:ember)?|Dec(?:ember)?)[\s\-,]+\d{2,4}"
    r"|(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|"
    r"Dec(?:ember)?)\s+\d{1,2},?\s+\d{2,4}"
    r"|\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b",
    re.IGNORECASE,
)
PIN_RE = re.compile(r"\b[1-9]\d{5}\b")
ADDRESS_HINTS = (
    "village",
    "road",
    "marg",
    "tower",
    "floor",
    "office",
    "plot",
    "pune",
    "mumbai",
    "baner",
    "chakan",
)
URL_RE = re.compile(r"\b(?:https?://|www\.)[A-Za-z0-9.\-]+(?:\.[A-Za-z]{2,})(?:/[^\s]*)?", re.I)

SPACY_TYPE_MAP = {
    "PERSON": PIIType.PERSON,
    "PER": PIIType.PERSON,
    "ORG": PIIType.ORGANIZATION,
    "GPE": PIIType.LOCATION,
    "LOC": PIIType.LOCATION,
    "FAC": PIIType.LOCATION,
}

PRESIDIO_ENTITIES = [
    "EMAIL_ADDRESS",
    "CREDIT_CARD",
    "US_SSN",
    "IP_ADDRESS",
    "URL",
]

PRESIDIO_TYPE_MAP = {
    "PERSON": PIIType.PERSON,
    "EMAIL_ADDRESS": PIIType.EMAIL_ADDRESS,
    "PHONE_NUMBER": PIIType.PHONE_NUMBER,
    "CREDIT_CARD": PIIType.CREDIT_CARD,
    "US_SSN": PIIType.US_SSN,
    "IP_ADDRESS": PIIType.IP_ADDRESS,
    "LOCATION": PIIType.LOCATION,
    "NRP": PIIType.LOCATION,
    "URL": PIIType.URL,
    "IN_PAN": PIIType.IN_PAN,
    "IN_AADHAAR": PIIType.IN_AADHAAR,
    "ORGANIZATION": PIIType.ORGANIZATION,
}

TYPE_PRIORITY = {
    PIIType.CREDIT_CARD: 100,
    PIIType.US_SSN: 99,
    PIIType.IN_AADHAAR: 98,
    PIIType.IN_PAN: 97,
    PIIType.EMAIL_ADDRESS: 96,
    PIIType.PHONE_NUMBER: 95,
    PIIType.IP_ADDRESS: 94,
    PIIType.DATE_OF_BIRTH: 90,
    PIIType.ADDRESS: 85,
    PIIType.URL: 80,
    PIIType.PERSON: 70,
    PIIType.ORGANIZATION: 60,
    PIIType.LOCATION: 50,
    PIIType.DATE_TIME: 20,
}


def luhn_ok(number: str) -> bool:
    digits = [int(ch) for ch in re.sub(r"\D", "", number)]
    if not (13 <= len(digits) <= 19):
        return False
    checksum = 0
    parity = len(digits) % 2
    for index, digit in enumerate(digits):
        if index % 2 == parity:
            digit *= 2
            if digit > 9:
                digit -= 9
        checksum += digit
    return checksum % 10 == 0


def looks_like_phone(raw: str) -> bool:
    digits = re.sub(r"\D", "", raw)
    if len(digits) < 10 or len(digits) > 13:
        return False
    if raw.strip().startswith("+") or digits.startswith("91"):
        return True
    if len(digits) == 10 and digits[0] in "6789":
        return True
    if len(digits) in {11, 12} and digits[0] == "0":
        return True
    return False


class RegexRecognizer:
    def __init__(self, config: AppConfig) -> None:
        self._detector = config.detector
        self._dates = config.dates

    def find(self, page: PageContent) -> list[PIIEntity]:
        text = page.text
        hits: list[PIIEntity] = []
        hits.extend(self._collect(page, EMAIL_RE, PIIType.EMAIL_ADDRESS, 0.99))
        hits.extend(self._phones(page))
        hits.extend(self._collect(page, SSN_RE, PIIType.US_SSN, 0.95))
        hits.extend(self._cards(page))
        hits.extend(self._collect(page, IPV4_RE, PIIType.IP_ADDRESS, 0.99))
        hits.extend(self._collect(page, IPV6_RE, PIIType.IP_ADDRESS, 0.95))
        hits.extend(self._collect(page, URL_RE, PIIType.URL, 0.9))
        hits.extend(self._dates_and_dobs(page))
        hits.extend(self._addresses(page))
        if self._detector.enable_india_identifiers:
            hits.extend(self._collect(page, PAN_RE, PIIType.IN_PAN, 0.9))
            hits.extend(self._collect(page, AADHAAR_RE, PIIType.IN_AADHAAR, 0.85))
        return hits

    def _collect(
        self,
        page: PageContent,
        pattern: re.Pattern[str],
        entity_type: PIIType,
        score: float,
    ) -> list[PIIEntity]:
        hits = []
        for match in pattern.finditer(page.text):
            hits.append(self._entity(page, match.start(), match.end(), entity_type, score))
        return hits

    def _phones(self, page: PageContent) -> list[PIIEntity]:
        hits = []
        for match in PHONE_RE.finditer(page.text):
            raw = match.group(0)
            if not looks_like_phone(raw):
                continue
            hits.append(
                self._entity(page, match.start(), match.end(), PIIType.PHONE_NUMBER, 0.9)
            )
        return hits

    def _cards(self, page: PageContent) -> list[PIIEntity]:
        hits = []
        for match in CREDIT_CARD_RE.finditer(page.text):
            raw = match.group(0)
            if not luhn_ok(raw):
                continue
            hits.append(
                self._entity(page, match.start(), match.end(), PIIType.CREDIT_CARD, 0.95)
            )
        return hits

    def _dates_and_dobs(self, page: PageContent) -> list[PIIEntity]:
        hits = []
        for match in DATE_RE.finditer(page.text):
            context = clip_context(
                page.text, match.start(), match.end(), self._detector.context_window
            )
            if self._is_dob(context):
                hits.append(
                    self._entity(
                        page,
                        match.start(),
                        match.end(),
                        PIIType.DATE_OF_BIRTH,
                        0.9,
                        context,
                    )
                )
            elif self._dates.redact_all_dates:
                hits.append(
                    self._entity(
                        page,
                        match.start(),
                        match.end(),
                        PIIType.DATE_TIME,
                        0.7,
                        context,
                    )
                )
        return hits

    def _addresses(self, page: PageContent) -> list[PIIEntity]:
        hits = []
        for match in PIN_RE.finditer(page.text):
            start = max(0, match.start() - 90)
            end = min(len(page.text), match.end() + 24)
            window = page.text[start:end]
            if not any(hint in window.casefold() for hint in ADDRESS_HINTS):
                continue
            hits.append(self._entity(page, start, end, PIIType.ADDRESS, 0.75))
        return hits

    def _is_dob(self, context: str) -> bool:
        lowered = context.casefold()
        return any(keyword in lowered for keyword in self._dates.dob_context_keywords)

    def _entity(
        self,
        page: PageContent,
        start: int,
        end: int,
        entity_type: PIIType,
        score: float,
        context: str = "",
    ) -> PIIEntity:
        if not context:
            context = clip_context(page.text, start, end, self._detector.context_window)
        return PIIEntity(
            text=page.text[start:end],
            entity_type=entity_type,
            start=start,
            end=end,
            page_number=page.page_number,
            score=score,
            detector=DetectionSource.REGEX,
            context=context,
        )


def normalize_span_text(value: str) -> str:
    return " ".join(value.split())


class SpacyRecognizer:
    def __init__(self, nlp: Language, policy: PrecisionPolicyConfig) -> None:
        self._nlp = nlp
        self._policy = policy

    def find(self, page: PageContent) -> list[PIIEntity]:
        hits = []
        doc = self._nlp(page.text)
        for ent in doc.ents:
            entity_type = SPACY_TYPE_MAP.get(ent.label_)
            if entity_type is None:
                continue
            if not self._keep(ent.text, entity_type):
                continue
            hits.append(
                PIIEntity(
                    text=ent.text,
                    entity_type=entity_type,
                    start=ent.start_char,
                    end=ent.end_char,
                    page_number=page.page_number,
                    score=0.7,
                    detector=DetectionSource.SPACY,
                    context=clip_context(page.text, ent.start_char, ent.end_char, 40),
                )
            )
        return hits

    def _keep(self, text: str, entity_type: PIIType) -> bool:
        cleaned = normalize_span_text(text)
        if not cleaned:
            return False
        if entity_type == PIIType.PERSON:
            if self._policy.skip_single_token_persons and token_count(cleaned) < self._policy.person_min_tokens:
                return False
        if entity_type == PIIType.ORGANIZATION and (
            is_allowlisted(cleaned, self._policy.organization_allowlist)
            or is_allowlisted(cleaned, self._policy.generic_org_denylist)
        ):
            return False
        if entity_type == PIIType.LOCATION and is_allowlisted(
            cleaned, self._policy.location_allowlist
        ):
            return False
        return True


class PresidioRecognizer:
    def __init__(self, analyzer: AnalyzerEngine, language: str, policy: PrecisionPolicyConfig) -> None:
        self._analyzer = analyzer
        self._language = language
        self._policy = policy

    def find(self, page: PageContent) -> list[PIIEntity]:
        hits = []
        results = self._analyzer.analyze(
            text=page.text,
            language=self._language,
            entities=PRESIDIO_ENTITIES,
        )
        for result in results:
            entity_type = PRESIDIO_TYPE_MAP.get(result.entity_type)
            if entity_type is None:
                continue
            span = page.text[result.start : result.end]
            if entity_type == PIIType.DATE_TIME:
                continue
            if entity_type == PIIType.ORGANIZATION and is_allowlisted(
                span, self._policy.organization_allowlist
            ):
                continue
            if entity_type == PIIType.ORGANIZATION and is_allowlisted(
                span, self._policy.generic_org_denylist
            ):
                continue
            if entity_type == PIIType.LOCATION and is_allowlisted(
                span, self._policy.location_allowlist
            ):
                continue
            if entity_type == PIIType.PERSON and token_count(span) < 2:
                continue
            hits.append(
                PIIEntity(
                    text=span,
                    entity_type=entity_type,
                    start=result.start,
                    end=result.end,
                    page_number=page.page_number,
                    score=float(result.score),
                    detector=DetectionSource.PRESIDIO,
                    context=clip_context(page.text, result.start, result.end, 40),
                )
            )
        return hits


class PIIDetector:
    def __init__(self, config: AppConfig | None = None) -> None:
        self._config = config or DEFAULT_CONFIG
        self._nlp = self._load_spacy(self._config.detector.spacy_model)
        self._regex = RegexRecognizer(self._config)
        self._spacy = SpacyRecognizer(self._nlp, self._config.precision)
        self._presidio = None
        if self._config.detector.enable_presidio:
            self._presidio = PresidioRecognizer(
                self._build_presidio(self._config.detector),
                self._config.detector.presidio_language,
                self._config.precision,
            )

    @staticmethod
    def _load_spacy(model_name: str) -> Language:
        try:
            logger.info("Loading spaCy model: %s", model_name)
            return spacy.load(model_name, disable=["parser", "lemmatizer", "attribute_ruler"])
        except OSError:
            logger.warning("spaCy model %s not found, falling back to en_core_web_sm", model_name)
            return spacy.load("en_core_web_sm", disable=["parser", "lemmatizer", "attribute_ruler"])

    @staticmethod
    def _build_presidio(detector: DetectorConfig) -> AnalyzerEngine:
        logger.info("Starting Presidio analyzer with %s", detector.spacy_model)
        ner_ignore = [
            "CARDINAL",
            "MONEY",
            "PERCENT",
            "ORDINAL",
            "QUANTITY",
            "EVENT",
            "WORK_OF_ART",
            "LAW",
            "PRODUCT",
            "LANGUAGE",
            "FAC",
        ]
        provider = NlpEngineProvider(
            nlp_configuration={
                "nlp_engine_name": "spacy",
                "models": [{"lang_code": "en", "model_name": detector.spacy_model}],
                "ner_model_configuration": {"labels_to_ignore": ner_ignore},
            }
        )
        try:
            nlp_engine = provider.create_engine()
        except Exception:
            nlp_engine = NlpEngineProvider(
                nlp_configuration={
                    "nlp_engine_name": "spacy",
                    "models": [{"lang_code": "en", "model_name": "en_core_web_sm"}],
                }
            ).create_engine()
        return AnalyzerEngine(nlp_engine=nlp_engine, supported_languages=["en"])

    def detect_document(self, document: ExtractedDocument) -> list[PIIEntity]:
        entities: list[PIIEntity] = []
        for page in document.pages:
            if not page.text:
                continue
            page_hits = self.detect_page(page)
            entities.extend(page_hits)
            if page.page_number == 1 or page.page_number % 15 == 0:
                logger.info(
                    "Page %s/%s: %s hits (running total %s)",
                    page.page_number,
                    document.page_count,
                    len(page_hits),
                    len(entities),
                )
        logger.info("Detected %s PII spans across %s pages", len(entities), document.page_count)
        return entities

    def detect_page(self, page: PageContent) -> list[PIIEntity]:
        raw: list[PIIEntity] = []
        if self._config.detector.enable_regex:
            raw.extend(self._regex.find(page))
        if self._config.detector.enable_spacy:
            raw.extend(self._spacy.find(page))
        if self._presidio is not None:
            raw.extend(self._presidio.find(page))
        filtered = [
            item
            for item in raw
            if item.score >= self._config.detector.threshold_for(item.entity_type)
            and not self._is_noise(item)
        ]
        return resolve_overlaps(filtered)

    def _is_noise(self, entity: PIIEntity) -> bool:
        text = " ".join(entity.text.split())
        if len(text) < 3:
            return True
        key = normalize_for_match(text)
        policy = self._config.precision
        if entity.entity_type == PIIType.ORGANIZATION:
            if is_allowlisted(text, policy.organization_allowlist):
                return True
            if is_allowlisted(text, policy.generic_org_denylist):
                return True
            if token_count(text) == 1 and (text.isupper() or len(text) <= 4):
                return True
            if policy.require_org_legal_hint and not any(hint in key for hint in policy.org_legal_hints):
                return True
        if entity.entity_type == PIIType.PERSON:
            if policy.skip_single_token_persons and token_count(text) < policy.person_min_tokens:
                return True
            if any(ch.isdigit() for ch in text):
                return True
            if any(hint in key for hint in policy.person_place_hints):
                return True
            if any(hint in key for hint in policy.person_noise_hints):
                return True
        if entity.entity_type == PIIType.LOCATION and is_allowlisted(text, policy.location_allowlist):
            return True
        if entity.entity_type == PIIType.DATE_TIME and not self._config.dates.redact_all_dates:
            return True
        return False


def resolve_overlaps(entities: list[PIIEntity]) -> list[PIIEntity]:
    by_page: dict[int, list[PIIEntity]] = defaultdict(list)
    for entity in entities:
        by_page[entity.page_number].append(entity)

    resolved: list[PIIEntity] = []
    for page_entities in by_page.values():
        ranked = sorted(
            page_entities,
            key=lambda item: (
                TYPE_PRIORITY.get(item.entity_type, 0),
                item.span_length,
                item.score,
            ),
            reverse=True,
        )
        kept: list[PIIEntity] = []
        for candidate in ranked:
            if any(candidate.overlaps(existing) for existing in kept):
                continue
            kept.append(candidate)
        resolved.extend(sorted(kept, key=lambda item: item.start))
    return sorted(resolved, key=lambda item: (item.page_number, item.start))
