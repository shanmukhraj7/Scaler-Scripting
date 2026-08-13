from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from .models import PIIType


def project_root() -> Path:
    return Path(__file__).resolve().parent.parent


@dataclass(frozen=True, slots=True)
class PathConfig:
    input_dir: Path = field(default_factory=lambda: project_root() / "input")
    output_dir: Path = field(default_factory=lambda: project_root() / "output")
    eval_dir: Path = field(default_factory=lambda: project_root() / "eval")
    default_input_name: str = "Red Herring Prospectus.docx"
    default_output_name: str = "redacted_prospectus.docx"
    mapping_filename: str = "replacement_mapping.json"
    entities_filename: str = "detected_entities.json"
    gold_filename: str = "gold_subset.json"
    metrics_filename: str = "evaluation_metrics.json"

    @property
    def default_input_path(self) -> Path:
        return self.input_dir / self.default_input_name

    @property
    def default_docx_path(self) -> Path:
        return self.output_dir / self.default_output_name

    @property
    def mapping_path(self) -> Path:
        return self.output_dir / self.mapping_filename

    @property
    def entities_path(self) -> Path:
        return self.output_dir / self.entities_filename

    @property
    def gold_path(self) -> Path:
        return self.eval_dir / self.gold_filename

    @property
    def metrics_path(self) -> Path:
        return self.output_dir / self.metrics_filename


@dataclass(frozen=True, slots=True)
class ExtractorConfig:
    sort_blocks: bool = False
    join_hyphenated_linebreaks: bool = True
    repair_pdf_artifacts: bool = True
    keep_empty_pages: bool = True


@dataclass(frozen=True, slots=True)
class DetectorConfig:
    enable_regex: bool = True
    enable_spacy: bool = True
    enable_presidio: bool = True
    spacy_model: str = "en_core_web_sm"
    presidio_language: str = "en"
    default_score_threshold: float = 0.40
    score_thresholds: dict[PIIType, float] = field(
        default_factory=lambda: {
            PIIType.PERSON: 0.50,
            PIIType.ORGANIZATION: 0.55,
            PIIType.LOCATION: 0.50,
            PIIType.ADDRESS: 0.50,
            PIIType.EMAIL_ADDRESS: 0.80,
            PIIType.PHONE_NUMBER: 0.70,
            PIIType.CREDIT_CARD: 0.80,
            PIIType.US_SSN: 0.80,
            PIIType.IP_ADDRESS: 0.80,
            PIIType.DATE_OF_BIRTH: 0.60,
            PIIType.IN_PAN: 0.80,
            PIIType.IN_AADHAAR: 0.80,
        }
    )
    context_window: int = 48
    enable_india_identifiers: bool = True

    def threshold_for(self, entity_type: PIIType) -> float:
        return self.score_thresholds.get(entity_type, self.default_score_threshold)


@dataclass(frozen=True, slots=True)
class DatePolicyConfig:
    redact_all_dates: bool = False
    dob_context_keywords: tuple[str, ...] = (
        "date of birth",
        "d.o.b",
        "dob",
        "born on",
        "born",
        "birth date",
        "birthday",
        "aged",
        "age",
    )


@dataclass(frozen=True, slots=True)
class FakerConfig:
    locale: str = "en_IN"
    seed: int = 42


@dataclass(frozen=True, slots=True)
class LoggingConfig:
    level: str = "INFO"
    fmt: str = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    datefmt: str = "%Y-%m-%d %H:%M:%S"


