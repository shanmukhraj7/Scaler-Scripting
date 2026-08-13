from src.evaluator import GoldEntity, evaluate
from src.models import DetectionSource, PIIEntity, PIIType


def test_evaluator_counts_tp_fp_fn():
    predicted = [
        PIIEntity("Rashi Patil", PIIType.PERSON, 0, 11, 1, 1.0, DetectionSource.REGEX),
        PIIEntity("Order 123", PIIType.PERSON, 12, 21, 1, 0.6, DetectionSource.SPACY),
    ]
    gold = [
        GoldEntity("Rashi Patil", "PERSON", 1),
        GoldEntity("Rohan Dey", "PERSON", 1),
    ]
    report = evaluate(predicted, gold)
    assert report.overall.true_positives == 1
    assert report.overall.false_positives == 1
    assert report.overall.false_negatives == 1
    assert 0 < report.overall.f1 < 1
