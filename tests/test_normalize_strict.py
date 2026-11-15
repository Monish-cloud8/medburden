"""Regression tests: look-alike names must not become a different drug (zero false flags)."""
from src.normalize import RxNavClient, normalize_all, spelling_correction, levenshtein


def test_spelling_never_turns_librium_into_lithium():
    sc = spelling_correction("Librium")
    assert not sc or sc[1] != "lithium"


def test_levenshtein_basic():
    assert levenshtein("exaprin", "nexaprine") == 2


def test_baseline_pairing_accepts_whole_line_but_strict_does_not():
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
    from evaluate import pair_items
    gold = [{"name": "Tylenol PM"}]
    assert pair_items(gold, ["Tylenol PM 2 caplets at bedtime"], lenient=True) == {0: 0}
    assert pair_items(gold, ["Tylenol PM 2 caplets at bedtime"]) == {}
