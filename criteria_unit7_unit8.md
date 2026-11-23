# Acceptance criteria — Provenance Guard

These targets were recorded in Unit 7 after initial implementation and a submission-and-appeal smoke test, but before the full acceptance evaluation.

---

## 1. False positives

Submit 10 English passages that I wrote myself, each containing at least three sentences and between 50 and 150 words. At most 3 responses may return `guess: "ai"`. Responses labeled `unsure` do not count as AI accusations.

Why this target:

My model signal measures predictability, and my style signal measures sentence-length uniformity and vocabulary repetition. Human writing can share these patterns, so I expect some false positives. I chose a maximum of 3 out of 10 as my initial limit; more than that would make the system too quick to accuse genuine human writers.

---

## 2. Score spread

Submit the 10 human-written passages from criterion 1 and 10 AI-generated English passages, each containing at least three sentences and between 50 and 150 words, to POST /submit. Calculate the arithmetic mean of the `confidence` field for each group. The AI-generated group's mean must be at least 0.50 higher than the human-written group's mean. All 20 submissions must return a successful scored response; a rejected submission is not silently excluded.

Why this target:

I want human-written passages to receive substantially more human-like scores than AI-generated passages on average. Since higher combined scores mean more AI-like patterns, the 0.50 gap tests whether my two-signal scoring rule makes a meaningful distinction between the groups. It does not prove authorship.

---

## 3. Label coverage

Submit three different English passages to POST /submit. Across the three responses, `guess` must contain each value exactly once: `human`, `unsure`, and `ai`. Every response must also contain a nonempty `label` explaining the assessment in plain language, with no placeholder text.

Why this target:

I want all three outcomes to be reachable, and I want the label to explain whether the text showed human-like patterns, AI-like patterns, or insufficient evidence to distinguish them.

---

## 4. Appeal path

Submit a valid passage to POST /submit, then send its returned `content_id` and nonempty `reasoning` to POST /appeal. The appeal must return HTTP 200, the same content ID, and `status: "under_review"`. GET /log must show the original decision and a later appeal entry containing the same content ID, the submitted reasoning, and `status: "under_review"`.

Why this target:

A writer whose work was flagged deserves confirmation that their challenge was received and documented. My append-only audit log must preserve the original decision and the appeal so the assessment can be examined, rather than silently erased. Confirmation does not mean a reviewer has already resolved the appeal.

---

## 5. Bad input

Send three requests to POST /submit, each with a valid `creator_id`: one with `text` missing, one with `text: ""`, and one with a text string of 10,001 characters. The first two must return HTTP 400, and the third must return HTTP 413. Each response must contain a nonempty `error` message and must not contain an authorship `guess`.

Why this target:

The service cannot analyze writing that was not provided, so it should tell the writer to supply valid text rather than issue an authorship judgment. The 10,000-character request limit also keeps oversized submissions out of this local-model pipeline.

---

<!--
UNIT 8 REVISION REMINDER

Keep the original criteria when recording evaluation results.

If a criterion cannot be measured or measures the wrong thing, preserve the original wording and add a revision underneath with an explanation.

Do not lower a target simply because the system missed it. Record the miss, diagnose the mechanism, and measure an attempted improvement.
-->