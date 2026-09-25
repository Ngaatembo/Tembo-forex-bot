from app.research.book_hypotheses import (
    BookHypothesisSpec,
    EvidenceRequirement,
    build_book_hypotheses,
)


def test_every_book_claim_maps_to_one_structured_hypothesis():
    hypotheses = build_book_hypotheses()
    claim_ids = {h.claim_id for h in hypotheses}
    assert claim_ids == {
        "CANDLE_001", "CANDLE_002", "CANDLE_003", "CANDLE_004", "CANDLE_005",
    }
    assert len({h.hypothesis_id for h in hypotheses}) == len(hypotheses)


def test_book_hypotheses_remain_unvalidated():
    assert all(h.profitability_status == "UNVALIDATED" for h in build_book_hypotheses())


def test_confirmation_and_context_are_explicit():
    hammer = next(h for h in build_book_hypotheses() if h.claim_id == "CANDLE_002")
    assert any(e.pattern == "HAMMER" and e.confirmation_required and e.context == "DOWN" for e in hammer.evidence)
    assert any(e.pattern == "HANGING_MAN" and e.confirmation_required and e.context == "UP" for e in hammer.evidence)


def test_invalid_evidence_kind_is_rejected():
    try:
        EvidenceRequirement("execute_order", "HAMMER", "BULLISH", True, "DOWN")
    except ValueError as exc:
        assert "Unsupported evidence" in str(exc)
    else:
        raise AssertionError("invalid evidence kind was accepted")


def test_invalid_hypothesis_cannot_be_marked_validated():
    try:
        BookHypothesisSpec(
            "x", "CANDLE_001", "BOOK_CANDLESTICK_MATERIAL", "x", "x",
            (EvidenceRequirement("candlestick_pattern", "DOJI", "NEUTRAL", False, "contextual"),),
            profitability_status="VALIDATED",
        )
    except ValueError as exc:
        assert "UNVALIDATED" in str(exc)
    else:
        raise AssertionError("validated book hypothesis was accepted")
