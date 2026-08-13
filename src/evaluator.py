from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass

from .models import ExtractedDocument, PIIEntity
from .utils import dump_json, get_logger, load_json, normalize_for_match

logger = get_logger(__name__)


@dataclass(frozen=True)
class GoldEntity:
    text: str
    entity_type: str
    page_number: int


@dataclass(frozen=True)
class MetricSet:
    precision: float
    recall: float
    f1: float
    accuracy: float
    true_positives: int
    false_positives: int
    false_negatives: int
    support: int


@dataclass(frozen=True)
class EvaluationReport:
    overall: MetricSet
    by_type: dict[str, MetricSet]
    notes: str


def load_gold(path) -> list[GoldEntity]:
    raw = load_json(path)
    gold = []
    for page in raw.get("pages", []):
        page_number = int(page["page_number"])
        for entity in page.get("entities", []):
            gold.append(
                GoldEntity(
                    text=entity["text"],
                    entity_type=entity["entity_type"],
                    page_number=page_number,
                )
            )
    return gold


def _match(predicted: PIIEntity, gold: GoldEntity) -> bool:
    if predicted.entity_type.value != gold.entity_type:
        return False
    left = normalize_for_match(predicted.text)
    right = normalize_for_match(gold.text)
    return left == right or left in right or right in left


def _safe_div(num: float, den: float) -> float:
    if den == 0:
        return 0.0
    return num / den


def _metrics(tp: int, fp: int, fn: int) -> MetricSet:
    precision = _safe_div(tp, tp + fp)
    recall = _safe_div(tp, tp + fn)
    f1 = _safe_div(2 * precision * recall, precision + recall) if (precision + recall) else 0.0
    accuracy = _safe_div(tp, tp + fp + fn)
    return MetricSet(
        precision=round(precision, 4),
        recall=round(recall, 4),
        f1=round(f1, 4),
        accuracy=round(accuracy, 4),
        true_positives=tp,
        false_positives=fp,
        false_negatives=fn,
        support=tp + fn,
    )


def evaluate(predicted: list[PIIEntity], gold: list[GoldEntity]) -> EvaluationReport:
    used_pred: set[int] = set()
    used_gold: set[int] = set()
    tp_types: dict[str, int] = defaultdict(int)

    for g_index, gold_item in enumerate(gold):
        for p_index, pred in enumerate(predicted):
            if p_index in used_pred:
                continue
            if _match(pred, gold_item):
                used_pred.add(p_index)
                used_gold.add(g_index)
                tp_types[gold_item.entity_type] += 1
                break

    fp_types: dict[str, int] = defaultdict(int)
    for p_index, pred in enumerate(predicted):
        if p_index not in used_pred:
            fp_types[pred.entity_type.value] += 1

    fn_types: dict[str, int] = defaultdict(int)
    for g_index, gold_item in enumerate(gold):
        if g_index not in used_gold:
            fn_types[gold_item.entity_type] += 1

    overall = _metrics(len(used_gold), sum(fp_types.values()), sum(fn_types.values()))

    labels = sorted({item.entity_type for item in gold} | {item.entity_type.value for item in predicted})
    by_type = {}
    for label in labels:
        by_type[label] = _metrics(tp_types[label], fp_types[label], fn_types[label])

    logger.info(
        "Eval overall P=%.3f R=%.3f F1=%.3f Acc=%.3f TP=%s FP=%s FN=%s",
        overall.precision,
        overall.recall,
        overall.f1,
        overall.accuracy,
        overall.true_positives,
        overall.false_positives,
        overall.false_negatives,
    )
    return EvaluationReport(
        overall=overall,
        by_type=by_type,
        notes=(
            "Entity-level scores on a manually labeled cover/intro subset. "
            "A prediction counts as TP if type and normalized text match or overlap "
            "(DOCX blocks have no PDF page numbers). "
            "Accuracy is TP / (TP+FP+FN); true negatives are not meaningful for span tagging."
        ),
    )


def report_to_dict(report: EvaluationReport) -> dict:
    return {
        "overall": asdict(report.overall),
        "by_type": {key: asdict(value) for key, value in report.by_type.items()},
        "notes": report.notes,
    }


def write_report(report: EvaluationReport, path) -> None:
    dump_json(path, report_to_dict(report))


def filter_by_pages(entities: list[PIIEntity], page_numbers: set[int]) -> list[PIIEntity]:
    return [item for item in entities if item.page_number in page_numbers]


def _gold_anchor(item: GoldEntity) -> bool:
    if item.entity_type in {"EMAIL_ADDRESS", "PHONE_NUMBER", "URL", "ADDRESS"}:
        return True
    tokens = item.text.split()
    return len(tokens) >= 2 and len(item.text) >= 8


def filter_to_labeled_blocks(
    entities: list[PIIEntity],
    document: ExtractedDocument,
    gold: list[GoldEntity],
) -> list[PIIEntity]:
    needles = [
        normalize_for_match(item.text)
        for item in gold
        if _gold_anchor(item)
    ]
    labeled = set()
    for block in document.pages:
        key = normalize_for_match(block.text)
        if any(needle in key for needle in needles):
            labeled.add(block.page_number)
    return [item for item in entities if item.page_number in labeled]
