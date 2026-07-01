"""SearchQA evaluation metrics: Exact Match, F1, and Substring Match.

Normalization follows the SQuAD convention:
  - lowercase
  - remove punctuation
  - remove articles (a, an, the)
  - collapse whitespace

Answer extraction looks for <answer>...</answer> XML tags,
falling back to the last non-empty line of the response.

Opt-in lenient EM
-----------------
Set the env var ``SEARCHQA_LENIENT_EM=1`` (or ``true``/``yes``/``on``) to make
``evaluate()`` report ``em`` using a more permissive normalization that closes
common SQuAD-EM noise: ``&`` ↔ ``and``, ``/`` and ``-`` boundaries, plural →
singular, spelled-out numbers → digits, and standalone middle-initial tokens.
The strict SQuAD EM is always also returned as ``strict_em`` so nothing is lost.
The default behavior (env var unset) is unchanged.
"""
from __future__ import annotations

import os
import re
import string
from collections import Counter


def normalize_answer(s: str) -> str:
    """Normalize answer string (SQuAD convention)."""
    s = s.lower()
    s = "".join(ch for ch in s if ch not in string.punctuation)
    s = re.sub(r"\b(a|an|the)\b", " ", s)
    s = " ".join(s.split())
    return s.strip()


def extract_answer(text: str) -> str:
    """Extract answer from <answer>...</answer> tags.

    Fallback: last non-empty line, then full response stripped.
    """
    matches = re.findall(r"<answer>(.*?)</answer>", text, re.DOTALL | re.IGNORECASE)
    if matches:
        return matches[-1].strip()
    lines = [ln.strip() for ln in text.strip().splitlines() if ln.strip()]
    if lines:
        return lines[-1]
    return text.strip()


def exact_match(prediction: str, gold_answers: list[str]) -> float:
    norm_pred = normalize_answer(prediction)
    for gold in gold_answers:
        if normalize_answer(gold) == norm_pred:
            return 1.0
    return 0.0


def f1_score(prediction: str, gold_answers: list[str]) -> float:
    """Token-level F1 (SQuAD-style), max across all gold answers."""
    norm_pred = normalize_answer(prediction)
    pred_tokens = norm_pred.split()

    if not pred_tokens:
        for gold in gold_answers:
            if not normalize_answer(gold).split():
                return 1.0
        return 0.0

    best_f1 = 0.0
    for gold in gold_answers:
        gold_tokens = normalize_answer(gold).split()
        if not gold_tokens:
            continue
        common = Counter(pred_tokens) & Counter(gold_tokens)
        n_common = sum(common.values())
        if n_common == 0:
            continue
        precision = n_common / len(pred_tokens)
        recall = n_common / len(gold_tokens)
        f1 = 2 * precision * recall / (precision + recall)
        best_f1 = max(best_f1, f1)

    return best_f1


def sub_em(prediction: str, gold_answers: list[str]) -> float:
    """1.0 if any normalized gold is a substring of prediction, or vice versa."""
    norm_pred = normalize_answer(prediction)
    for gold in gold_answers:
        norm_gold = normalize_answer(gold)
        if norm_gold in norm_pred or norm_pred in norm_gold:
            return 1.0
    return 0.0


# ── Lenient (opt-in) normalization ─────────────────────────────────────────
# Designed to catch correct answers that strict SQuAD EM drops purely for
# surface-form reasons. Symmetric: applied to both prediction and gold.

_NUMBER_WORDS = {
    "zero": "0", "one": "1", "two": "2", "three": "3", "four": "4",
    "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9",
    "ten": "10", "eleven": "11", "twelve": "12", "thirteen": "13",
    "fourteen": "14", "fifteen": "15", "sixteen": "16", "seventeen": "17",
    "eighteen": "18", "nineteen": "19", "twenty": "20", "thirty": "30",
    "forty": "40", "fifty": "50", "sixty": "60", "seventy": "70",
    "eighty": "80", "ninety": "90", "hundred": "100", "thousand": "1000",
    "million": "1000000", "billion": "1000000000",
}

