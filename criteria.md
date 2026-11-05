# Acceptance criteria — Provenance Guard

These targets were recorded in Unit 7 after initial implementation and a
submission-and-appeal smoke test, but before the full acceptance evaluation.


**All five are yours.** None are given.

1. False positives: Submit 10 English passages that I wrote myself, each containing at least three sentences and between 50 and 150 words. At most 3 responses may return `guess: "ai"`. Responses labeled `unsure` do not count as AI accusations.

Reason: My model signal measures predictability, and my style signal measures sentence-length uniformity and vocabulary repetition. Human writing can share these patterns, so I expect some false positives. I chose a maximum of 3 out of 10 as my initial limit; more than that would make the system too quick to accuse genuine human writers.

2. Score spread: Submit the 10 human-written passages from criterion 1 and 10 AI-generated English passages, each containing at least three sentences and between 50 and 150 words, to POST /submit. Calculate the arithmetic mean of the `confidence` field for each group. The AI-generated group's mean must be at least 0.50 higher than the human-written group's mean. All 20 submissions must return a successful scored response; a rejected submission is not silently excluded.

Reason: I want human-written passages to receive substantially more human-like scores than AI-generated passages on average. Since higher combined scores mean more AI-like patterns, the 0.50 gap tests whether my two-signal scoring rule makes a meaningful distinction between the groups. It does not prove authorship.

3. Label coverage: Submit three different English passages to POST /submit. Across the three responses, `guess` must contain each value exactly once: `human`, `unsure`, and `ai`. Every response must also contain a nonempty `label` explaining the assessment in plain language, with no placeholder text.

Reason: I want all three outcomes to be reachable, and I want the label to explain whether the text showed human-like patterns, AI-like patterns, or insufficient evidence to distinguish them.

4. Appeal path: Submit a valid passage to POST /submit, then send its returned `content_id` and nonempty `reasoning` to POST /appeal. The appeal must return HTTP 200, the same content ID, and `status: "under_review"`. GET /log must show the original decision and a later appeal entry containing the same content ID, the submitted reasoning, and `status: "under_review"`.

Reason: A writer whose work was flagged deserves confirmation that their challenge was received and documented. My append-only audit log must preserve the original decision and the appeal so the assessment can be examined, rather than silently erased. Confirmation does not mean a reviewer has already resolved the appeal.

5. Bad input: Send three requests to POST /submit, each with a valid `creator_id`: one with `text` missing, one with `text: ""`, and one with a text string of 10,001 characters. The first two must return HTTP 400, and the third must return HTTP 413. Each response must contain a nonempty `error` message and must not contain an authorship `guess`.

Reason: The service cannot analyze writing that was not provided, so it should tell the writer to supply valid text rather than issue an authorship judgment. The 10,000-character request limit also keeps oversized submissions out of this local-model pipeline.

> Missing your own targets next unit costs you nothing. Setting a target so
> easy you can't miss it does.

---

## Pick numbers you can defend

**Cover at least three of these five areas.** They're prompts, not a form.

| Area | A question it could answer |
|---|---|
| False positives | How often may a human's writing get called AI? |
| Score spread | How far apart should clearly-AI and clearly-human text score? |
| Label coverage | Is every one of your three labels actually reachable? |
| The appeal path | Does an appeal always change status and always get recorded? |
| Bad input | What happens when `text` is missing, empty, or enormous? |

Two things worth knowing before you pick numbers:

- **The expensive mistake is one-sided.** Missing some AI text costs the site a
  little. Accusing a real writer costs that person a lot. A criterion that
  treats both errors as equally bad is describing a system nobody would ship.
- **Unit 8 tests across three trials, and the target has to hold across all
  three.** Your first signal runs a model, so identical input can score
  differently twice. A target of "at most 1 in 10" against trials of 2, 1, 2 is
  a **miss**.

---
## 1.

<!-- Your criterion. It must name a number. -->



**Why this target:**



---

## 2.

<!-- Your criterion. -->



**Why this target:**



---

## 3.

<!-- Your criterion. -->



**Why this target:**



---

## 4.

<!-- Your criterion. -->



**Why this target:**



---

## 5.

<!-- Your criterion. -->



**Why this target:**



---

<!-- ─────────────────────────────────────────────────────────────────────────
     UNIT 8 — read this before you change anything above.

     If a criterion turns out to be BROKEN rather than merely unmet, you can
     revise it, and that earns credit. But never delete or edit the original
     line. Add the revision underneath, like this:

         ## 2. Uncertain cases land in the unsure band

         The system handles uncertain cases well.

         **Why this target:** ...

         > **Revised in unit 8:** Text I judged borderline scores between
         > 0.4 and 0.6 in at least 4 of 5 cases.
         >
         > **Why revised:** "well" gave me nothing to check. I couldn't
         > reach a verdict from it at all.

     That's a revision because the criterion couldn't be MEASURED.

     Lowering a target because you missed it is not a revision, and it costs
     you the point:

         ✗ "At most 1 of 10 of my own pieces flagged as AI" → "at most 3
            of 10", because 1 of 10 turned out to be hard.

     A number you missed stays where it is, gets diagnosed, and gets a fix
     attempted. That's where the points are.
     ───────────────────────────────────────────────────────────────────────── -->
