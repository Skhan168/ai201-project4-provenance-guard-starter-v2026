# Submission Design

## Submission path

1. Receive a POST /submit request containing text and creator_id.
2. Validate that both fields are non-empty strings; otherwise return a 400 error without scoring.
3. Run detector.py to measure how predictable the writing is to the local language model and obtain an AI-like signal score.

## Signal 1: Local model

Measures: How predictable the wording is to GPT-2, using perplexity.

Why it might help: AI-generated text may use predictable word patterns.

Blind spot: Humans also use simple, predictable language, so this signal can incorrectly flag genuine human writing.

Blind spot: A human may naturally write sentences of similar lengths, so low sentence-length variation could incorrectly flag genuine human writing as AI-generated.
Example: A human-written short story may use sentences of similar lengths for stylistic effect. The detector could mistake that consistent pattern for a sign of AI-generated writing.