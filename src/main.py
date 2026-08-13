from __future__ import annotations

import argparse
from pathlib import Path

from .config import DEFAULT_CONFIG, AppConfig
from .detector import PIIDetector
from .evaluator import evaluate, filter_to_labeled_blocks, load_gold, write_report
from .exporter import DocxExporter
from .extractor import extract_docx
from .faker_utils import FakeValueFactory
from .replacer import ReplacementEngine
from .utils import configure_logging, ensure_directory, get_logger

logger = get_logger(__name__)


def run_pipeline(
    input_path: Path,
    output_path: Path,
    config: AppConfig | None = None,
    evaluate_run: bool = True,
) -> None:
    config = config or DEFAULT_CONFIG
    configure_logging(config.logging)
    ensure_directory(config.paths.output_dir)

    logger.info("Extracting %s", input_path)
    document = extract_docx(input_path, config)

    logger.info("Running hybrid PII detection")
    detector = PIIDetector(config)
    entities = detector.detect_document(document)

    logger.info("Replacing PII with consistent fake values")
    engine = ReplacementEngine(FakeValueFactory(config.faker))
    anonymized = engine.anonymize(document, entities)

    exporter = DocxExporter()
    exporter.export(anonymized, output_path, source_path=input_path, engine=engine)
    exporter.export_mapping(anonymized, config.paths.mapping_path)
    exporter.export_entities(anonymized, config.paths.entities_path)

    if evaluate_run and config.paths.gold_path.exists():
        gold = load_gold(config.paths.gold_path)
        subset = filter_to_labeled_blocks(entities, document, gold)
        report = evaluate(subset, gold)
        write_report(report, config.paths.metrics_path)
        logger.info("Wrote evaluation metrics to %s", config.paths.metrics_path)
    elif evaluate_run:
        logger.warning("Gold file not found at %s; skipping evaluation", config.paths.gold_path)

    logger.info("Done. Redacted DOCX: %s", output_path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Detect PII in a DOCX and write a structured redacted DOCX."
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_CONFIG.paths.default_input_path,
        help="Source DOCX",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_CONFIG.paths.default_docx_path,
        help="Destination DOCX",
    )
    parser.add_argument(
        "--skip-eval",
        action="store_true",
        help="Do not score against the labeled subset",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    run_pipeline(
        input_path=args.input,
        output_path=args.output,
        config=AppConfig.from_env(),
        evaluate_run=not args.skip_eval,
    )


if __name__ == "__main__":
    main()