@dataclass(frozen=True, slots=True)
class PrecisionPolicyConfig:
    organization_allowlist: frozenset[str] = field(
        default_factory=lambda: frozenset(
            {
                "sebi",
                "sebi icdr regulations",
                "bse",
                "bse limited",
                "nse",
                "nsdl",
                "cdsl",
                "rbi",
                "government of india",
                "companies act",
                "companies act, 1956",
                "companies act, 2013",
                "registrar of companies",
                "roc",
                "qualified institutional buyers",
                "non-institutional investors",
                "retail individual investors",
                "book built offer",
                "book running lead managers",
                "stock exchanges",
                "national stock exchange of india limited",
                "national stock exchange of india",
                "securities and exchange board of india",
                "securities and exchange board",
                "the bse limited",
                "bse limited",
                "securities contracts (regulation) rules, 1957",
                "mutual funds",
                "life insurance companies",
                "pension funds",
                "anchor investors",
                "anchor investor portion",
                "qib portion",
                "net qib portion",
                "retail portion",
                "our company",
                "the company",
                "the offer",
                "equity shares",
                "promoter group",
                "promoter selling shareholders",
                "central processing centre",
                "self certified syndicate banks",
                "sponsor banks",
                "designated stock exchange",
                "financial express",
                "jansatta",
                "loksatta",
                "scrr",
                "asba",
                "upi",
                "mutual funds",
                "book running lead manager",
                "lead managers",
            }
        )
    )
    location_allowlist: frozenset[str] = field(
        default_factory=lambda: frozenset(
            {
                "india",
                "usa",
                "uk",
                "united states",
                "united kingdom",
                "europe",
                "asia",
            }
        )
    )
    person_min_tokens: int = 2
    skip_single_token_persons: bool = True
    org_legal_hints: tuple[str, ...] = (
        "limited",
        "ltd",
        "llp",
        "trust",
        "private",
        "pvt",
        "inc",
        "corp",
        "bank",
        "securities",
        "industries",
        "international",
        "company",
    )
    require_org_legal_hint: bool = True
    person_place_hints: tuple[str, ...] = (
        "pune",
        "mumbai",
        "bombay",
        "village",
        "taluka",
        "nagar",
        "road",
        "marg",
        "maharashtra",
    )
    person_noise_hints: tuple[str, ...] = (
        "price",
        "funds",
        "newspaper",
        "circulated",
        "edition",
        "offer",
        "bid",
        "shares",
        "equity",
        "regulation",
        "page",
    )
    generic_org_denylist: frozenset[str] = field(
        default_factory=lambda: frozenset(
            {
                "offer",
                "sale",
                "bonus",
                "company",
                "board",
                "shares",
                "equity",
                "the offer",
                "the company",
                "the equity shares",
                "offer for sale",
                "fresh issue",
                "statutory auditors",
                "promoter selling shareholders",
                "the promoter selling shareholders",
                "split of equity shares",
                "bonus issue",
                "red herring prospectus",
                "this red herring prospectus",
                "the red herring prospectus",
                "prospectus",
                "issuer",
                "bidders",
                "investors",
                "price band",
                "floor price",
                "cap price",
                "offer price",
                "book building process",
                "working days",
                "equity share",
                "face value",
            }
        )
    )


@dataclass(frozen=True, slots=True)
class AppConfig:
    paths: PathConfig = field(default_factory=PathConfig)
    extractor: ExtractorConfig = field(default_factory=ExtractorConfig)
    detector: DetectorConfig = field(default_factory=DetectorConfig)
    dates: DatePolicyConfig = field(default_factory=DatePolicyConfig)
    faker: FakerConfig = field(default_factory=FakerConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    precision: PrecisionPolicyConfig = field(default_factory=PrecisionPolicyConfig)

    @classmethod
    def from_env(cls) -> AppConfig:
        paths = PathConfig()
        detector = DetectorConfig()
        faker = FakerConfig()
        logging_cfg = LoggingConfig()

        input_dir = os.getenv("PII_INPUT_DIR")
        output_dir = os.getenv("PII_OUTPUT_DIR")
        input_name = os.getenv("PII_INPUT_NAME")
        model = os.getenv("PII_SPACY_MODEL")
        locale = os.getenv("PII_FAKER_LOCALE")
        seed = os.getenv("PII_FAKER_SEED")
        log_level = os.getenv("PII_LOG_LEVEL")
        threshold = os.getenv("PII_SCORE_THRESHOLD")

        paths = PathConfig(
            input_dir=Path(input_dir) if input_dir else paths.input_dir,
            output_dir=Path(output_dir) if output_dir else paths.output_dir,
            default_input_name=input_name or paths.default_input_name,
        )
        detector = DetectorConfig(
            spacy_model=model or detector.spacy_model,
            default_score_threshold=(
                float(threshold) if threshold else detector.default_score_threshold
            ),
        )
        faker = FakerConfig(
            locale=locale or faker.locale,
            seed=int(seed) if seed else faker.seed,
        )
        logging_cfg = LoggingConfig(level=(log_level or logging_cfg.level).upper())
        return cls(paths=paths, detector=detector, faker=faker, logging=logging_cfg)


DEFAULT_CONFIG = AppConfig()
