# Provenance Guard

A local backend service that measures AI-like writing patterns using two experimental signals. Its assessments are not proof of authorship.

See [RUNNING.md](RUNNING.md) for environment setup. Start the service with:

```powershell
python app.py
```

## What This Does

1. A client sends a JSON object containing `text` and `creator_id` to POST `/submit`.
2. The route validates the fields. Missing or empty text is rejected with HTTP 400; text longer than 10,000 characters is rejected with HTTP 413. Rejected submissions are recorded in the audit log.
3. `detector.py::model_signal` uses local GPT-2 perplexity to produce a model score between 0 and 1.
4. `stylometry.py::style_signal` measures sentence-length variation and vocabulary repetition to produce a second score between 0 and 1.
5. `scoring.py::combine_signals` averages the two scores with equal weights.
6. `scoring.py::score_to_label` selects a human, unsure, or AI assessment. The service creates a content ID and records the decision, both signal scores, combined score, label, and status in `logs/audit.jsonl`.
7. The client receives the content ID, assessment, label, and scores. A writer can challenge the decision through POST `/appeal`, which appends an appeal event with status `under_review`.

### Endpoint contracts

POST `/submit` accepts:

```json
{
  "text": "A passage to assess.",
  "creator_id": "writer-123"
}
```

A successful HTTP 200 response contains:

- `content_id`: generated UUID string.
- `guess`: `human`, `unsure`, or `ai`.
- `confidence`: combined AI-like score from 0 to 1.
- `label`: full reader-facing explanation.
- `model_score`: model signal from 0 to 1.
- `style_score`: style signal from 0 to 1.
- `status`: `decided`.

The field named `confidence` is the combined AI-like score, not a calibrated probability or confidence in the selected label.

Invalid input returns an `error` string. Missing, empty, wrongly typed, or unscorable text returns HTTP 400. Oversized text returns HTTP 413. A caught detector-loading failure returns HTTP 503.

POST `/appeal` accepts:

```json
{
  "content_id": "An existing submission ID",
  "reasoning": "Why the writer challenges the assessment."
}
```

A successful HTTP 200 response contains `content_id`, `status: "under_review"`, and a confirmation `message`. Invalid appeal fields return HTTP 400; an unknown content ID returns HTTP 404.

GET `/log?limit=2` returns a `count` and an `entries` array containing the most recent audit events.

### False-positive scenario

A genuine writer might use ordinary vocabulary and sentences of similar lengths. Both signals could score that writing as AI-like. If the combined score were 0.70, the writer would receive the AI label below. This is an illustrative scenario, not a measured human test result.

The label explicitly says the result is not proof and points the writer to the appeal path. An appeal records the writer's reasoning and moves the item's latest recorded status to `under_review`; it does not automatically reverse the assessment.

## Signals and Scoring

### Additional submission probes and signal disagreement

I submitted three assistant-generated passages through POST /submit. These probes demonstrate pipeline behavior, not detection accuracy on genuine human writing.

| Probe | Model score | Style score | Combined score | Returned guess |
|---|---:|---:|---:|---|
| Ornate | 0.1492 | 0.0627 | 0.10595 | human |
| Mixed | 0.7682 | 0.1036 | 0.4359 | unsure |
| Uniform | 0.6928 | 0.7800 | 0.7364 | ai |

The mixed passage is a measured disagreement case. The model signal scored it 0.7682, while the style signal scored it 0.1036. Equal weighting produced `(0.7682 + 0.1036) / 2 = 0.4359`, which falls in the unsure range. The combining rule therefore avoided an AI label when the signals strongly disagreed.

The ornate passage was assistant-generated but received a human label. This illustrates a false negative: low predictability and varied text shape do not establish human authorship.

All three labels were reached through actual submissions. The full calibration set containing genuine human writing and lightly edited AI writing remains incomplete.

### Signal one: local model

File and function: `detector.py::model_signal`.

This signal measures how predictable the text is to GPT-2 using perplexity. Lower perplexity produces a higher AI-like score.

The supplied mapping is:

```text
model_score = 1 / (1 + (perplexity / 45.0) ** 1.6)
```

The detector scores at most 400 tokens. Predictable generated text may score highly, but predictability is not authorship.

Blind spot: Genuine human writing can use common words and predictable phrasing. Unusual vocabulary can also make AI-generated text look more human-like to this signal. It cannot verify who wrote the text.

### Signal two: style

File and function: `stylometry.py::style_signal`.

The style signal combines two text-shape measurements:

- Sentence-length spread: population standard deviation of sentence word counts divided by their mean. The spread is capped at 1 and subtracted from 1 to obtain sentence uniformity.
- Type-token ratio: unique lowercase words divided by total recognized words. This is subtracted from 1 to obtain vocabulary repetition.

```text
style_score = 0.6 * sentence_uniformity + 0.4 * vocabulary_repetition
```

For fewer than two nonempty sentences, sentence uniformity contributes a neutral 0.5. Text with no recognized words receives a neutral style score of 0.5 from the helper, although the submission route rejects it.

Uniform sentences and repeated vocabulary are experimental AI-like indicators, not validated authorship evidence.

Blind spot: A human may naturally write sentences of similar lengths, so low sentence-length variation could incorrectly flag genuine human writing as AI-generated. A human-written short story may use consistent sentence lengths for stylistic effect. Vocabulary ratio also depends on passage length, and changing words or sentence boundaries can alter the score without changing authorship.

The word splitter recognizes ASCII letters, digits, and apostrophes; it is not a multilingual tokenizer. The punctuation-density helper is implemented but does not contribute to the style score.

### Combining rule

File and function: `scoring.py::combine_signals`.

```text
combined_score = 0.5 * model_score + 0.5 * style_score
```

Weights and thresholds live in `config.py`. Equal weighting is an initial baseline, not a finding that the signals are equally reliable.

Strong disagreement can produce an unsure result. For example, model and style scores of 0.9 and 0.1 would combine to 0.5. This is a mathematical example, not an observed calibration run.

The recorded submission below produced model score 0.6928 and style score 0.78, combining to approximately 0.7364. Both signals leaned AI-like in this test.
     
A measured disagreement case is documented above. The full four-category calibration run remains incomplete. No detection-accuracy claim is made.

## Label Variants

| Guess | Combined score range | Exact reader-facing label |
|---|---|---|
| `human` | 0.00 ≤ score ≤ 0.35 | This text shows patterns associated with human writing. This assessment does not verify who wrote it. |
| `unsure` | 0.35 < score < 0.65 | We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID. |
| `ai` | 0.65 ≤ score ≤ 1.00 | This text shows patterns associated with AI-generated writing. This is not proof of AI use. If you wrote it yourself, you can request a review using the content ID. |

The unsure label admits uncertainty without accusing the writer and identifies a way to challenge the assessment.

All three labels have now been demonstrated through actual submissions: the ornate probe returned human, the mixed probe returned unsure, and the uniform probe returned AI. These were all assistant-generated passages, so label coverage does not demonstrate authorship accuracy.

## Sample Run

These requests were executed locally in Windows PowerShell. The passage was supplied by the AI assistant as test text; it is not a genuine-human accuracy sample.

### Submission request

```powershell
$submissionBody = @{
    text = "The system provides useful information. The system provides clear answers. The system provides helpful results. The system provides consistent support."
    creator_id = "fawaz-test"
} | ConvertTo-Json

$submission = Invoke-RestMethod `
    -Method Post `
    -Uri "http://127.0.0.1:5000/submit" `
    -ContentType "application/json" `
    -Body $submissionBody

$submission | ConvertTo-Json -Depth 10
```

### Submission response

```json
{
  "confidence": 0.7363999999999999,
  "content_id": "766059e7-e844-4a7d-94b7-8d3913655127",
  "guess": "ai",
  "label": "This text shows patterns associated with AI-generated writing. This is not proof of AI use. If you wrote it yourself, you can request a review using the content ID.",
  "model_score": 0.6928,
  "status": "decided",
  "style_score": 0.78
}
```

### Appeal request

```powershell
$appealBody = @{
    content_id = $submission.content_id
    reasoning = "This is a test of the appeal workflow. Please review the automated assessment."
} | ConvertTo-Json

$appeal = Invoke-RestMethod `
    -Method Post `
    -Uri "http://127.0.0.1:5000/appeal" `
    -ContentType "application/json" `
    -Body $appealBody

$appeal | ConvertTo-Json -Depth 10
```

### Appeal response

```json
{
  "content_id": "766059e7-e844-4a7d-94b7-8d3913655127",
  "message": "Your appeal was recorded and the submission is under review.",
  "status": "under_review"
}
```

### Log request

