"""Experimental text-shape measurements; higher scores mean more AI-like."""

import re
import statistics
import string


def sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [part for part in parts if part.strip()]


def words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", text.lower())


def sentence_length_spread(text: str) -> float:
    """Population standard deviation divided by mean sentence word count."""
    lengths = [
        len(words(sentence))
        for sentence in sentences(text)
        if words(sentence)
    ]
    if len(lengths) < 2:
        return 0.0

    mean_length = statistics.mean(lengths)
    return statistics.pstdev(lengths) / mean_length


def type_token_ratio(text: str) -> float:
    tokens = words(text)
    if not tokens:
        return 0.0
    return len(set(tokens)) / len(tokens)


def punctuation_density(text: str) -> float:
    """Fraction of characters that are ASCII or common typographic punctuation."""
    if not text:
        return 0.0
    punctuation = set(string.punctuation + "—–…“”‘’")
    return sum(character in punctuation for character in text) / len(text)


def style_signal(text: str) -> float:
    tokens = words(text)
    if not tokens:
        return 0.5

    sentence_count = sum(bool(words(part)) for part in sentences(text))
    if sentence_count < 2:
        uniformity = 0.5
    else:
        uniformity = 1.0 - min(sentence_length_spread(text), 1.0)

    repetition = 1.0 - type_token_ratio(text)
    score = 0.6 * uniformity + 0.4 * repetition
    return round(max(0.0, min(1.0, score)), 4)


if __name__ == "__main__":
    import sys

    text = " ".join(sys.argv[1:]) or (
        "The system works well. It handles most cases correctly and provides "
        "good results. Users generally find it easy to use and understand."
    )

    print(f"{len(sentences(text))} sentences, {len(words(text))} words")
    print(f"sentence_length_spread: {sentence_length_spread(text):.4f}")
    print(f"type_token_ratio: {type_token_ratio(text):.4f}")
    print(f"punctuation_density: {punctuation_density(text):.4f}")
    print(f"style_signal: {style_signal(text):.4f}")