# Suffixes whose trailing 's' should NOT be stripped (avoids gas→ga, axis→axi).
_S_KEEP_SUFFIXES = ("ss", "us", "is", "os", "as")


def _singularize(tok: str) -> str:
    """Conservative singularizer (symmetric, applied to both sides)."""
    # cities -> city, currencies -> currency  (but not "days" → "dy")
    if len(tok) >= 5 and tok.endswith("ies") and tok[-4] not in "aeiou":
        return tok[:-3] + "y"
    # currents -> current, propellers -> propeller
    # leave mass/bus/axis/photos/atlas alone via suffix block-list
    if len(tok) >= 4 and tok.endswith("s") and not tok.endswith(_S_KEEP_SUFFIXES):
        return tok[:-1]
    return tok


def _split_separators(s: str) -> str:
    """Turn '&', '/', '-' into word boundaries so tokens line up across forms.

    Without this, SQuAD normalization drops these chars without inserting a
    space, so "Spain & Portugal" → "spain  portugal" but "Spain and Portugal"
    keeps the connector, and "hostile/hostel" collapses to one token.
    """
    return s.replace("&", " and ").replace("/", " ").replace("-", " ")


def lenient_normalize_answer(s: str) -> str:
    """Lenient normalization: SQuAD rules + a few symmetric extras.

    Extras (applied identically to prediction and gold):
      - replace ``&`` with ``and``; replace ``/`` and ``-`` with spaces
      - drop standalone single-letter tokens between alphabetic tokens
        (middle initials: "Harry S Truman" → "Harry Truman"); only when
        the result still has ≥ 1 token
      - map spelled-out numbers (0–20, tens, hundred/thousand/...) to digits
      - conservative singularization (currents → current, cities → city)
    """
    s = s.lower()
    s = _split_separators(s)
    s = "".join(ch for ch in s if ch not in string.punctuation)
    s = re.sub(r"\b(a|an|the)\b", " ", s)
    tokens = s.split()
    if not tokens:
        return ""

    # Number-word → digit (and singularize) per token.
    tokens = [_singularize(_NUMBER_WORDS.get(t, t)) for t in tokens]

    # Drop standalone single-letter tokens (likely middle initials) unless
    # doing so would leave the answer empty (so "S" as a literal answer
    # survives on both sides).
    non_initials = [t for t in tokens if len(t) > 1]
    if non_initials:
        tokens = non_initials

    return " ".join(tokens).strip()


def lenient_exact_match(prediction: str, gold_answers: list[str]) -> float:
    """EM under :func:`lenient_normalize_answer`."""
    norm_pred = lenient_normalize_answer(prediction)
    for gold in gold_answers:
        if lenient_normalize_answer(gold) == norm_pred:
            return 1.0
    return 0.0


def _lenient_em_enabled() -> bool:
    """Whether to report lenient EM in the ``em`` field of :func:`evaluate`."""
    return os.environ.get("SEARCHQA_LENIENT_EM", "").strip().lower() in (
        "1", "true", "yes", "on",
    )


def evaluate(prediction_text: str, gold_answers: list[str]) -> dict:
    """Evaluate a single QA prediction against gold answers.

    Returns dict with: em, strict_em, lenient_em, f1, sub_em,
    predicted_answer, gold_answers.

    ``em`` (and therefore the downstream ``hard`` score) is the strict SQuAD
    EM by default. When ``SEARCHQA_LENIENT_EM`` is set (e.g. via
    ``run.sh --lenient_em``), ``em`` reports the lenient variant instead.
    Both metrics are always present in the returned dict.
    """
    answer = extract_answer(prediction_text)
    strict = exact_match(answer, gold_answers)
    lenient = lenient_exact_match(answer, gold_answers)
    return {
        "em": lenient if _lenient_em_enabled() else strict,
        "strict_em": strict,
        "lenient_em": lenient,
        "f1": f1_score(answer, gold_answers),
        "sub_em": sub_em(answer, gold_answers),
        "predicted_answer": answer,
        "gold_answers": gold_answers,
    }