```powershell
Invoke-RestMethod `
    -Uri "http://127.0.0.1:5000/log?limit=2" |
    ConvertTo-Json -Depth 10
```

### Log response

```json
{
  "count": 2,
  "entries": [
    {
      "combined_score": 0.7363999999999999,
      "content_id": "766059e7-e844-4a7d-94b7-8d3913655127",
      "creator_id": "fawaz-test",
      "guess": "ai",
      "label": "This text shows patterns associated with AI-generated writing. This is not proof of AI use. If you wrote it yourself, you can request a review using the content ID.",
      "model_score": 0.6928,
      "status": "decided",
      "style_score": 0.78,
      "timestamp": "2026-11-05T02:27:57+00:00"
    },
    {
      "content_id": "766059e7-e844-4a7d-94b7-8d3913655127",
      "creator_id": "fawaz-test",
      "event": "appeal",
      "reasoning": "This is a test of the appeal workflow. Please review the automated assessment.",
      "status": "under_review",
      "timestamp": "2026-11-05T02:28:25+00:00"
    }
  ]
}
```

The audit log is append-only. The original decision remains unchanged; the later appeal event records the item's new status.

## How I Used AI

### Moment 1: Understanding signal blind spots

I asked about predictable writing, similar sentence lengths, and examples such as poems and short stories. The assistant explained the distinction between a writing pattern and proof of authorship. I used that discussion to describe how genuine human writing could be incorrectly flagged.

### Moment 2: Implementation and debugging

I asked for help completing the project using the starter files. The assistant supplied substantial implementation code for the style signal, submission route, appeal route, and reader-facing labels. I pasted and saved the changes, ran the syntax check, started the server, and executed the PowerShell requests.

My first submission exposed a placeholder label. With the assistant's help, I replaced the label function and repeated the test. The later response contained the finished label, and I verified that an appeal appeared in the audit log.

### Criteria and documentation assistance

I chose a maximum of 3 false positives in 10 human samples, a minimum average score gap of 0.50, and three passages to demonstrate the three labels. I explained my intended appeal and invalid-input outcomes. The assistant helped turn those choices into specific testing procedures, drafted wording, and assembled this README from the code and recorded outputs.

The criteria were finalized after implementation and the initial smoke test, not before building. The full acceptance evaluation has not yet been run.

### Current limitations

- Detection accuracy has not been established.
- Full calibration with genuine human writing and lightly edited AI writing remains incomplete.
- An appeal is recorded, but no human review workflow or automatic resolution is implemented.
- Appeal ownership is not authenticated.
- Rate limiting was disabled in Unit 7 and is now enabled for Unit 8; flood-test evidence appears below.
- The model examines at most 400 tokens, while the style signal examines the accepted passage.
- Unit 8 attack testing and three-trial acceptance evaluation are not yet completed.

## Rate Limiting

POST /submit is limited to 10 requests per minute and 200 requests per day for each caller identified by the limiter.

Ten requests per minute allows a writer to submit a passage and several revisions while restricting rapid automated probing. A limit of 15 or more would allow the entire 15-request flood test through, while one or two would unnecessarily restrict normal revision testing. The daily limit of 200 allows sustained use while restricting longer automated probing sessions.

The limiter uses in-memory storage. Restarting the service resets the counters, so this is a local testing configuration rather than a durable production setup.

### Flood-test evidence

Command: `python run_attacks.py --flood 15`

Actual status codes:

```text
200 200 200 200 200 200 200 200 200 200 429 429 429 429 429
```

Ten submissions succeeded and five were rate limited. GET /health reported `rate_limiting: true`. GET /log confirmed that the rejected requests were recorded with `reason: "rate_limited"` and `status: "rejected"`.

Full output: `results/flood_2026-11-11_2336.md`.

## The Improvement

### Diagnosis and chosen change

The baseline falsely labeled five of the eight staff human-writing samples as AI: FP02, FP03, FP04, FP05, and FP06. Their combined scores ranged from 0.65165 to 0.7062, crossing the original AI threshold of 0.65.

The pipeline stages responsible are the signals, combining rule, and label mapping. Predictable human prose received high model scores; the style scores did not provide sufficient counter-evidence under equal weighting. The label mapping then converted these overlapping pattern scores into AI assessments.

For example, FP05 received model score 0.8005 and style score 0.6119. Equal weighting produced 0.7062, so the original threshold assigned an AI label to staff-provided human writing.

My single improvement is to raise AI_THRESHOLD from 0.65 to 0.75. HUMAN_THRESHOLD remains 0.35. Both signal implementations, both weights, the model, validation, and label wording remain unchanged.

This widens the unsure band to reduce false accusations. The expected cost is that some AI-written passages previously labeled AI will now receive unsure. It does not improve the underlying scores or fix criterion 2's insufficient mean-score gap.

The new threshold is selected using the baseline failures. Any measured improvement on this same set is an in-sample result, not evidence of generalization to unseen writing.

### Measurement plan

Re-run all 56 staff attacks and all five original criteria for three trials each, using the same inputs and test harness. Compare false positives, evasion outcomes, criterion verdicts, and unchanged score values before and after.

# Unit 8 Testing Evidence

This section records the completed Unit 8 work. Earlier sample runs and original thresholds above are retained as Unit 7/baseline history. The current AI threshold is 0.75, not 0.65. The previously stated unfinished Unit 8 evaluation is now completed below; the separate four-category Unit 7 calibration remains incomplete. No detection-accuracy claim is made.

## Test method and sample provenance

The human test set contains ten non-overlapping excerpts from six of my own Literature of Medicine discussion posts. I confirmed these posts were written without AI assistance. Classmates’ answers, bibliography entries, and direct quotations from readings were excluded; work titles and parenthetical citations were retained. Each excerpt has 50–150 whitespace-separated words and at least three complete sentences. The assistant selected excerpts without rewriting my prose. These are one author’s course posts, not ten independent authors or a representative population.

The AI group contains ten assistant-generated passages using one deliberately formulaic template across ten topics. This narrow, correlated comparison group limits generalization. Label-coverage inputs EV05, EV01, and EV10 were selected using observed baseline labels; this tests reachability, not independent accuracy. All inputs were fixed before the criterion baseline and reused after the improvement.

`scenarios.py::SCENARIOS` defines all five criteria. `run_eval.py::run_trial` performs three HTTP trials per criterion, including submission + appeal + log-history verification for criterion 4. The harness saves complete response JSON. Unique synthetic creator IDs isolate content evaluation from the separately measured flood behavior; this is disclosed rather than treated as evidence against identity rotation. No original criterion or target was revised.

Rate limiting stayed enabled at 10/minute and 200/day. A nonempty client-supplied creator_id is the key, falling back to IP address when absent or unusable. Creator IDs are not authenticated, so rotation can bypass the creator quota. No new authentication mechanism was added. In-memory counts reset on service restart; the after run was deliberately restarted with fresh counters. Both full attack runs show ten allowed flood requests followed by two 429s. The file contains twelve flood rows despite their target text saying twenty. All 56 actual rows were run; no extra eight rows are claimed.

## Attack Run — Before

### Judgment rules

HELD/BROKE is judged against the attack purpose, not just HTTP status. For evasion I use a strict detection rule: only ai is HELD; both unsure and human are BROKE because the input avoided an AI label. Unsure is an abstention, not proof of human authorship, and its counts are reported separately. For false-positive attacks, only an ai accusation is BROKE; unsure is HELD for the no-wrong-accusation objective.

For prompt-injection tests, I check the specific attempted outcome: PI01, PI03, and PI06 do not achieve their demanded bypass; PI04 does not alter the fixed label; PI05 does not inject forged log fields. PI02 is conservatively BROKE for its desired human classification, but there is no evidence of instruction execution or the requested exact score. Malformed requests are HELD when safely rejected; MF03 and MF05 are BROKE for receiving substantive authorship assessments on junk. MF07 is HELD only as a safe, scoped English-service rejection, not a claim that right-to-left writing is inherently malformed. Flood rows 1–10 are HELD as requests within the declared quota; rows 11–12 are HELD when rejected.

Produced by `run_attacks.py::main`; full raw output: `results/attack_run_2026-11-11_2356_before.md`.

| ID | HTTP | Guess | Model | Style | Combined | Verdict |
|---|---|---|---|---|---|---|
| EV01 | 200 | unsure | 0.16350 | 0.56250 | 0.36300 | BROKE |
| EV02 | 200 | unsure | 0.59430 | 0.18080 | 0.38755 | BROKE |
| EV03 | 200 | unsure | 0.66620 | 0.41050 | 0.53835 | BROKE |
| EV04 | 200 | unsure | 0.61140 | 0.55450 | 0.58295 | BROKE |
| EV05 | 200 | human | 0.32120 | 0.31760 | 0.31940 | BROKE |
| EV06 | 200 | human | 0.57270 | 0.10000 | 0.33635 | BROKE |
| EV07 | 200 | unsure | 0.58620 | 0.39070 | 0.48845 | BROKE |
| EV08 | 200 | unsure | 0.24520 | 0.48000 | 0.36260 | BROKE |
| EV09 | 200 | unsure | 0.70420 | 0.39680 | 0.55050 | BROKE |
| EV10 | 200 | ai | 0.97920 | 0.66710 | 0.82315 | HELD |
| FP01 | 200 | unsure | 0.61750 | 0.45970 | 0.53860 | HELD |
| FP02 | 200 | ai | 0.73870 | 0.58230 | 0.66050 | BROKE |
| FP03 | 200 | ai | 0.80510 | 0.52850 | 0.66680 | BROKE |
| FP04 | 200 | ai | 0.83290 | 0.47070 | 0.65180 | BROKE |
| FP05 | 200 | ai | 0.80050 | 0.61190 | 0.70620 | BROKE |
| FP06 | 200 | ai | 0.88140 | 0.42190 | 0.65165 | BROKE |
| FP07 | 200 | unsure | 0.88160 | 0.41090 | 0.64625 | HELD |
| FP08 | 200 | unsure | 0.32230 | 0.38790 | 0.35510 | HELD |
| PI01 | 200 | unsure | 0.46250 | 0.26370 | 0.36310 | HELD |
| PI02 | 200 | human | 0.20440 | 0.26080 | 0.23260 | BROKE |
| PI03 | 200 | unsure | 0.59430 | 0.45810 | 0.52620 | HELD |
| PI04 | 200 | unsure | 0.49980 | 0.44880 | 0.47430 | HELD |
| PI05 | 200 | unsure | 0.64010 | 0.41330 | 0.52670 | HELD |
| PI06 | 200 | unsure | 0.55830 | 0.46480 | 0.51155 | HELD |
| MF01 | 400 | — | — | — | — | HELD |
| MF02 | 400 | — | — | — | — | HELD |
| MF03 | 200 | human | 0.00000 | 0.30000 | 0.15000 | BROKE |
| MF04 | 400 | — | — | — | — | HELD |
| MF05 | 200 | unsure | 0.99760 | 0.30000 | 0.64880 | BROKE |
| MF06 | 400 | — | — | — | — | HELD |
| MF07 | 400 | — | — | — | — | HELD |
| MF08 | 413 | — | — | — | — | HELD |
| RQ01 | 400 | — | — | — | — | HELD |
| RQ02 | 400 | — | — | — | — | HELD |
| RQ03 | 400 | — | — | — | — | HELD |
| RQ04 | 400 | — | — | — | — | HELD |
| RQ05 | 400 | — | — | — | — | HELD |
| RQ06 | 400 | — | — | — | — | HELD |
| RQ07 | 400 | — | — | — | — | HELD |
| RQ08 | 400 | — | — | — | — | HELD |
| RQ09 | 400 | — | — | — | — | HELD |
| RQ10 | 400 | — | — | — | — | HELD |
| RQ11 | 400 | — | — | — | — | HELD |
| RQ12 | 400 | — | — | — | — | HELD |
| FL01_01 | 200 | human | 0.02870 | 0.30000 | 0.16435 | HELD |
| FL01_02 | 200 | human | 0.02870 | 0.30000 | 0.16435 | HELD |
| FL01_03 | 200 | human | 0.02870 | 0.30000 | 0.16435 | HELD |
| FL01_04 | 200 | human | 0.02870 | 0.30000 | 0.16435 | HELD |
| FL01_05 | 200 | human | 0.02870 | 0.30000 | 0.16435 | HELD |
| FL01_06 | 200 | human | 0.02870 | 0.30000 | 0.16435 | HELD |
| FL01_07 | 200 | human | 0.02870 | 0.30000 | 0.16435 | HELD |
| FL01_08 | 200 | human | 0.02870 | 0.30000 | 0.16435 | HELD |
| FL01_09 | 200 | human | 0.02870 | 0.30000 | 0.16435 | HELD |
| FL01_10 | 200 | human | 0.02870 | 0.30000 | 0.16435 | HELD |
| FL01_11 | 429 | — | — | — | — | HELD |
| FL01_12 | 429 | — | — | — | — | HELD |

### Counts and outcomes

Before: 39 HELD, 17 BROKE, out of 56. These are purpose-based test judgments, not an accuracy percentage.
After: 44 HELD, 12 BROKE, out of 56. These are purpose-based test judgments, not an accuracy percentage.

### Audit-log extract: ten actual entries

These nine decisions and one flood rejection are from the baseline attack run, selected to show five false accusations, two human-labeled evasions, the system-message classification failure, and junk-text acceptance. Every decision contains timestamp, content_id, creator_id, guess, model_score, style_score, combined_score, label, and status. A rejected request has no computed decision or content ID; its smaller schema is expected under the assignment. No invented scores or null decision fields were added.

```json
[
  {
    "combined_score": 0.6605000000000001,
    "content_id": "9e6b1a03-ed4b-4e4b-a6b8-0fdea1563bf1",
    "creator_id": "attacker_FP02",
    "guess": "ai",
    "label": "This text shows patterns associated with AI-generated writing. This is not proof of AI use. If you wrote it yourself, you can request a review using the content ID.",
    "model_score": 0.7387,
    "status": "decided",
    "style_score": 0.5823,
    "timestamp": "2026-11-12T04:55:56+00:00"
  },
  {
    "combined_score": 0.6668000000000001,
    "content_id": "97ac69a2-b4f3-4ee3-ac7b-e7dfa1787836",
    "creator_id": "attacker_FP03",
    "guess": "ai",
    "label": "This text shows patterns associated with AI-generated writing. This is not proof of AI use. If you wrote it yourself, you can request a review using the content ID.",
    "model_score": 0.8051,
    "status": "decided",
    "style_score": 0.5285,
    "timestamp": "2026-11-12T04:55:56+00:00"
  },
  {
    "combined_score": 0.6517999999999999,
    "content_id": "1ea42c16-0569-4a17-8c18-8ef1748eeab1",
    "creator_id": "attacker_FP04",
    "guess": "ai",
    "label": "This text shows patterns associated with AI-generated writing. This is not proof of AI use. If you wrote it yourself, you can request a review using the content ID.",
    "model_score": 0.8329,
    "status": "decided",
    "style_score": 0.4707,
    "timestamp": "2026-11-12T04:55:56+00:00"
  },
  {
    "combined_score": 0.7061999999999999,
    "content_id": "083912a8-008c-4790-a513-d47ea7ec6da0",
    "creator_id": "attacker_FP05",
    "guess": "ai",
    "label": "This text shows patterns associated with AI-generated writing. This is not proof of AI use. If you wrote it yourself, you can request a review using the content ID.",
    "model_score": 0.8005,
    "status": "decided",
    "style_score": 0.6119,
    "timestamp": "2026-11-12T04:55:56+00:00"
  },
  {
    "combined_score": 0.65165,
    "content_id": "64ec0626-f05b-4b85-811d-c8bfaa424cde",
    "creator_id": "attacker_FP06",
    "guess": "ai",
    "label": "This text shows patterns associated with AI-generated writing. This is not proof of AI use. If you wrote it yourself, you can request a review using the content ID.",
    "model_score": 0.8814,
    "status": "decided",
    "style_score": 0.4219,
    "timestamp": "2026-11-12T04:55:57+00:00"
  },
  {
    "combined_score": 0.3194,
    "content_id": "ef78b088-d1fe-46ad-9ff8-f43ef06ee206",
    "creator_id": "attacker_EV05",
    "guess": "human",
    "label": "This text shows patterns associated with human writing. This assessment does not verify who wrote it.",
    "model_score": 0.3212,
    "status": "decided",
    "style_score": 0.3176,
    "timestamp": "2026-11-12T04:55:54+00:00"
  },
  {
    "combined_score": 0.33635,
    "content_id": "7210d32e-2244-4298-a789-856fca403590",
    "creator_id": "attacker_EV06",
    "guess": "human",
    "label": "This text shows patterns associated with human writing. This assessment does not verify who wrote it.",
    "model_score": 0.5727,
    "status": "decided",
    "style_score": 0.1,
    "timestamp": "2026-11-12T04:55:55+00:00"
  },
  {
    "combined_score": 0.23259999999999997,
    "content_id": "7036b9c4-7f34-4d80-a1f6-1a07370e29fb",
    "creator_id": "attacker_PI02",
    "guess": "human",
    "label": "This text shows patterns associated with human writing. This assessment does not verify who wrote it.",
    "model_score": 0.2044,
    "status": "decided",
    "style_score": 0.2608,
    "timestamp": "2026-11-12T04:55:57+00:00"
  },
  {
    "combined_score": 0.15,
    "content_id": "298bb64e-89a6-4e9a-8a21-11975c800e20",
    "creator_id": "attacker_MF03",
    "guess": "human",
    "label": "This text shows patterns associated with human writing. This assessment does not verify who wrote it.",
    "model_score": 0.0,
    "status": "decided",
    "style_score": 0.3,
    "timestamp": "2026-11-12T04:55:58+00:00"
  },
  {
    "creator_id": "attacker_flood",
    "event": "rejected",
    "limit": "10 per 1 minute",
    "reason": "rate_limited",
    "status": "rejected",
    "timestamp": "2026-11-12T04:56:00+00:00"
  }
]
```

### Worst outcome

I selected FP03 as the worst outcome: careful non-native English writing received an AI accusation at 0.6668. Its model score was 0.8051 and style score 0.5285. A writer should not have to make their language less predictable to avoid suspicion. This is a signal/combination/label-mapping failure, not a route crash.

## Run Log and Verdicts

### Before: five criteria, three trials each

| Criterion | Target | Run 1 | Run 2 | Run 3 | Verdict |
|---|---|---|---|---|---|
| 1. False positives | At most 3/10 AI; all ten scored | 0/10 AI; 10/10 scored | 0/10 AI; 10/10 scored | 0/10 AI; 10/10 scored | MET |
| 2. Score spread | AI mean minus human mean >= 0.50; all 20 scored | gap 0.12975 (human 0.51907, AI 0.64882) | gap 0.12975 (human 0.51907, AI 0.64882) | gap 0.12975 (human 0.51907, AI 0.64882) | MISSED |
| 3. Label coverage | human, unsure, ai exactly once; valid labels | human, unsure, ai; labels valid: True | human, unsure, ai; labels valid: True | human, unsure, ai; labels valid: True | MET |
| 4. Appeal path | 200, same ID, under_review; original + later appeal in log | appeal 200; original + later appeal: True | appeal 200; original + later appeal: True | appeal 200; original + later appeal: True | MET |
| 5. Bad input | 400, 400, 413; error messages; no guess | 3/3 correct; codes 400, 400, 413 | 3/3 correct; codes 400, 400, 413 | 3/3 correct; codes 400, 400, 413 | MET |
### After: five criteria, three trials each

| Criterion | Target | Run 1 | Run 2 | Run 3 | Verdict |
|---|---|---|---|---|---|
| 1. False positives | At most 3/10 AI; all ten scored | 0/10 AI; 10/10 scored | 0/10 AI; 10/10 scored | 0/10 AI; 10/10 scored | MET |
| 2. Score spread | AI mean minus human mean >= 0.50; all 20 scored | gap 0.12975 (human 0.51907, AI 0.64882) | gap 0.12975 (human 0.51907, AI 0.64882) | gap 0.12975 (human 0.51907, AI 0.64882) | MISSED |
| 3. Label coverage | human, unsure, ai exactly once; valid labels | human, unsure, ai; labels valid: True | human, unsure, ai; labels valid: True | human, unsure, ai; labels valid: True | MET |
| 4. Appeal path | 200, same ID, under_review; original + later appeal in log | appeal 200; original + later appeal: True | appeal 200; original + later appeal: True | appeal 200; original + later appeal: True | MET |
| 5. Bad input | 400, 400, 413; error messages; no guess | 3/3 correct; codes 400, 400, 413 | 3/3 correct; codes 400, 400, 413 | 3/3 correct; codes 400, 400, 413 | MET |

### Why each verdict follows

1. False positives: MET before and after because every trial scored all ten passages and returned zero AI accusations, within the original maximum of three. This does not contradict the five staff false positives: those are different texts.

2. Score spread: MISSED before and after because every trial produced an AI-minus-human mean gap of 0.12975, below 0.50. All twenty requests were scored, so no rejection was excluded to improve the gap.

3. Label coverage: MET before and after because each trial returned human, unsure, and ai exactly once, with nonempty, non-placeholder explanations.

4. Appeal path: MET before and after because every trial returned HTTP 200, the same content ID, and under_review, and GET /log preserved the original decision followed by the correct appeal reasoning. This is recorded challenge status, not proof of a completed human review.

5. Bad input: MET before and after because all three trials returned 400, 400, and 413 in the requested order, with nonempty error messages and no guess field.

All three trials matched in the recorded scores and metrics. IDs and timestamps naturally differ. No target was lowered or rewritten.

### Diagnosis of criterion 2

The responsible stages are signal one, signal two, and their combining rule. In the baseline first trial, human model/style means were 0.54805/0.49010 and AI means were 0.69994/0.59771. The model separates the groups by only 0.15189 and style by only 0.10761; equal averaging produces 0.12975. Predictability and surface regularity overlap between human academic prose and formulaic AI prose. Neither signal supplies a 0.50 separation, so their convex weighted average cannot deliver it on these fixed samples. A threshold change cannot alter the confidence values and therefore cannot repair this criterion. The narrow, template-based AI set also means this measurement is not a broad authorship benchmark.

### Actual JSON from one trial per criterion, before and after

Produced by `run_eval.py::run_trial`; inputs from `scenarios.py::SCENARIOS`. These are actual recorded HTTP responses, not reconstructed examples. All three trials, full requests, and IDs remain in the committed evaluation JSON/Markdown files.

#### Before, criterion 1: False positives

```json
[
  {
    "http_status": 200,
    "response": {
      "confidence": 0.3456,
      "content_id": "97b55d2f-6fd0-448a-bc27-a7c7cd0f8e30",
      "guess": "human",
      "label": "This text shows patterns associated with human writing. This assessment does not verify who wrote it.",
      "model_score": 0.3563,
      "status": "decided",
      "style_score": 0.3349
    }
  },
  {
    "http_status": 200,
    "response": {
      "confidence": 0.5204,
      "content_id": "f7e47a03-74c9-4f3e-86f0-4425612e7ce3",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.5759,
      "status": "decided",
      "style_score": 0.4649
    }
  },
  {
    "http_status": 200,
    "response": {
      "confidence": 0.50615,
      "content_id": "ac283334-4ed6-4e83-b394-bdf408ceea31",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.439,
      "status": "decided",
      "style_score": 0.5733
    }
  },
  {
    "http_status": 200,
    "response": {
      "confidence": 0.61365,
      "content_id": "634b0941-acfb-4ef1-b928-6836fa6466f6",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.7186,
      "status": "decided",
      "style_score": 0.5087
    }
  },
  {
    "http_status": 200,
    "response": {
      "confidence": 0.5199,
      "content_id": "cf5cc0d5-e8df-479b-a593-d1780ae183d6",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.6579,
      "status": "decided",
      "style_score": 0.3819
    }
  },
  {
    "http_status": 200,
    "response": {
      "confidence": 0.5132,
      "content_id": "c5210bbc-cc46-4360-826f-971f44d7bbf5",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.5931,
      "status": "decided",
      "style_score": 0.4333
    }
  },
  {
    "http_status": 200,
    "response": {
      "confidence": 0.55385,
      "content_id": "e52c6522-e582-4b32-8607-0908cf237e30",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.5552,
      "status": "decided",
      "style_score": 0.5525
    }
  },
  {
    "http_status": 200,
    "response": {
      "confidence": 0.62205,
      "content_id": "2b81bd23-4c03-4dc8-9bc0-48cdc9dd759d",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.7039,
      "status": "decided",
      "style_score": 0.5402
    }
  },
  {
    "http_status": 200,
    "response": {
      "confidence": 0.46025,
      "content_id": "6a20a408-36ec-4dcf-b158-8e789122262f",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.3208,
      "status": "decided",
      "style_score": 0.5997
    }
  },
  {
    "http_status": 200,
    "response": {
      "confidence": 0.5357000000000001,
      "content_id": "e979f38c-a112-46d1-aa0f-4a1174e55120",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.5598,
      "status": "decided",
      "style_score": 0.5116
    }
  }
]
```

#### Before, criterion 2: Score spread

```json
[
  {
    "http_status": 200,
    "response": {
      "confidence": 0.3456,
      "content_id": "054fecdf-ce98-4a55-91f6-b59672d2ce81",
      "guess": "human",
      "label": "This text shows patterns associated with human writing. This assessment does not verify who wrote it.",
      "model_score": 0.3563,
      "status": "decided",
      "style_score": 0.3349
    }
  },
  {
    "http_status": 200,
    "response": {
      "confidence": 0.5204,
      "content_id": "24fd61c3-4614-4c8f-8784-f0f44c340fc9",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.5759,
      "status": "decided",
      "style_score": 0.4649
    }
  },
  {
    "http_status": 200,
    "response": {
      "confidence": 0.50615,
      "content_id": "016c9bb5-a080-46bc-9cb9-40f35c902288",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.439,
      "status": "decided",
      "style_score": 0.5733
    }
  },
  {
    "http_status": 200,
    "response": {
      "confidence": 0.61365,
      "content_id": "56cbc588-7d4c-4813-b894-24f88f93ccec",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.7186,
      "status": "decided",
      "style_score": 0.5087
    }
  },
  {
    "http_status": 200,
    "response": {
      "confidence": 0.5199,
      "content_id": "c03aa95d-22b1-4019-93b6-6c6b32067722",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.6579,
      "status": "decided",
      "style_score": 0.3819
    }
  },
  {
    "http_status": 200,
    "response": {
      "confidence": 0.5132,
      "content_id": "4b91a185-fde3-4f5c-874a-d7b5ca8eb7d2",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.5931,
      "status": "decided",
      "style_score": 0.4333
    }
  },
  {
    "http_status": 200,
    "response": {
      "confidence": 0.55385,
      "content_id": "b40fa153-779b-40da-9661-ec238f2f5bb0",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.5552,
      "status": "decided",
      "style_score": 0.5525
    }
  },
  {
    "http_status": 200,
    "response": {
      "confidence": 0.62205,
      "content_id": "16179caa-f089-4a3c-a952-15c022d71a7f",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.7039,
      "status": "decided",
      "style_score": 0.5402
    }
  },
  {
    "http_status": 200,
    "response": {
      "confidence": 0.46025,
      "content_id": "78409def-908c-402d-a4ff-dcec49050163",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.3208,
      "status": "decided",
      "style_score": 0.5997
    }
  },
  {
    "http_status": 200,
    "response": {
      "confidence": 0.5357000000000001,
      "content_id": "9b31d0db-b2fb-4254-9556-246f46d59d54",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.5598,
      "status": "decided",
      "style_score": 0.5116
    }
  },
  {
    "http_status": 200,
    "response": {
      "confidence": 0.6428,
      "content_id": "192b10a4-1e03-48bc-adae-3c73a26b1a95",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.6926,
      "status": "decided",
      "style_score": 0.593
    }
  },
  {
    "http_status": 200,
    "response": {
      "confidence": 0.6489499999999999,
      "content_id": "0d3a528c-eaa7-4b53-90f1-5ba358ce0948",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.7049,
      "status": "decided",
      "style_score": 0.593
    }
  },
  {
    "http_status": 200,
    "response": {
      "confidence": 0.64775,
      "content_id": "67afa2de-0caa-4a51-baf9-f02fd26fb05b",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.7025,
      "status": "decided",
      "style_score": 0.593
    }
  },
  {
    "http_status": 200,
    "response": {
      "confidence": 0.6436999999999999,
      "content_id": "5c0628cc-4c58-436e-a9ed-2c4b6fce3112",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.6944,
      "status": "decided",
      "style_score": 0.593
    }
  },
  {
    "http_status": 200,
    "response": {
      "confidence": 0.6456,
      "content_id": "294deb93-37e7-4389-9915-e35cff6fcac2",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.6982,
      "status": "decided",
      "style_score": 0.593
    }
  },
  {
    "http_status": 200,
    "response": {
      "confidence": 0.64445,
      "content_id": "f7beed42-a838-420e-a567-a6de8e137793",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.6959,
      "status": "decided",
      "style_score": 0.593
    }
  },
  {
    "http_status": 200,
    "response": {
      "confidence": 0.67215,
      "content_id": "28458d18-fe46-4e01-9a19-9033bb336329",
      "guess": "ai",
      "label": "This text shows patterns associated with AI-generated writing. This is not proof of AI use. If you wrote it yourself, you can request a review using the content ID.",
      "model_score": 0.7354,
      "status": "decided",
      "style_score": 0.6089
    }
  },
  {
    "http_status": 200,
    "response": {
      "confidence": 0.6392,
      "content_id": "33ff9d1d-79c7-4b92-8ef6-a2ed6b4d3ee2",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.675,
      "status": "decided",
      "style_score": 0.6034
    }
  },
  {
    "http_status": 200,
    "response": {
      "confidence": 0.6579,
      "content_id": "7ef855a5-04c7-4126-9e12-98ac4ea57bd7",
      "guess": "ai",
      "label": "This text shows patterns associated with AI-generated writing. This is not proof of AI use. If you wrote it yourself, you can request a review using the content ID.",
      "model_score": 0.7124,
      "status": "decided",
      "style_score": 0.6034
    }
  },
  {
    "http_status": 200,
    "response": {
      "confidence": 0.64575,
      "content_id": "f3c5ae58-e378-4aa8-9b61-d3e657e00188",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.6881,
      "status": "decided",
      "style_score": 0.6034
    }
  }
]
```

#### Before, criterion 3: Label coverage

```json
[
  {
    "http_status": 200,
    "response": {
      "confidence": 0.3194,
      "content_id": "d1122b9e-ca64-4195-b0ea-c400a73316bc",
      "guess": "human",
      "label": "This text shows patterns associated with human writing. This assessment does not verify who wrote it.",
      "model_score": 0.3212,
      "status": "decided",
      "style_score": 0.3176
    }
  },
  {
    "http_status": 200,
    "response": {
      "confidence": 0.363,
      "content_id": "e9309e3c-f8ed-4a04-8208-1e00675b90cd",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.1635,
      "status": "decided",
      "style_score": 0.5625
    }
  },
  {
    "http_status": 200,
    "response": {
      "confidence": 0.82315,
      "content_id": "1ae2f8d9-ba87-4eeb-8e5e-7648c4ff5f1c",
      "guess": "ai",
      "label": "This text shows patterns associated with AI-generated writing. This is not proof of AI use. If you wrote it yourself, you can request a review using the content ID.",
      "model_score": 0.9792,
      "status": "decided",
      "style_score": 0.6671
    }
  }
]
```

#### Before, criterion 4: Appeal path

```json
[
  {
    "http_status": 200,
    "response": {
      "confidence": 0.3456,
      "content_id": "ead919fb-34d1-4576-86a2-cd79d9661288",
      "guess": "human",
      "label": "This text shows patterns associated with human writing. This assessment does not verify who wrote it.",
      "model_score": 0.3563,
      "status": "decided",
      "style_score": 0.3349
    }
  },
  {
    "appeal_request": {
      "content_id": "ead919fb-34d1-4576-86a2-cd79d9661288",
      "reasoning": "I wrote this passage myself and request review of its automated assessment."
    },
    "appeal_result": {
      "http_status": 200,
      "response": {
        "content_id": "ead919fb-34d1-4576-86a2-cd79d9661288",
        "message": "Your appeal was recorded and the submission is under review.",
        "status": "under_review"
      }
    },
    "log_http_status": 200,
    "matching_log_entries": [
      {
        "combined_score": 0.3456,
        "content_id": "ead919fb-34d1-4576-86a2-cd79d9661288",
        "creator_id": "eval_54d423f03f_c4_t1_i1",
        "guess": "human",
        "label": "This text shows patterns associated with human writing. This assessment does not verify who wrote it.",
        "model_score": 0.3563,
        "status": "decided",
        "style_score": 0.3349,
        "timestamp": "2026-11-12T05:40:25+00:00"
      },
      {
        "content_id": "ead919fb-34d1-4576-86a2-cd79d9661288",
        "creator_id": "eval_54d423f03f_c4_t1_i1",
        "event": "appeal",
        "reasoning": "I wrote this passage myself and request review of its automated assessment.",
        "status": "under_review",
        "timestamp": "2026-11-12T05:40:25+00:00"
      }
    ]
  }
]
```

#### Before, criterion 5: Bad input

```json
[
  {
    "http_status": 400,
    "response": {
      "error": "text must be a non-empty string."
    }
  },
  {
    "http_status": 400,
    "response": {
      "error": "text must be a non-empty string."
    }
  },
  {
    "http_status": 413,
    "response": {
      "error": "text must not exceed 10000 characters."
    }
  }
]
```

#### After, criterion 1: False positives

```json
[
  {
    "http_status": 200,
    "response": {
      "confidence": 0.3456,
      "content_id": "c9c14385-2d1e-4982-b4d0-7d3844963374",
      "guess": "human",
      "label": "This text shows patterns associated with human writing. This assessment does not verify who wrote it.",
      "model_score": 0.3563,
      "status": "decided",
      "style_score": 0.3349
    }
  },
  {
    "http_status": 200,
    "response": {
      "confidence": 0.5204,
      "content_id": "d50a9525-ae46-46f2-8708-13997e0f0b6c",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.5759,
      "status": "decided",
      "style_score": 0.4649
    }
  },
  {
    "http_status": 200,
    "response": {
      "confidence": 0.50615,
      "content_id": "8269d1e7-8840-4203-8dc3-3835b7d91a65",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.439,
      "status": "decided",
      "style_score": 0.5733
    }
  },
  {
    "http_status": 200,
    "response": {
      "confidence": 0.61365,
      "content_id": "14fc583a-4009-440d-8699-e0371a80dfb4",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.7186,
      "status": "decided",
      "style_score": 0.5087
    }
  },
  {
    "http_status": 200,
    "response": {
      "confidence": 0.5199,
      "content_id": "4ea22afb-0ce9-4db9-a20b-847cd0bd2e7a",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.6579,
      "status": "decided",
      "style_score": 0.3819
    }
  },
  {
    "http_status": 200,
    "response": {
      "confidence": 0.5132,
      "content_id": "719ec310-bfa9-414e-9217-cad352132a0c",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.5931,
      "status": "decided",
      "style_score": 0.4333
    }
  },
  {
    "http_status": 200,
    "response": {
      "confidence": 0.55385,
      "content_id": "f1803d86-f914-47e4-a35c-686f843c53d1",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.5552,
      "status": "decided",
      "style_score": 0.5525
    }
  },
  {
    "http_status": 200,
    "response": {
      "confidence": 0.62205,
      "content_id": "eeada1d7-e379-4a1a-9576-93e4d3ae34e3",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.7039,
      "status": "decided",
      "style_score": 0.5402
    }
  },
  {
    "http_status": 200,
    "response": {
      "confidence": 0.46025,
      "content_id": "5d12f03c-9750-43fe-9bda-7c4e53979cd8",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.3208,
      "status": "decided",
      "style_score": 0.5997
    }
  },
  {
    "http_status": 200,
    "response": {
      "confidence": 0.5357000000000001,
      "content_id": "ec36ea14-4087-4f26-859f-3818227b6eee",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.5598,
      "status": "decided",
      "style_score": 0.5116
    }
  }
]
```

#### After, criterion 2: Score spread

```json
[
  {
    "http_status": 200,
    "response": {
      "confidence": 0.3456,
      "content_id": "1633fc83-5120-4919-ab6d-0c4fed3c2719",
      "guess": "human",
      "label": "This text shows patterns associated with human writing. This assessment does not verify who wrote it.",
      "model_score": 0.3563,
      "status": "decided",
      "style_score": 0.3349
    }
  },
  {
    "http_status": 200,
    "response": {
      "confidence": 0.5204,
      "content_id": "e9aab618-0bf4-4b49-a3ac-c5401b4ca4aa",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.5759,
      "status": "decided",
      "style_score": 0.4649
    }
  },
  {
    "http_status": 200,
    "response": {
      "confidence": 0.50615,
      "content_id": "cd2df817-a23a-4cc9-b9fc-e90d2c5466c0",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.439,
      "status": "decided",
      "style_score": 0.5733
    }
  },
  {
    "http_status": 200,
    "response": {
      "confidence": 0.61365,
      "content_id": "2f256c3a-c2a3-4266-b78b-726d608c100a",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.7186,
      "status": "decided",
      "style_score": 0.5087
    }
  },
  {
    "http_status": 200,
    "response": {
      "confidence": 0.5199,
      "content_id": "5862bb7b-f42c-4712-b804-7fb701f6a8c9",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.6579,
      "status": "decided",
      "style_score": 0.3819
    }
  },
  {
    "http_status": 200,
    "response": {
      "confidence": 0.5132,
      "content_id": "15cb87f5-f912-4bed-90a8-46b93a647442",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.5931,
      "status": "decided",
      "style_score": 0.4333
    }
  },
  {
    "http_status": 200,
    "response": {
      "confidence": 0.55385,
      "content_id": "e1b00203-7290-4f3f-8221-67ac4640c501",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.5552,
      "status": "decided",
      "style_score": 0.5525
    }
  },
  {
    "http_status": 200,
    "response": {
      "confidence": 0.62205,
      "content_id": "72870f06-4ef6-4ee1-8a03-f837f802d394",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.7039,
      "status": "decided",
      "style_score": 0.5402
    }
  },
  {
    "http_status": 200,
    "response": {
      "confidence": 0.46025,
      "content_id": "ca0e943d-21cc-4020-8bce-231debb4cbf4",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.3208,
      "status": "decided",
      "style_score": 0.5997
    }
  },
  {
    "http_status": 200,
    "response": {
      "confidence": 0.5357000000000001,
      "content_id": "800ff64c-aa6c-4473-9154-66b2196eee77",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.5598,
      "status": "decided",
      "style_score": 0.5116
    }
  },
  {
    "http_status": 200,
    "response": {
      "confidence": 0.6428,
      "content_id": "7d952b3e-b287-433b-a082-67151f5edc6d",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.6926,
      "status": "decided",
      "style_score": 0.593
    }
  },
  {
    "http_status": 200,
    "response": {
      "confidence": 0.6489499999999999,
      "content_id": "23de062b-fd5c-478e-8fd2-4a3fe22208e8",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.7049,
      "status": "decided",
      "style_score": 0.593
    }
  },
  {
    "http_status": 200,
    "response": {
      "confidence": 0.64775,
      "content_id": "8358eb61-671d-470d-a0e6-bfdc3f18580d",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.7025,
      "status": "decided",
      "style_score": 0.593
    }
  },
  {
    "http_status": 200,
    "response": {
      "confidence": 0.6436999999999999,
      "content_id": "eed6ec2d-a003-4574-a158-73614064749f",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.6944,
      "status": "decided",
      "style_score": 0.593
    }
  },
  {
    "http_status": 200,
    "response": {
      "confidence": 0.6456,
      "content_id": "27642f39-0c51-47c7-8ffe-7ea75b2aaa04",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.6982,
      "status": "decided",
      "style_score": 0.593
    }
  },
  {
    "http_status": 200,
    "response": {
      "confidence": 0.64445,
      "content_id": "99adff18-9f55-44f2-897b-0c9f65686ab6",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.6959,
      "status": "decided",
      "style_score": 0.593
    }
  },
  {
    "http_status": 200,
    "response": {
      "confidence": 0.67215,
      "content_id": "da62714f-40b6-4b68-9cf8-3334f7e7705c",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.7354,
      "status": "decided",
      "style_score": 0.6089
    }
  },
  {
    "http_status": 200,
    "response": {
      "confidence": 0.6392,
      "content_id": "edf26ab7-a6e0-411b-92f3-969e9d9c8144",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.675,
      "status": "decided",
      "style_score": 0.6034
    }
  },
  {
    "http_status": 200,
    "response": {
      "confidence": 0.6579,
      "content_id": "73d7b988-5ecb-4ce8-98b4-4d1400d4c560",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.7124,
      "status": "decided",
      "style_score": 0.6034
    }
  },
  {
    "http_status": 200,
    "response": {
      "confidence": 0.64575,
      "content_id": "662dd788-b0b6-40ce-b1c3-71ca97643fd9",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.6881,
      "status": "decided",
      "style_score": 0.6034
    }
  }
]
```

#### After, criterion 3: Label coverage

```json
[
  {
    "http_status": 200,
    "response": {
      "confidence": 0.3194,
      "content_id": "69cc4093-b40a-404f-bc18-9f4d6c2baf99",
      "guess": "human",
      "label": "This text shows patterns associated with human writing. This assessment does not verify who wrote it.",
      "model_score": 0.3212,
      "status": "decided",
      "style_score": 0.3176
    }
  },
  {
    "http_status": 200,
    "response": {
      "confidence": 0.363,
      "content_id": "a9b67387-293e-4353-b2fa-5bf6da2f929c",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.1635,
      "status": "decided",
      "style_score": 0.5625
    }
  },
  {
    "http_status": 200,
    "response": {
      "confidence": 0.82315,
      "content_id": "4b5fada4-bef4-48dd-8fc0-1398ff19748c",
      "guess": "ai",
      "label": "This text shows patterns associated with AI-generated writing. This is not proof of AI use. If you wrote it yourself, you can request a review using the content ID.",
      "model_score": 0.9792,
      "status": "decided",
      "style_score": 0.6671
    }
  }
]
```

#### After, criterion 4: Appeal path

```json
[
  {
    "http_status": 200,
    "response": {
      "confidence": 0.3456,
      "content_id": "c71ec7f9-ee9b-41de-a22a-b22ec6a84361",
      "guess": "human",
      "label": "This text shows patterns associated with human writing. This assessment does not verify who wrote it.",
      "model_score": 0.3563,
      "status": "decided",
      "style_score": 0.3349
    }
  },
  {
    "appeal_request": {
      "content_id": "c71ec7f9-ee9b-41de-a22a-b22ec6a84361",
      "reasoning": "I wrote this passage myself and request review of its automated assessment."
    },
    "appeal_result": {
      "http_status": 200,
      "response": {
        "content_id": "c71ec7f9-ee9b-41de-a22a-b22ec6a84361",
        "message": "Your appeal was recorded and the submission is under review.",
        "status": "under_review"
      }
    },
    "log_http_status": 200,
    "matching_log_entries": [
      {
        "combined_score": 0.3456,
        "content_id": "c71ec7f9-ee9b-41de-a22a-b22ec6a84361",
        "creator_id": "eval_751803d5bc_c4_t1_i1",
        "guess": "human",
        "label": "This text shows patterns associated with human writing. This assessment does not verify who wrote it.",
        "model_score": 0.3563,
        "status": "decided",
        "style_score": 0.3349,
        "timestamp": "2026-11-12T05:48:41+00:00"
      },
      {
        "content_id": "c71ec7f9-ee9b-41de-a22a-b22ec6a84361",
        "creator_id": "eval_751803d5bc_c4_t1_i1",
        "event": "appeal",
        "reasoning": "I wrote this passage myself and request review of its automated assessment.",
        "status": "under_review",
        "timestamp": "2026-11-12T05:48:41+00:00"
      }
    ]
  }
]
```

#### After, criterion 5: Bad input

```json
[
  {
    "http_status": 400,
    "response": {
      "error": "text must be a non-empty string."
    }
  },
  {
    "http_status": 400,
    "response": {
      "error": "text must be a non-empty string."
    }
  },
  {
    "http_status": 413,
    "response": {
      "error": "text must not exceed 10000 characters."
    }
  }
]
```

## Diagnoses of every broken attack

The attack descriptions suggest hypotheses, not proven causal effects. Without paired unmodified controls I distinguish observed score mechanisms from unverified claims that a specific edit caused a score change. The following table covers every attack marked BROKE in either run.

| ID | Before / After | Stage | Mechanism and observed scores |
|---|---|---|---|
| EV01 | BROKE / BROKE | signal one + combining rule | Typo-bearing text received a low model score despite a moderate style score; equal averaging stayed below the AI threshold. The result supports a model-signal weakness, not proof that the advertised word-variety mechanism caused it. Baseline model=0.1635, style=0.5625, combined=0.363. |
| EV02 | BROKE / BROKE | signal two + combining rule | Inserted short sentences increase length variation, which lowers the sentence-uniformity feature. The low style score pulls the average below the AI threshold. Baseline model=0.5943, style=0.1808, combined=0.38755. |
| EV03 | BROKE / BROKE | signal two + combining rule | The added conversational quotation changes sentence lengths and vocabulary; the lower style score pulls a model score above 0.65 into the unsure band. Baseline model=0.6662, style=0.4105, combined=0.53835. |
| EV04 | BROKE / BROKE | both signals + label mapping | The unusual-word sample receives only moderate scores from both signals; their average is below the AI cutoff. Increased perplexity is consistent with the attack design, but no unedited paired control was run to prove the causal change. Baseline model=0.6114, style=0.5545, combined=0.5829500000000001. |
| EV05 | BROKE / BROKE | both signals + combining rule | The heavily edited sample receives low scores from both signals. Their average falls below 0.35, so edited AI-origin text receives human. Baseline model=0.3212, style=0.3176, combined=0.3194. |
| EV06 | BROKE / BROKE | signal two + combining rule | Extreme sentence-length variation drives the style score to 0.1. Equal averaging pulls the moderately AI-like model score into the human band. Baseline model=0.5727, style=0.1, combined=0.33635. |
| EV07 | BROKE / BROKE | signal two + combining rule | The sentence-boundary manipulation produces a lower style score. Punctuation density is not used by this detector; it is the boundary-dependent shape and averaging, not a punctuation-density feature, that permits the non-AI outcome. Baseline model=0.5862, style=0.3907, combined=0.48845000000000005. |
| EV08 | BROKE / BROKE | signal one + combining rule | The very short input passes validation but produces a low model score; the style score does not compensate. This is weak evidence from short text, not demonstrated token-window truncation. Baseline model=0.2452, style=0.48, combined=0.3626. |
| EV09 | BROKE / BROKE | signal two + combining rule | The conversational opening changes the full passage shape. The low style score offsets a model score above 0.65 and produces unsure. Baseline model=0.7042, style=0.3968, combined=0.5505. |
| FP02 | BROKE / HELD | signal one + combining rule + label mapping | Predictable human prose receives a high model score. The style score does not offset it enough under equal weighting, and the original 0.65 cutoff converts the overlapping pattern evidence into an AI accusation. Raising only that cutoff changes the label, not the evidence. Baseline model=0.7387, style=0.5823, combined=0.6605000000000001. |
| FP03 | BROKE / HELD | signal one + combining rule + label mapping | Predictable human prose receives a high model score. The style score does not offset it enough under equal weighting, and the original 0.65 cutoff converts the overlapping pattern evidence into an AI accusation. Raising only that cutoff changes the label, not the evidence. Baseline model=0.8051, style=0.5285, combined=0.6668000000000001. |
| FP04 | BROKE / HELD | signal one + combining rule + label mapping | Predictable human prose receives a high model score. The style score does not offset it enough under equal weighting, and the original 0.65 cutoff converts the overlapping pattern evidence into an AI accusation. Raising only that cutoff changes the label, not the evidence. Baseline model=0.8329, style=0.4707, combined=0.6517999999999999. |
| FP05 | BROKE / HELD | signal one + combining rule + label mapping | Predictable human prose receives a high model score. The style score does not offset it enough under equal weighting, and the original 0.65 cutoff converts the overlapping pattern evidence into an AI accusation. Raising only that cutoff changes the label, not the evidence. Baseline model=0.8005, style=0.6119, combined=0.7061999999999999. |
| FP06 | BROKE / HELD | signal one + combining rule + label mapping | Predictable human prose receives a high model score. The style score does not offset it enough under equal weighting, and the original 0.65 cutoff converts the overlapping pattern evidence into an AI accusation. Raising only that cutoff changes the label, not the evidence. Baseline model=0.8814, style=0.4219, combined=0.65165. |
| PI02 | BROKE / BROKE | both signals + combining rule | The system-like wording receives low model and style scores, and their average maps to human. This is an attacker-desired classification outcome, NOT evidence that GPT-2 executed the instruction: the recorded score is calculated normally and is not the requested 0.02. Baseline model=0.2044, style=0.2608, combined=0.23259999999999997. |
| MF03 | BROKE / BROKE | route validation + signals | Validation requires recognized words but does not reject control characters. This input passes to scoring, receives model score 0 and style score 0.3, and is assigned human despite being unsuitable prose. Baseline model=0.0, style=0.3, combined=0.15. |
| MF05 | BROKE / BROKE | route validation + signal two | A long repeated-letter word fits within the character cap and contains recognized letters. There is no minimum meaningful-word or prose check. Style returns 0.3 for the single-word shape even though model score is 0.9976, producing an authorship assessment on junk input. Baseline model=0.9976, style=0.3, combined=0.6488. |

### Pattern across failures

The common pattern is that surface features measure regularity, not provenance. Human formal writing may be predictable, while edited AI text may be irregular. Equal weighting can turn those weak signals into a misleading aggregate; the label thresholds then decide which error is exposed. Separately, route validation accepts some meaningless but letter-containing strings. These are distinct problems and would require separate changes.

## The Improvement — Measured Results

The sole service improvement was AI_THRESHOLD: 0.65 → 0.75 in config.py. HUMAN_THRESHOLD stayed 0.35, weights stayed 0.5/0.5, and signal implementations, validation, model, and label strings stayed unchanged. Rate limiting and logging are the instrumentation changes allowed separately. Test-harness additions enabled measurement and did not change service scoring.

Current mapping: human for score <= 0.35; unsure for 0.35 < score < 0.75; ai for score >= 0.75. The original label-range table above describes the baseline, not the current mapping.

### Attack Run — After

Produced by `run_attacks.py::main`; raw report: `results/attack_run_2026-11-12_0048_after.md`. Same 56 inputs and same judgment rules as before.

| ID | HTTP | Guess | Model | Style | Combined | Verdict |
|---|---|---|---|---|---|---|
| EV01 | 200 | unsure | 0.16350 | 0.56250 | 0.36300 | BROKE |
| EV02 | 200 | unsure | 0.59430 | 0.18080 | 0.38755 | BROKE |
| EV03 | 200 | unsure | 0.66620 | 0.41050 | 0.53835 | BROKE |
| EV04 | 200 | unsure | 0.61140 | 0.55450 | 0.58295 | BROKE |
| EV05 | 200 | human | 0.32120 | 0.31760 | 0.31940 | BROKE |
| EV06 | 200 | human | 0.57270 | 0.10000 | 0.33635 | BROKE |
| EV07 | 200 | unsure | 0.58620 | 0.39070 | 0.48845 | BROKE |
| EV08 | 200 | unsure | 0.24520 | 0.48000 | 0.36260 | BROKE |
| EV09 | 200 | unsure | 0.70420 | 0.39680 | 0.55050 | BROKE |
| EV10 | 200 | ai | 0.97920 | 0.66710 | 0.82315 | HELD |
| FP01 | 200 | unsure | 0.61750 | 0.45970 | 0.53860 | HELD |
| FP02 | 200 | unsure | 0.73870 | 0.58230 | 0.66050 | HELD |
| FP03 | 200 | unsure | 0.80510 | 0.52850 | 0.66680 | HELD |
| FP04 | 200 | unsure | 0.83290 | 0.47070 | 0.65180 | HELD |
| FP05 | 200 | unsure | 0.80050 | 0.61190 | 0.70620 | HELD |
| FP06 | 200 | unsure | 0.88140 | 0.42190 | 0.65165 | HELD |
| FP07 | 200 | unsure | 0.88160 | 0.41090 | 0.64625 | HELD |
| FP08 | 200 | unsure | 0.32230 | 0.38790 | 0.35510 | HELD |
| PI01 | 200 | unsure | 0.46250 | 0.26370 | 0.36310 | HELD |
| PI02 | 200 | human | 0.20440 | 0.26080 | 0.23260 | BROKE |
| PI03 | 200 | unsure | 0.59430 | 0.45810 | 0.52620 | HELD |
| PI04 | 200 | unsure | 0.49980 | 0.44880 | 0.47430 | HELD |
| PI05 | 200 | unsure | 0.64010 | 0.41330 | 0.52670 | HELD |
| PI06 | 200 | unsure | 0.55830 | 0.46480 | 0.51155 | HELD |
| MF01 | 400 | — | — | — | — | HELD |
| MF02 | 400 | — | — | — | — | HELD |
| MF03 | 200 | human | 0.00000 | 0.30000 | 0.15000 | BROKE |
| MF04 | 400 | — | — | — | — | HELD |
| MF05 | 200 | unsure | 0.99760 | 0.30000 | 0.64880 | BROKE |
| MF06 | 400 | — | — | — | — | HELD |
| MF07 | 400 | — | — | — | — | HELD |
| MF08 | 413 | — | — | — | — | HELD |
| RQ01 | 400 | — | — | — | — | HELD |
| RQ02 | 400 | — | — | — | — | HELD |
| RQ03 | 400 | — | — | — | — | HELD |
| RQ04 | 400 | — | — | — | — | HELD |
| RQ05 | 400 | — | — | — | — | HELD |
| RQ06 | 400 | — | — | — | — | HELD |
| RQ07 | 400 | — | — | — | — | HELD |
| RQ08 | 400 | — | — | — | — | HELD |
| RQ09 | 400 | — | — | — | — | HELD |
| RQ10 | 400 | — | — | — | — | HELD |
| RQ11 | 400 | — | — | — | — | HELD |
| RQ12 | 400 | — | — | — | — | HELD |
| FL01_01 | 200 | human | 0.02870 | 0.30000 | 0.16435 | HELD |
| FL01_02 | 200 | human | 0.02870 | 0.30000 | 0.16435 | HELD |
| FL01_03 | 200 | human | 0.02870 | 0.30000 | 0.16435 | HELD |
| FL01_04 | 200 | human | 0.02870 | 0.30000 | 0.16435 | HELD |
| FL01_05 | 200 | human | 0.02870 | 0.30000 | 0.16435 | HELD |
| FL01_06 | 200 | human | 0.02870 | 0.30000 | 0.16435 | HELD |
| FL01_07 | 200 | human | 0.02870 | 0.30000 | 0.16435 | HELD |
| FL01_08 | 200 | human | 0.02870 | 0.30000 | 0.16435 | HELD |
| FL01_09 | 200 | human | 0.02870 | 0.30000 | 0.16435 | HELD |
| FL01_10 | 200 | human | 0.02870 | 0.30000 | 0.16435 | HELD |
| FL01_11 | 429 | — | — | — | — | HELD |
| FL01_12 | 429 | — | — | — | — | HELD |

### Side-by-side comparison

| Measure | Before | After | Interpretation |
|---|---|---|---|
| Staff human samples labeled ai | 5/8 | 0/8 | Five false accusations moved to unsure |
| Evasion samples labeled ai | 1/10 | 1/10 | EV10 still detected; nine strict detection misses remain |
| Evasion outcomes | 2 human, 7 unsure, 1 ai | 2 human, 7 unsure, 1 ai | No change in this family |
| Own human samples labeled ai, each trial | 0/10 | 0/10 | No new benefit on this already-passing set |
| AI comparison samples labeled ai, each trial | 2/10 | 0/10 | Two AI labels were lost to unsure |
| Criterion 2 mean-score gap | 0.12975 | 0.12975 | Scores did not improve |
| Criteria met | 4/5 | 4/5 | No criterion verdict changed |
| Flood rows | 10 HTTP 200, 2 HTTP 429 | 10 HTTP 200, 2 HTTP 429 | Limiter behavior preserved |

The change helped the chosen objective: five staff false accusations disappeared. It cost detection on the AI comparison set: the time-management and community-service samples changed from ai to unsure. This is not an overall accuracy improvement claim. The attack-set change was five labels moving from ai to unsure; no new signal evidence was created. Both result sets and all three-trial logs are retained, including the unchanged miss.

## What’s Still Broken

- EV01–EV09 still avoid the AI label under the strict evasion rule. I would next investigate robustness to editing using paired original/edited controls and evaluate sentence-shape features against a separate validation set. For EV01/EV04/EV08 I would examine model perplexity sensitivity and minimum evidence; for EV02/EV03/EV06/EV07/EV09 I would examine sentence-boundary sensitivity; EV05 shows both signals can look human after editing. I stopped rather than add a second unmeasured signal change.

- PI02 still receives human. I would test matched texts with and without the system-like prefix and examine the score shift. The current result supports feature evasion, not instruction execution; adding an instruction-following filter without that diagnosis would solve the wrong problem.

- MF03 and MF05 still receive authorship scores on junk. I would add a narrowly specified content-quality validation rule for control-character and repeated single-token inputs, then test legitimate short writing so the fix does not just reject difficult cases. I did not implement it because the one improvement was the threshold change.

- Criterion 2 remains missed in every trial. I would collect a more diverse, independently sourced and labeled validation set and evaluate alternative signals before claiming reliable separation. Changing thresholds or lowering the target would not repair the measured score gap.

- English-only word recognition rejects MF07. Safe rejection is not multilingual support; I would explicitly expose the language scope and evaluate a multilingual tokenizer before expanding it.

- Per-creator limits can be bypassed by rotating unauthenticated IDs, and in-memory counts disappear on restart. Production would need authenticated identities, appropriate address-level protection, and shared persistent counters. Appeal ownership and actual human review also remain unimplemented.

I stopped after one measured threshold change to preserve a clean before/after comparison and finish the required evidence rather than introduce several fixes I could not attribute. The human set is one writer, the AI set is one template, and the same attacks selected and assessed the improvement; unseen-data performance remains unknown.

In production I would prioritize fewer wrong accusations and send uncertain cases to review rather than punish writers based on these scores. That means more AI text escapes automated labeling and reviewers bear a larger workload, but genuine writers bear less risk of an unsupported accusation.

## How I Used AI — Unit 8

I used the assistant to interpret the rubric, enable the existing limiter, explain log evidence, and organize commands and commits. I supplied my own discussion-post writing and clarified that later pasted responses belonged to classmates; those classmates’ responses were excluded. The assistant selected unchanged excerpts, generated the explicitly AI-labeled comparison template, and supplied substantial scenarios/evaluation code, including appeal checks and response recording.

The assistant also drafted the HELD/BROKE rules, diagnoses, threshold-change proposal, and documentation from my real uploaded results. I ran the service, flood test, both complete attack sets, and both three-trial evaluations locally. This write-up was AI-assisted, not independently authored analysis; I am responsible for reviewing the judgments against the actual targets and evidence. No results were fabricated and no original criterion was revised.

