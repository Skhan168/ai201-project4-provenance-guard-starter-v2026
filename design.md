# Submission Design

## Submission path

1. Receive a POST /submit request containing `text` and `creator_id`.
2. Validate that the request is a JSON object and both fields are non-empty strings. Reject invalid input with HTTP 400, or text longer than 10,000 characters with HTTP 413, without scoring it. Record rejected submissions in the audit log.
3. Run `detector.py::model_signal` to measure predictability using local GPT-2 perplexity and obtain an AI-like score between 0 and 1.
4. Run `stylometry.py::style_signal` to measure sentence-length variation and vocabulary repetition, producing another AI-like score between 0 and 1.
5. Run `scoring.py::combine_signals` to calculate `0.5 * model_score + 0.5 * style_score`.
6. Run `scoring.py::score_to_label` to select the guess and reader-facing label. Create a content ID and log the decision, both signal scores, combined score, label, creator ID, timestamp, and status.
7. Return the content ID, guess, combined score, label, both signal scores, and status. The writer may appeal using the content ID.

## Signal 1: Local model

Measures: How predictable the wording is to GPT-2, using perplexity. Lower perplexity produces a higher AI-like score.

Why it might help: AI-generated text may use predictable word patterns.

Blind spot: Humans also use simple, predictable language, so this signal can incorrectly flag genuine human writing. Unusual wording can make AI-generated writing appear more human-like. Predictability does not establish authorship.

## Signal 2: Style

Measures: Sentence-length spread and type-token ratio. The signal combines sentence uniformity with vocabulary repetition.

Rule: `style_score = 0.6 * sentence_uniformity + 0.4 * vocabulary_repetition`.

Why it might help: Uniform sentence lengths and repeated vocabulary may provide additional AI-like pattern evidence, although these are experimental heuristics.

Blind spot: A human may naturally write sentences of similar lengths, so low sentence-length variation could incorrectly flag genuine human writing as AI-generated. Vocabulary ratio also depends on passage length. Editing words or sentence boundaries can change the score without changing authorship.

Example: A human-written short story may use sentences of similar lengths for stylistic effect. The style signal could mistake that consistent pattern for AI-like writing.

## False-positive scenario

A genuine writer submits a plainly written passage with repeated vocabulary and similar sentence lengths.

For illustration, suppose the model score is 0.80 and the style score is 0.60. The combined score is 0.70. These are hypothetical values, not a measured human-writing result.

Because 0.70 is at or above the 0.65 AI threshold, the response returns `guess: "ai"` and this label:

"This text shows patterns associated with AI-generated writing. This is not proof of AI use. If you wrote it yourself, you can request a review using the content ID."

The writer can send the content ID and their reasoning to POST /appeal. The service preserves the original decision, appends the appeal, and confirms `status: "under_review"`. It does not automatically reverse the score or claim that a reviewer has resolved the appeal.

## Endpoint 1: POST /submit

Request: A JSON object with these fields:

- `text`: non-empty string, no more than 10,000 characters, containing text the detector can score.
- `creator_id`: non-empty string identifying the creator.

Successful response: HTTP 200 with these fields:

- `content_id`: generated UUID string.
- `guess`: `human`, `unsure`, or `ai`.
- `confidence`: combined AI-like score between 0 and 1, not a calibrated authorship probability.
- `label`: full reader-facing assessment.
- `model_score`: model signal between 0 and 1.
- `style_score`: style signal between 0 and 1.
- `status`: `decided`.

Error response: A JSON object containing an `error` string.

- HTTP 400: invalid fields, invalid JSON-object shape, or unscorable text.
- HTTP 413: text exceeds 10,000 characters.
- HTTP 503: a caught detector-loading failure.

Label ranges:

- `human`: score at or below 0.35.
- `unsure`: score greater than 0.35 and less than 0.65.
- `ai`: score at or above 0.65.

## Endpoint 2: POST /appeal

Request: A JSON object with these fields:

- `content_id`: non-empty string matching an existing submission.
- `reasoning`: non-empty string explaining the challenge.

Successful response: HTTP 200 with these fields:

- `content_id`: the appealed submission's ID.
- `status`: `under_review`.
- `message`: confirmation that the appeal was recorded.

Error response: A JSON object containing an `error` string.

- HTTP 400: invalid request shape or missing, empty, or wrongly typed fields.
- HTTP 404: no original decision exists for the content ID.

The appeal is appended to the audit log without overwriting the original decision. Appeal ownership is not authenticated in this implementation.