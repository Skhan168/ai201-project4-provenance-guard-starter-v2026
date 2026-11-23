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

The criteria were finalized after implementation and the initial smoke test, not before building. The full acceptance evaluation had not been run at the end of Unit 7. The completed Unit 8 before-and-after evaluations appear below.

### Current limitations

- Detection accuracy has not been established.
- Full calibration with genuine human writing and lightly edited AI writing remains incomplete.
- An appeal is recorded, but no human review workflow or automatic resolution is implemented.
- Appeal ownership is not authenticated.
- Rate limiting was disabled in Unit 7 and is now enabled for Unit 8; flood-test evidence appears below.
- The model examines at most 400 tokens, while the style signal examines the accepted passage.
- Unit 8 attack testing and three-trial acceptance evaluation are completed below. Criterion 2 remains MISSED in both evaluations.

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

The new threshold is selected using the baseline failures. Any measured improvement on this same set is an in-sampl

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

e result, not evidence of generalization to unseen writing.

### Measurement plan

Re-run all 56 staff attacks and all five original criteria for three trials each, using the same inputs and test harness. Compare false positives, evasion outcomes, criterion verdicts, and unchanged score values before and after.

## Capstone

**What This Extends**

This capstone extends my existing Provenance Guard service from Units 7 and 8. The service already scores submitted writing, returns explanatory labels, records decisions and appeals, and limits submission rates. The new work is a request-level operational logging layer that records request inputs, response outputs, HTTP status codes, and duration for completed requests, including rejected requests. I will use these records to measure runtime and evaluate the operational layer without changing the authorship detector.

**The Shape**

I chose Shape A: deploy and instrument. I will use Path B: local with logs. The extension is a request-level operational record around the existing service, supported by reproducible running instructions and measured runtime cost.

Out of scope: changing the model, style signal, scoring weights, or label thresholds; adding authentication or a human-review interface; and hosting the model online. Existing audit evidence will be preserved. Tests will use synthetic inputs rather than private writing because request logs will contain submitted data.

**Running It**

The service will run locally using a single documented start command. I will update RUNNING.md with the actual environment, dependency versions, model-file requirements, and setup instructions, then verify those instructions from a clean checkout.

**Instrumentation**

Planned; not yet implemented or measured.

**What It Costs**

Not yet measured.

**Run Log and Verdicts**

Capstone acceptance criteria and test results are not yet recorded.

**The Improvement**

No capstone improvement has been selected. I will choose one after examining the baseline test results.

**What's Still Broken**

The existing audit log does not measure request duration or consistently capture request inputs and response outputs. Invalid appeal requests are not recorded there. The capstone will add a separate operational log while preserving the existing audit history.

**How I Used AI**

I asked the assistant to inspect my existing service and distinguish existing functionality from a new capstone extension. It identified gaps in request-level measurement and outdated running instructions, and helped draft this scope. I will update this section with a second specific moment after the work occurs.

## Capstone Latency Breakdown

This standalone latency breakdown was measured before the startup
improvement, but before this stretch declaration was committed.
I therefore do not claim that the stretch was declared before measurement.

The script timed library imports, detector._load(), and two successive
detector.model_signal() calls in a separate Python process, not through HTTP.

| Stage | Seconds |
|---|---:|
| Import torch and transformers | 6.30 |
| Import detector and load the model/tokenizer | 3.67 |
| First scoring call after loading | 0.285 |
| Second scoring call | 0.119 |

Imports were the largest measured stage, followed by model loading.
Imports, model loading, and the first scoring call totaled about
10.26 seconds in this standalone process.

The baseline service separately recorded a first-request server duration
of about 20.23 seconds. These are different runs under potentially
different conditions, so the standalone timings do not directly partition
that HTTP request's duration.

Planned improvement: call detector.warm_up() in run_local.py before
app.run(). This should move library import and model-loading work before
the server accepts requests. It does not remove that work or guarantee
that the first inference will be fully warm.

The tradeoff is a longer wait before the service starts accepting requests.
After implementing the change, I will rerun all five original criteria
for three trials each and compare the first-request and warm timings.


## Unit 9 Completed Evaluation and Findings

This completed section supersedes the planning-status statements in the
earlier Capstone section. Unit 7 and Unit 8 evidence remains historical.

### Running It

The measured local run path is:

```powershell
python run_local.py
```

Run this from the repository root with the project's virtual environment
activated and its dependencies installed. The launcher disables debug mode,
the reloader, and threading. After the improvement, it loads the detector
before accepting requests. The evaluation runs in a second terminal:

```powershell
python capstone_eval.py --label before
python capstone_eval.py --label after
```

The before command records the historical baseline, not a command to run
again against the changed code. Use the committed before report for that
comparison. The after command tests the current implementation.

### Instrumentation

The extension records request-level operational data separately from the
existing decision/appeal audit log. The recorded fields include timestamp,
request ID, method, path, query, input, output, HTTP status, and duration.
The producer named in the reports is
operational.py::install.<locals>.finish_operational_request.

The complete reports pasted below include more than ten actual structured
operational entries, including HTTP 400 empty-input rejections and HTTP 429
rate-limit rejections. Inputs are synthetic test passages, not private writing.

The HTTP evaluation producer is capstone_eval.py::main, run_trial, send.
Client elapsed time and server duration are distinct measurements and
are not interchangeable.

### Run Log and Verdicts

Both full reports appear below in the same format, with three trials for
each of the five criteria and actual first-trial responses underneath.
All five criteria were MET before and after.

Logging coverage and contents passed their three-request checks in every
trial. Empty-input cases were rejected and logged. All checked warm
requests returned HTTP 200 within 90 seconds. Each rate-limit trial
returned ten HTTP 200 responses followed by HTTP 429 in under 60 seconds.

The original criteria and targets were not revised.
Criteria were committed in a0fdba6, before the first results commit f58ba8a.
The after reports were committed in d991192.

### Diagnosis

No original criterion was missed. Criterion 4's 90-second warm-latency
ceiling was too permissive for these local test passages: the maximum
observed baseline criterion-4 request was about 0.2255 seconds.
A specific tighter future target would be all three warm requests returning
HTTP 200 within 1.0 second in each trial. This is a proposed future target,
not a retrospective replacement for the committed 90-second criterion.

Separately, the baseline's first warmup request took about 20.2536 seconds
client-side, even though later requests were much faster. In detector.py,
perplexity() reaches _load(), which imports dependencies and loads the model
on first use. Later calls reuse the cached model. This identifies a
one-time initialization mechanism on the request path.

The separate timing probe found library imports took 6.30 seconds, model
loading including importing detector took 3.67 seconds, first scoring took
0.285 seconds, and repeat scoring took 0.119 seconds. These independent
timings support the mechanism but do not partition the separate HTTP run.

### The Improvement

The single service change adds an import of detector and calls
detector.warm_up() in run_local.py before app.run().
It moves dependency import and model loading ahead of request acceptance.
The model, scoring weights, thresholds, and validation were not changed.

| Measure | Before | After |
|---|---:|---:|
| First trial warmup, client seconds | 20.2536 | 0.3702 |
| Mean of ten additional warm requests, client seconds | 0.179774 | 0.189853 |
| Maximum criterion-4 request across three trials, seconds | 0.2255 | 0.2038 |
| Criteria MET | 5/5 | 5/5 |

The first observed HTTP request was much faster after the change.
The mean additional warm-request time did not improve: it increased by
about 0.0101 seconds. These small samples do not establish that the change
caused the warm-time difference or guarantee performance on other machines.

The tradeoff is waiting for initialization before the server accepts
requests. The work was moved, not eliminated. Full startup time was not
measured, so no end-to-end startup-plus-request speedup is claimed.
The model is resident earlier; it was already resident after the first
request in the baseline. First inference can still have initialization cost.
Only run_local.py received this startup behavior; python app.py is not
the evaluated capstone launch path.

### What It Costs

The cost measure is warm client elapsed seconds, not CPU time, dollars,
electricity, or a concurrency-capacity measurement. Each report measures
ten additional warm HTTP requests and takes their arithmetic mean.

Before:
100 people/day x 1 request/person x 0.17977374 seconds/request
= 17.977374 seconds/day of summed client request duration.

After:
100 people/day x 1 request/person x 0.18985289 seconds/request
= 18.985289 seconds/day of summed client request duration.

These extrapolations exclude process startup, initial model download,
idle server time, and cold-start behavior. They do not mean that 100
simultaneous users were tested.

### What's Still Broken

No Unit 9 acceptance criterion remains missed, but the passing results
cover only the recorded local workload. The 90-second latency target was
too loose, and full startup duration and repeated cold starts remain
unmeasured. Preloading also means model-loading failure prevents this
launcher from starting; no startup-recovery behavior was evaluated.

Operational logs retain submitted text and response content. They are
suitable for these synthetic tests, but private submissions would need a
retention and redaction policy before real use.

The extension does not repair the detector's authorship limitations,
implement authenticated identities, make rate-limit counters persistent,
or complete human appeal review. Earlier Unit 8 misses remain historical
limitations, not newly passing Unit 9 criteria.

With more time, I would first measure repeated fresh-process launches,
including time until the server is ready and the first HTTP response.
That would distinguish moved startup work from genuine end-to-end savings,
which the present request-only comparison cannot do.

I stopped after one service change and a complete re-run to preserve an
attributable comparison and finish the required evidence under the deadline.

### How I Used AI

For Unit 9, the assistant helped implement and debug the operational logging
and evaluation harness. I ran the commands locally and supplied the real
outputs and saved reports. A misplaced first-trial index caused a syntax
error; the assistant provided a correction, which I applied and checked.

The assistant then helped interpret the measured initialization delay,
proposed using the existing detector.warm_up() function in the local
launcher, and drafted this analysis from my results. I applied the change
and ran the complete after evaluation. The latency breakdown was measured
before its declaration was committed, so I do not claim that the stretch
was declared before measurement. This write-up is AI-assisted.

### Full Before Report

Capstone before results

Producer: capstone_eval.py::main, run_trial, send.

| Criterion | Target | Run 1 | Run 2 | Run 3 | Verdict |
|---|---|---|---|---|---|
| 1. Logging coverage | 3/3 exactly once | 3/3 exactly once | 3/3 exactly once | 3/3 exactly once | MET |
| 2. Record contents | 3/3 complete and matching | 3/3 complete and matching | 3/3 complete and matching | 3/3 complete and matching | MET |
| 3. Empty-input visibility | 3/3 HTTP 400 and logged | 3/3 rejected and logged | 3/3 rejected and logged | 3/3 rejected and logged | MET |
| 4. Warm latency | 3/3 HTTP 200 within 90s after warmup | 3/3 within 90s; warmup=True; max=0.1929s | 3/3 within 90s; warmup=True; max=0.1879s | 3/3 within 90s; warmup=True; max=0.2255s | MET |
| 5. Rate-limit regression | 10 HTTP 200 then 429; sequence under 60s | codes=[200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 429]; elapsed=1.7733s | codes=[200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 429]; elapsed=1.7410s | codes=[200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 429]; elapsed=1.7932s | MET |

Cost measurement complete: True
Mean warm client elapsed seconds: 0.17977374000020063
100 people x 1 request each x mean seconds: 17.977374000020063

Actual first-trial HTTP output for criteria 1, 2, and 4:
```json
[
  {
    "request_id": "fe5b5e07-6d5b-4826-a1c0-f180a3f0475d",
    "method": "POST",
    "path": "/submit",
    "input": {
      "text": "Our neighborhood library opened a small reading room beside the main entrance last spring. Volunteers arranged comfortable chairs near the windows and placed a collection of donated books on wooden shelves for visitors of different ages. I visit on Saturday mornings because the quiet space helps me concentrate on reading before the afternoon becomes busy.",
      "creator_id": "cap_ddcb3476c6c8_valid_1_0"
    },
    "http_status": 200,
    "output": {
      "confidence": 0.4515,
      "content_id": "9557e511-c3ec-4d4e-94b2-84a83725fa07",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.3528,
      "status": "decided",
      "style_score": 0.5502
    },
    "client_seconds": 0.17505660000006174
  },
  {
    "request_id": "a157bf07-6644-46fd-ab30-855228f77b6e",
    "method": "POST",
    "path": "/submit",
    "input": {
      "text": "The community garden has become a useful meeting place for people who live on our street. Each weekend several neighbors bring tools and spend an hour watering vegetables or removing weeds from the narrow paths between the planting beds. Working together gives everyone a chance to share practical advice while producing fresh food for their families.",
      "creator_id": "cap_ddcb3476c6c8_valid_1_1"
    },
    "http_status": 200,
    "output": {
      "confidence": 0.48119999999999996,
      "content_id": "ec308d80-2aa9-49c4-b8a3-c5055f07eee8",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.4332,
      "status": "decided",
      "style_score": 0.5292
    },
    "client_seconds": 0.18208430000049702
  },
  {
    "request_id": "460f355f-de88-4f31-a3f9-bc521b9577da",
    "method": "POST",
    "path": "/submit",
    "input": {
      "text": "Preparing a weekly schedule helps me balance coursework with responsibilities at home and time with friends. I begin by listing important deadlines and then divide larger assignments into smaller tasks that fit into the available hours on different days. The plan sometimes changes, but having a clear starting point makes it easier to decide what needs attention.",
      "creator_id": "cap_ddcb3476c6c8_valid_1_2"
    },
    "http_status": 200,
    "output": {
      "confidence": 0.53235,
      "content_id": "a991c65f-8692-475f-b25d-3a1ef0a5c37c",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.5226,
      "status": "decided",
      "style_score": 0.5421
    },
    "client_seconds": 0.19286680000004708
  }
]
```
Actual first-trial HTTP output for criterion 3:
```json
[
  {
    "request_id": "48e634da-dd10-4d07-8384-46904424823b",
    "method": "POST",
    "path": "/submit",
    "input": {
      "text": "",
      "creator_id": "cap_ddcb3476c6c8_empty_1_0"
    },
    "http_status": 400,
    "output": {
      "error": "text must be a non-empty string."
    },
    "client_seconds": 0.01996099999996659
  },
  {
    "request_id": "28fdcdc2-2b6e-409e-b3ee-9f811282ade8",
    "method": "POST",
    "path": "/submit",
    "input": {
      "text": "",
      "creator_id": "cap_ddcb3476c6c8_empty_1_1"
    },
    "http_status": 400,
    "output": {
      "error": "text must be a non-empty string."
    },
    "client_seconds": 0.006925099999534723
  },
  {
    "request_id": "b0ba8016-6438-4167-af6d-eb1939a2c3b0",
    "method": "POST",
    "path": "/submit",
    "input": {
      "text": "",
      "creator_id": "cap_ddcb3476c6c8_empty_1_2"
    },
    "http_status": 400,
    "output": {
      "error": "text must be a non-empty string."
    },
    "client_seconds": 0.022068499999477353
  }
]
```
Actual first-trial HTTP output for criterion 5:
```json
[
  {
    "request_id": "cbb04034-8de4-4053-b739-17fdac0a8b58",
    "method": "POST",
    "path": "/submit",
    "input": {
      "text": "Our neighborhood library opened a small reading room beside the main entrance last spring. Volunteers arranged comfortable chairs near the windows and placed a collection of donated books on wooden shelves for visitors of different ages. I visit on Saturday mornings because the quiet space helps me concentrate on reading before the afternoon becomes busy.",
      "creator_id": "cap_ddcb3476c6c8_limit_1"
    },
    "http_status": 200,
    "output": {
      "confidence": 0.4515,
      "content_id": "f7921e71-ee0f-45a7-94dc-7b1d68452b03",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.3528,
      "status": "decided",
      "style_score": 0.5502
    },
    "client_seconds": 0.17835910000030708
  },
  {
    "request_id": "ae45b45d-5ff4-427f-a951-d4796ff22d47",
    "method": "POST",
    "path": "/submit",
    "input": {
      "text": "The community garden has become a useful meeting place for people who live on our street. Each weekend several neighbors bring tools and spend an hour watering vegetables or removing weeds from the narrow paths between the planting beds. Working together gives everyone a chance to share practical advice while producing fresh food for their families.",
      "creator_id": "cap_ddcb3476c6c8_limit_1"
    },
    "http_status": 200,
    "output": {
      "confidence": 0.48119999999999996,
      "content_id": "aecf79bc-35bb-46ed-b22a-581991111760",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.4332,
      "status": "decided",
      "style_score": 0.5292
    },
    "client_seconds": 0.17272380000031262
  },
  {
    "request_id": "7e1864e7-edb5-4d4b-bd52-ba6ff77a492d",
    "method": "POST",
    "path": "/submit",
    "input": {
      "text": "Preparing a weekly schedule helps me balance coursework with responsibilities at home and time with friends. I begin by listing important deadlines and then divide larger assignments into smaller tasks that fit into the available hours on different days. The plan sometimes changes, but having a clear starting point makes it easier to decide what needs attention.",
      "creator_id": "cap_ddcb3476c6c8_limit_1"
    },
    "http_status": 200,
    "output": {
      "confidence": 0.53235,
      "content_id": "f85e07d6-057c-4365-9307-b638c758a15a",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.5226,
      "status": "decided",
      "style_score": 0.5421
    },
    "client_seconds": 0.18558930000017426
  },
  {
    "request_id": "fa8cdee3-e200-48b3-84d9-279e85750be1",
    "method": "POST",
    "path": "/submit",
    "input": {
      "text": "Our neighborhood library opened a small reading room beside the main entrance last spring. Volunteers arranged comfortable chairs near the windows and placed a collection of donated books on wooden shelves for visitors of different ages. I visit on Saturday mornings because the quiet space helps me concentrate on reading before the afternoon becomes busy.",
      "creator_id": "cap_ddcb3476c6c8_limit_1"
    },
    "http_status": 200,
    "output": {
      "confidence": 0.4515,
      "content_id": "96e59fee-d287-4627-94b8-d68e9f7d5214",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.3528,
      "status": "decided",
      "style_score": 0.5502
    },
    "client_seconds": 0.18170540000028268
  },
  {
    "request_id": "5a0041fe-23e1-4142-b307-2b536cf385ab",
    "method": "POST",
    "path": "/submit",
    "input": {
      "text": "The community garden has become a useful meeting place for people who live on our street. Each weekend several neighbors bring tools and spend an hour watering vegetables or removing weeds from the narrow paths between the planting beds. Working together gives everyone a chance to share practical advice while producing fresh food for their families.",
      "creator_id": "cap_ddcb3476c6c8_limit_1"
    },
    "http_status": 200,
    "output": {
      "confidence": 0.48119999999999996,
      "content_id": "b4b872a7-39d4-4c28-bb40-97b5ff4c9527",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.4332,
      "status": "decided",
      "style_score": 0.5292
    },
    "client_seconds": 0.17360919999919133
  },
  {
    "request_id": "06ebf195-c932-4213-bd46-2dfb8664d7d0",
    "method": "POST",
    "path": "/submit",
    "input": {
      "text": "Preparing a weekly schedule helps me balance coursework with responsibilities at home and time with friends. I begin by listing important deadlines and then divide larger assignments into smaller tasks that fit into the available hours on different days. The plan sometimes changes, but having a clear starting point makes it easier to decide what needs attention.",
      "creator_id": "cap_ddcb3476c6c8_limit_1"
    },
    "http_status": 200,
    "output": {
      "confidence": 0.53235,
      "content_id": "939eb2a8-84f0-438e-b743-0c1ac35187c4",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.5226,
      "status": "decided",
      "style_score": 0.5421
    },
    "client_seconds": 0.1790008999996644
  },
  {
    "request_id": "b73c75a4-6ddc-4ab6-b14e-37a009185ce1",
    "method": "POST",
    "path": "/submit",
    "input": {
      "text": "Our neighborhood library opened a small reading room beside the main entrance last spring. Volunteers arranged comfortable chairs near the windows and placed a collection of donated books on wooden shelves for visitors of different ages. I visit on Saturday mornings because the quiet space helps me concentrate on reading before the afternoon becomes busy.",
      "creator_id": "cap_ddcb3476c6c8_limit_1"
    },
    "http_status": 200,
    "output": {
      "confidence": 0.4515,
      "content_id": "bba972c8-8617-464e-9125-80e7e3efc952",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.3528,
      "status": "decided",
      "style_score": 0.5502
    },
    "client_seconds": 0.16062480000073265
  },
  {
    "request_id": "b43debc1-58a3-4483-bce7-44bb95611189",
    "method": "POST",
    "path": "/submit",
    "input": {
      "text": "The community garden has become a useful meeting place for people who live on our street. Each weekend several neighbors bring tools and spend an hour watering vegetables or removing weeds from the narrow paths between the planting beds. Working together gives everyone a chance to share practical advice while producing fresh food for their families.",
      "creator_id": "cap_ddcb3476c6c8_limit_1"
    },
    "http_status": 200,
    "output": {
      "confidence": 0.48119999999999996,
      "content_id": "8af6d23e-bcfd-4cad-b401-d9432f28d506",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.4332,
      "status": "decided",
      "style_score": 0.5292
    },
    "client_seconds": 0.17889709999963088
  },
  {
    "request_id": "466caa36-71e0-49e1-9bdc-80cb73b9493b",
    "method": "POST",
    "path": "/submit",
    "input": {
      "text": "Preparing a weekly schedule helps me balance coursework with responsibilities at home and time with friends. I begin by listing important deadlines and then divide larger assignments into smaller tasks that fit into the available hours on different days. The plan sometimes changes, but having a clear starting point makes it easier to decide what needs attention.",
      "creator_id": "cap_ddcb3476c6c8_limit_1"
    },
    "http_status": 200,
    "output": {
      "confidence": 0.53235,
      "content_id": "2826b2c0-4b0a-4e6f-adcf-bb1831f29505",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.5226,
      "status": "decided",
      "style_score": 0.5421
    },
    "client_seconds": 0.18735749999996187
  },
  {
    "request_id": "279e38dc-f10d-4367-a714-f937b68160eb",
    "method": "POST",
    "path": "/submit",
    "input": {
      "text": "Our neighborhood library opened a small reading room beside the main entrance last spring. Volunteers arranged comfortable chairs near the windows and placed a collection of donated books on wooden shelves for visitors of different ages. I visit on Saturday mornings because the quiet space helps me concentrate on reading before the afternoon becomes busy.",
      "creator_id": "cap_ddcb3476c6c8_limit_1"
    },
    "http_status": 200,
    "output": {
      "confidence": 0.4515,
      "content_id": "df6b0316-5354-4af2-af20-2e4e7edf5407",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.3528,
      "status": "decided",
      "style_score": 0.5502
    },
    "client_seconds": 0.15496190000067145
  },
  {
    "request_id": "105a914c-f507-479f-b110-371661b29a2e",
    "method": "POST",
    "path": "/submit",
    "input": {
      "text": "The community garden has become a useful meeting place for people who live on our street. Each weekend several neighbors bring tools and spend an hour watering vegetables or removing weeds from the narrow paths between the planting beds. Working together gives everyone a chance to share practical advice while producing fresh food for their families.",
      "creator_id": "cap_ddcb3476c6c8_limit_1"
    },
    "http_status": 429,
    "output": {
      "error": "rate_limited",
      "limit": "10 per 1 minute",
      "message": "Too many submissions. Try again shortly."
    },
    "client_seconds": 0.019385800000236486
  }
]
```
Operational records produced by operational.py::install.<locals>.finish_operational_request:
```json
[
  {
    "timestamp": "2026-11-23T06:59:37.261283+00:00",
    "request_id": "f5fe1e30-ddc1-4455-964d-73b202455885",
    "method": "POST",
    "path": "/submit",
    "query": "",
    "input": {
      "text": "Our neighborhood library opened a small reading room beside the main entrance last spring. Volunteers arranged comfortable chairs near the windows and placed a collection of donated books on wooden shelves for visitors of different ages. I visit on Saturday mornings because the quiet space helps me concentrate on reading before the afternoon becomes busy.",
      "creator_id": "cap_ddcb3476c6c8_warm_1"
    },
    "output": {
      "confidence": 0.4515,
      "content_id": "3cf98405-adb9-457a-8076-acd1d6665c9d",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.3528,
      "status": "decided",
      "style_score": 0.5502
    },
    "http_status": 200,
    "duration_seconds": 20.230477999999493
  },
  {
    "timestamp": "2026-11-23T06:59:57.508719+00:00",
    "request_id": "fe5b5e07-6d5b-4826-a1c0-f180a3f0475d",
    "method": "POST",
    "path": "/submit",
    "query": "",
    "input": {
      "text": "Our neighborhood library opened a small reading room beside the main entrance last spring. Volunteers arranged comfortable chairs near the windows and placed a collection of donated books on wooden shelves for visitors of different ages. I visit on Saturday mornings because the quiet space helps me concentrate on reading before the afternoon becomes busy.",
      "creator_id": "cap_ddcb3476c6c8_valid_1_0"
    },
    "output": {
      "confidence": 0.4515,
      "content_id": "9557e511-c3ec-4d4e-94b2-84a83725fa07",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.3528,
      "status": "decided",
      "style_score": 0.5502
    },
    "http_status": 200,
    "duration_seconds": 0.15932669999983773
  },
  {
    "timestamp": "2026-11-23T06:59:57.686734+00:00",
    "request_id": "a157bf07-6644-46fd-ab30-855228f77b6e",
    "method": "POST",
    "path": "/submit",
    "query": "",
    "input": {
      "text": "The community garden has become a useful meeting place for people who live on our street. Each weekend several neighbors bring tools and spend an hour watering vegetables or removing weeds from the narrow paths between the planting beds. Working together gives everyone a chance to share practical advice while producing fresh food for their families.",
      "creator_id": "cap_ddcb3476c6c8_valid_1_1"
    },
    "output": {
      "confidence": 0.48119999999999996,
      "content_id": "ec308d80-2aa9-49c4-b8a3-c5055f07eee8",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.4332,
      "status": "decided",
      "style_score": 0.5292
    },
    "http_status": 200,
    "duration_seconds": 0.16322789999958331
  },
  {
    "timestamp": "2026-11-23T06:59:57.867200+00:00",
    "request_id": "460f355f-de88-4f31-a3f9-bc521b9577da",
    "method": "POST",
    "path": "/submit",
    "query": "",
    "input": {
      "text": "Preparing a weekly schedule helps me balance coursework with responsibilities at home and time with friends. I begin by listing important deadlines and then divide larger assignments into smaller tasks that fit into the available hours on different days. The plan sometimes changes, but having a clear starting point makes it easier to decide what needs attention.",
      "creator_id": "cap_ddcb3476c6c8_valid_1_2"
    },
    "output": {
      "confidence": 0.53235,
      "content_id": "a991c65f-8692-475f-b25d-3a1ef0a5c37c",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.5226,
      "status": "decided",
      "style_score": 0.5421
    },
    "http_status": 200,
    "duration_seconds": 0.17564499999934924
  },
  {
    "timestamp": "2026-11-23T06:59:58.060126+00:00",
    "request_id": "48e634da-dd10-4d07-8384-46904424823b",
    "method": "POST",
    "path": "/submit",
    "query": "",
    "input": {
      "text": "",
      "creator_id": "cap_ddcb3476c6c8_empty_1_0"
    },
    "output": {
      "error": "text must be a non-empty string."
    },
    "http_status": 400,
    "duration_seconds": 0.003492700000606419
  },
  {
    "timestamp": "2026-11-23T06:59:58.064227+00:00",
    "request_id": "28fdcdc2-2b6e-409e-b3ee-9f811282ade8",
    "method": "POST",
    "path": "/submit",
    "query": "",
    "input": {
      "text": "",
      "creator_id": "cap_ddcb3476c6c8_empty_1_1"
    },
    "output": {
      "error": "text must be a non-empty string."
    },
    "http_status": 400,
    "duration_seconds": 0.0016976000006252434
  },
  {
    "timestamp": "2026-11-23T06:59:58.088967+00:00",
    "request_id": "b0ba8016-6438-4167-af6d-eb1939a2c3b0",
    "method": "POST",
    "path": "/submit",
    "query": "",
    "input": {
      "text": "",
      "creator_id": "cap_ddcb3476c6c8_empty_1_2"
    },
    "output": {
      "error": "text must be a non-empty string."
    },
    "http_status": 400,
    "duration_seconds": 0.002725299999838171
  },
  {
    "timestamp": "2026-11-23T06:59:58.110799+00:00",
    "request_id": "cbb04034-8de4-4053-b739-17fdac0a8b58",
    "method": "POST",
    "path": "/submit",
    "query": "",
    "input": {
      "text": "Our neighborhood library opened a small reading room beside the main entrance last spring. Volunteers arranged comfortable chairs near the windows and placed a collection of donated books on wooden shelves for visitors of different ages. I visit on Saturday mornings because the quiet space helps me concentrate on reading before the afternoon becomes busy.",
      "creator_id": "cap_ddcb3476c6c8_limit_1"
    },
    "output": {
      "confidence": 0.4515,
      "content_id": "f7921e71-ee0f-45a7-94dc-7b1d68452b03",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.3528,
      "status": "decided",
      "style_score": 0.5502
    },
    "http_status": 200,
    "duration_seconds": 0.160974499999611
  },
  {
    "timestamp": "2026-11-23T06:59:58.286748+00:00",
    "request_id": "ae45b45d-5ff4-427f-a951-d4796ff22d47",
    "method": "POST",
    "path": "/submit",
    "query": "",
    "input": {
      "text": "The community garden has become a useful meeting place for people who live on our street. Each weekend several neighbors bring tools and spend an hour watering vegetables or removing weeds from the narrow paths between the planting beds. Working together gives everyone a chance to share practical advice while producing fresh food for their families.",
      "creator_id": "cap_ddcb3476c6c8_limit_1"
    },
    "output": {
      "confidence": 0.48119999999999996,
      "content_id": "aecf79bc-35bb-46ed-b22a-581991111760",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.4332,
      "status": "decided",
      "style_score": 0.5292
    },
    "http_status": 200,
    "duration_seconds": 0.15737929999977496
  },
  {
    "timestamp": "2026-11-23T06:59:58.459476+00:00",
    "request_id": "7e1864e7-edb5-4d4b-bd52-ba6ff77a492d",
    "method": "POST",
    "path": "/submit",
    "query": "",
    "input": {
      "text": "Preparing a weekly schedule helps me balance coursework with responsibilities at home and time with friends. I begin by listing important deadlines and then divide larger assignments into smaller tasks that fit into the available hours on different days. The plan sometimes changes, but having a clear starting point makes it easier to decide what needs attention.",
      "creator_id": "cap_ddcb3476c6c8_limit_1"
    },
    "output": {
      "confidence": 0.53235,
      "content_id": "f85e07d6-057c-4365-9307-b638c758a15a",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.5226,
      "status": "decided",
      "style_score": 0.5421
    },
    "http_status": 200,
    "duration_seconds": 0.17020789999969566
  },
  {
    "timestamp": "2026-11-23T06:59:58.655782+00:00",
    "request_id": "fa8cdee3-e200-48b3-84d9-279e85750be1",
    "method": "POST",
    "path": "/submit",
    "query": "",
    "input": {
      "text": "Our neighborhood library opened a small reading room beside the main entrance last spring. Volunteers arranged comfortable chairs near the windows and placed a collection of donated books on wooden shelves for visitors of different ages. I visit on Saturday mornings because the quiet space helps me concentrate on reading before the afternoon becomes busy.",
      "creator_id": "cap_ddcb3476c6c8_limit_1"
    },
    "output": {
      "confidence": 0.4515,
      "content_id": "96e59fee-d287-4627-94b8-d68e9f7d5214",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.3528,
      "status": "decided",
      "style_score": 0.5502
    },
    "http_status": 200,
    "duration_seconds": 0.15501820000008593
  },
  {
    "timestamp": "2026-11-23T06:59:58.825448+00:00",
    "request_id": "5a0041fe-23e1-4142-b307-2b536cf385ab",
    "method": "POST",
    "path": "/submit",
    "query": "",
    "input": {
      "text": "The community garden has become a useful meeting place for people who live on our street. Each weekend several neighbors bring tools and spend an hour watering vegetables or removing weeds from the narrow paths between the planting beds. Working together gives everyone a chance to share practical advice while producing fresh food for their families.",
      "creator_id": "cap_ddcb3476c6c8_limit_1"
    },
    "output": {
      "confidence": 0.48119999999999996,
      "content_id": "b4b872a7-39d4-4c28-bb40-97b5ff4c9527",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.4332,
      "status": "decided",
      "style_score": 0.5292
    },
    "http_status": 200,
    "duration_seconds": 0.1599949999999808
  },
  {
    "timestamp": "2026-11-23T06:59:59.003324+00:00",
    "request_id": "06ebf195-c932-4213-bd46-2dfb8664d7d0",
    "method": "POST",
    "path": "/submit",
    "query": "",
    "input": {
      "text": "Preparing a weekly schedule helps me balance coursework with responsibilities at home and time with friends. I begin by listing important deadlines and then divide larger assignments into smaller tasks that fit into the available hours on different days. The plan sometimes changes, but having a clear starting point makes it easier to decide what needs attention.",
      "creator_id": "cap_ddcb3476c6c8_limit_1"
    },
    "output": {
      "confidence": 0.53235,
      "content_id": "939eb2a8-84f0-438e-b743-0c1ac35187c4",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.5226,
      "status": "decided",
      "style_score": 0.5421
    },
    "http_status": 200,
    "duration_seconds": 0.16074869999920338
  },
  {
    "timestamp": "2026-11-23T06:59:59.166928+00:00",
    "request_id": "b73c75a4-6ddc-4ab6-b14e-37a009185ce1",
    "method": "POST",
    "path": "/submit",
    "query": "",
    "input": {
      "text": "Our neighborhood library opened a small reading room beside the main entrance last spring. Volunteers arranged comfortable chairs near the windows and placed a collection of donated books on wooden shelves for visitors of different ages. I visit on Saturday mornings because the quiet space helps me concentrate on reading before the afternoon becomes busy.",
      "creator_id": "cap_ddcb3476c6c8_limit_1"
    },
    "output": {
      "confidence": 0.4515,
      "content_id": "bba972c8-8617-464e-9125-80e7e3efc952",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.3528,
      "status": "decided",
      "style_score": 0.5502
    },
    "http_status": 200,
    "duration_seconds": 0.1559871999997995
  },
  {
    "timestamp": "2026-11-23T06:59:59.346737+00:00",
    "request_id": "b43debc1-58a3-4483-bce7-44bb95611189",
    "method": "POST",
    "path": "/submit",
    "query": "",
    "input": {
      "text": "The community garden has become a useful meeting place for people who live on our street. Each weekend several neighbors bring tools and spend an hour watering vegetables or removing weeds from the narrow paths between the planting beds. Working together gives everyone a chance to share practical advice while producing fresh food for their families.",
      "creator_id": "cap_ddcb3476c6c8_limit_1"
    },
    "output": {
      "confidence": 0.48119999999999996,
      "content_id": "8af6d23e-bcfd-4cad-b401-d9432f28d506",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.4332,
      "status": "decided",
      "style_score": 0.5292
    },
    "http_status": 200,
    "duration_seconds": 0.15750060000027588
  },
  {
    "timestamp": "2026-11-23T06:59:59.528804+00:00",
    "request_id": "466caa36-71e0-49e1-9bdc-80cb73b9493b",
    "method": "POST",
    "path": "/submit",
    "query": "",
    "input": {
      "text": "Preparing a weekly schedule helps me balance coursework with responsibilities at home and time with friends. I begin by listing important deadlines and then divide larger assignments into smaller tasks that fit into the available hours on different days. The plan sometimes changes, but having a clear starting point makes it easier to decide what needs attention.",
      "creator_id": "cap_ddcb3476c6c8_limit_1"
    },
    "output": {
      "confidence": 0.53235,
      "content_id": "2826b2c0-4b0a-4e6f-adcf-bb1831f29505",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.5226,
      "status": "decided",
      "style_score": 0.5421
    },
    "http_status": 200,
    "duration_seconds": 0.1626890999996249
  },
  {
    "timestamp": "2026-11-23T06:59:59.696174+00:00",
    "request_id": "279e38dc-f10d-4367-a714-f937b68160eb",
    "method": "POST",
    "path": "/submit",
    "query": "",
    "input": {
      "text": "Our neighborhood library opened a small reading room beside the main entrance last spring. Volunteers arranged comfortable chairs near the windows and placed a collection of donated books on wooden shelves for visitors of different ages. I visit on Saturday mornings because the quiet space helps me concentrate on reading before the afternoon becomes busy.",
      "creator_id": "cap_ddcb3476c6c8_limit_1"
    },
    "output": {
      "confidence": 0.4515,
      "content_id": "df6b0316-5354-4af2-af20-2e4e7edf5407",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.3528,
      "status": "decided",
      "style_score": 0.5502
    },
    "http_status": 200,
    "duration_seconds": 0.1504715999999462
  },
  {
    "timestamp": "2026-11-23T06:59:59.863726+00:00",
    "request_id": "105a914c-f507-479f-b110-371661b29a2e",
    "method": "POST",
    "path": "/submit",
    "query": "",
    "input": {
      "text": "The community garden has become a useful meeting place for people who live on our street. Each weekend several neighbors bring tools and spend an hour watering vegetables or removing weeds from the narrow paths between the planting beds. Working together gives everyone a chance to share practical advice while producing fresh food for their families.",
      "creator_id": "cap_ddcb3476c6c8_limit_1"
    },
    "output": {
      "error": "rate_limited",
      "limit": "10 per 1 minute",
      "message": "Too many submissions. Try again shortly."
    },
    "http_status": 429,
    "duration_seconds": 0.0025998999999501393
  },
  {
    "timestamp": "2026-11-23T07:00:00.003944+00:00",
    "request_id": "a4e4c749-5f84-4779-874b-692e9fdd58f1",
    "method": "POST",
    "path": "/submit",
    "query": "",
    "input": {
      "text": "Our neighborhood library opened a small reading room beside the main entrance last spring. Volunteers arranged comfortable chairs near the windows and placed a collection of donated books on wooden shelves for visitors of different ages. I visit on Saturday mornings because the quiet space helps me concentrate on reading before the afternoon becomes busy.",
      "creator_id": "cap_ddcb3476c6c8_warm_2"
    },
    "output": {
      "confidence": 0.4515,
      "content_id": "668ca08f-74ab-41e7-962b-4adc2dc05f3e",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.3528,
      "status": "decided",
      "style_score": 0.5502
    },
    "http_status": 200,
    "duration_seconds": 0.1946838999992906
  },
  {
    "timestamp": "2026-11-23T07:00:00.202243+00:00",
    "request_id": "53e6a03c-9dca-4c04-8e0d-7a694948a501",
    "method": "POST",
    "path": "/submit",
    "query": "",
    "input": {
      "text": "Our neighborhood library opened a small reading room beside the main entrance last spring. Volunteers arranged comfortable chairs near the windows and placed a collection of donated books on wooden shelves for visitors of different ages. I visit on Saturday mornings because the quiet space helps me concentrate on reading before the afternoon becomes busy.",
      "creator_id": "cap_ddcb3476c6c8_valid_2_0"
    },
    "output": {
      "confidence": 0.4515,
      "content_id": "4832d94c-566c-432c-8c80-0620419fdf8c",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.3528,
      "status": "decided",
      "style_score": 0.5502
    },
    "http_status": 200,
    "duration_seconds": 0.15278459999990446
  },
  {
    "timestamp": "2026-11-23T07:00:00.374921+00:00",
    "request_id": "657d5c6e-12e1-478b-9882-901499d5496d",
    "method": "POST",
    "path": "/submit",
    "query": "",
    "input": {
      "text": "The community garden has become a useful meeting place for people who live on our street. Each weekend several neighbors bring tools and spend an hour watering vegetables or removing weeds from the narrow paths between the planting beds. Working together gives everyone a chance to share practical advice while producing fresh food for their families.",
      "creator_id": "cap_ddcb3476c6c8_valid_2_1"
    },
    "output": {
      "confidence": 0.48119999999999996,
      "content_id": "f47bf507-e645-4b19-9349-b31eadceec46",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.4332,
      "status": "decided",
      "style_score": 0.5292
    },
    "http_status": 200,
    "duration_seconds": 0.16040049999992334
  },
  {
    "timestamp": "2026-11-23T07:00:00.561205+00:00",
    "request_id": "e51875f5-61d9-47b8-b4b3-aa1d674e0f3f",
    "method": "POST",
    "path": "/submit",
    "query": "",
    "input": {
      "text": "Preparing a weekly schedule helps me balance coursework with responsibilities at home and time with friends. I begin by listing important deadlines and then divide larger assignments into smaller tasks that fit into the available hours on different days. The plan sometimes changes, but having a clear starting point makes it easier to decide what needs attention.",
      "creator_id": "cap_ddcb3476c6c8_valid_2_2"
    },
    "output": {
      "confidence": 0.53235,
      "content_id": "a06cc2f1-f0ea-419b-87f1-0bb8b569c68f",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.5226,
      "status": "decided",
      "style_score": 0.5421
    },
    "http_status": 200,
    "duration_seconds": 0.1621770000001561
  },
  {
    "timestamp": "2026-11-23T07:00:00.745157+00:00",
    "request_id": "b72a7417-baf7-4929-801c-8ff0dc515b25",
    "method": "POST",
    "path": "/submit",
    "query": "",
    "input": {
      "text": "",
      "creator_id": "cap_ddcb3476c6c8_empty_2_0"
    },
    "output": {
      "error": "text must be a non-empty string."
    },
    "http_status": 400,
    "duration_seconds": 0.0020457999999052845
  },
  {
    "timestamp": "2026-11-23T07:00:00.766731+00:00",
    "request_id": "e6c6f2dd-e82e-48e4-8ab5-b2f4d59d1021",
    "method": "POST",
    "path": "/submit",
    "query": "",
    "input": {
      "text": "",
      "creator_id": "cap_ddcb3476c6c8_empty_2_1"
    },
    "output": {
      "error": "text must be a non-empty string."
    },
    "http_status": 400,
    "duration_seconds": 0.0023745999997117906
  },
  {
    "timestamp": "2026-11-23T07:00:00.773733+00:00",
    "request_id": "5952761a-d71a-45ba-ab09-a7a9b2398b37",
    "method": "POST",
    "path": "/submit",
    "query": "",
    "input": {
      "text": "",
      "creator_id": "cap_ddcb3476c6c8_empty_2_2"
    },
    "output": {
      "error": "text must be a non-empty string."
    },
    "http_status": 400,
    "duration_seconds": 0.0015180999998847255
  },
  {
    "timestamp": "2026-11-23T07:00:00.781976+00:00",
    "request_id": "cb61a6fb-1608-49b9-89f1-e0cc65735dda",
    "method": "POST",
    "path": "/submit",
    "query": "",
    "input": {
      "text": "Our neighborhood library opened a small reading room beside the main entrance last spring. Volunteers arranged comfortable chairs near the windows and placed a collection of donated books on wooden shelves for visitors of different ages. I visit on Saturday mornings because the quiet space helps me concentrate on reading before the afternoon becomes busy.",
      "creator_id": "cap_ddcb3476c6c8_limit_2"
    },
    "output": {
      "confidence": 0.4515,
      "content_id": "1f952a93-f665-4663-b938-6971618b5a63",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.3528,
      "status": "decided",
      "style_score": 0.5502
    },
    "http_status": 200,
    "duration_seconds": 0.15698350000002392
  },
  {
    "timestamp": "2026-11-23T07:00:00.965467+00:00",
    "request_id": "90b48577-41d8-4250-bf2c-9c2a0f85877b",
    "method": "POST",
    "path": "/submit",
    "query": "",
    "input": {
      "text": "The community garden has become a useful meeting place for people who live on our street. Each weekend several neighbors bring tools and spend an hour watering vegetables or removing weeds from the narrow paths between the planting beds. Working together gives everyone a chance to share practical advice while producing fresh food for their families.",
      "creator_id": "cap_ddcb3476c6c8_limit_2"
    },
    "output": {
      "confidence": 0.48119999999999996,
      "content_id": "ba806ed6-722d-478a-ba75-79541abab97e",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.4332,
      "status": "decided",
      "style_score": 0.5292
    },
    "http_status": 200,
    "duration_seconds": 0.157255900000564
  },
  {
    "timestamp": "2026-11-23T07:00:01.124758+00:00",
    "request_id": "1b331fda-d73e-4b91-a03e-f2a74b51aeb9",
    "method": "POST",
    "path": "/submit",
    "query": "",
    "input": {
      "text": "Preparing a weekly schedule helps me balance coursework with responsibilities at home and time with friends. I begin by listing important deadlines and then divide larger assignments into smaller tasks that fit into the available hours on different days. The plan sometimes changes, but having a clear starting point makes it easier to decide what needs attention.",
      "creator_id": "cap_ddcb3476c6c8_limit_2"
    },
    "output": {
      "confidence": 0.53235,
      "content_id": "b5bbcc05-f9e5-42aa-b237-e016bc33cae1",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.5226,
      "status": "decided",
      "style_score": 0.5421
    },
    "http_status": 200,
    "duration_seconds": 0.16392279999945458
  },
  {
    "timestamp": "2026-11-23T07:00:01.311694+00:00",
    "request_id": "54b17b9f-14f0-4b6b-ad2f-4c19686fe5ba",
    "method": "POST",
    "path": "/submit",
    "query": "",
    "input": {
      "text": "Our neighborhood library opened a small reading room beside the main entrance last spring. Volunteers arranged comfortable chairs near the windows and placed a collection of donated books on wooden shelves for visitors of different ages. I visit on Saturday mornings because the quiet space helps me concentrate on reading before the afternoon becomes busy.",
      "creator_id": "cap_ddcb3476c6c8_limit_2"
    },
    "output": {
      "confidence": 0.4515,
      "content_id": "aa3a4847-b7be-4b24-a455-a4bbe0d50a34",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.3528,
      "status": "decided",
      "style_score": 0.5502
    },
    "http_status": 200,
    "duration_seconds": 0.15127289999963978
  },
  {
    "timestamp": "2026-11-23T07:00:01.469722+00:00",
    "request_id": "383e6ae4-bbfa-4d3f-becb-20f329acc29c",
    "method": "POST",
    "path": "/submit",
    "query": "",
    "input": {
      "text": "The community garden has become a useful meeting place for people who live on our street. Each weekend several neighbors bring tools and spend an hour watering vegetables or removing weeds from the narrow paths between the planting beds. Working together gives everyone a chance to share practical advice while producing fresh food for their families.",
      "creator_id": "cap_ddcb3476c6c8_limit_2"
    },
    "output": {
      "confidence": 0.48119999999999996,
      "content_id": "5af1e3d2-03ef-4a83-b47b-573e4ededbb7",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.4332,
      "status": "decided",
      "style_score": 0.5292
    },
    "http_status": 200,
    "duration_seconds": 0.15987560000030498
  },
  {
    "timestamp": "2026-11-23T07:00:01.649314+00:00",
    "request_id": "01646174-a24a-47d3-a5bf-5a36ac260ab1",
    "method": "POST",
    "path": "/submit",
    "query": "",
    "input": {
      "text": "Preparing a weekly schedule helps me balance coursework with responsibilities at home and time with friends. I begin by listing important deadlines and then divide larger assignments into smaller tasks that fit into the available hours on different days. The plan sometimes changes, but having a clear starting point makes it easier to decide what needs attention.",
      "creator_id": "cap_ddcb3476c6c8_limit_2"
    },
    "output": {
      "confidence": 0.53235,
      "content_id": "1a6ecf6d-d7b1-47fa-bd2e-423981a21c2a",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.5226,
      "status": "decided",
      "style_score": 0.5421
    },
    "http_status": 200,
    "duration_seconds": 0.16464989999985846
  },
  {
    "timestamp": "2026-11-23T07:00:01.818343+00:00",
    "request_id": "162eb2cb-edbb-4405-a818-f6b9a932d3e1",
    "method": "POST",
    "path": "/submit",
    "query": "",
    "input": {
      "text": "Our neighborhood library opened a small reading room beside the main entrance last spring. Volunteers arranged comfortable chairs near the windows and placed a collection of donated books on wooden shelves for visitors of different ages. I visit on Saturday mornings because the quiet space helps me concentrate on reading before the afternoon becomes busy.",
      "creator_id": "cap_ddcb3476c6c8_limit_2"
    },
    "output": {
      "confidence": 0.4515,
      "content_id": "6f2bd27b-f732-428a-bdcc-77d0410825cf",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.3528,
      "status": "decided",
      "style_score": 0.5502
    },
    "http_status": 200,
    "duration_seconds": 0.16114590000051976
  },
  {
    "timestamp": "2026-11-23T07:00:01.984832+00:00",
    "request_id": "29b67a2f-5dc9-4b9f-acd1-231183d6fc99",
    "method": "POST",
    "path": "/submit",
    "query": "",
    "input": {
      "text": "The community garden has become a useful meeting place for people who live on our street. Each weekend several neighbors bring tools and spend an hour watering vegetables or removing weeds from the narrow paths between the planting beds. Working together gives everyone a chance to share practical advice while producing fresh food for their families.",
      "creator_id": "cap_ddcb3476c6c8_limit_2"
    },
    "output": {
      "confidence": 0.48119999999999996,
      "content_id": "0078097e-573a-4cdb-8315-2326c46dcd5e",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.4332,
      "status": "decided",
      "style_score": 0.5292
    },
    "http_status": 200,
    "duration_seconds": 0.15858230000048934
  },
  {
    "timestamp": "2026-11-23T07:00:02.145298+00:00",
    "request_id": "b666c2d0-515a-4e54-b713-5904a4816664",
    "method": "POST",
    "path": "/submit",
    "query": "",
    "input": {
      "text": "Preparing a weekly schedule helps me balance coursework with responsibilities at home and time with friends. I begin by listing important deadlines and then divide larger assignments into smaller tasks that fit into the available hours on different days. The plan sometimes changes, but having a clear starting point makes it easier to decide what needs attention.",
      "creator_id": "cap_ddcb3476c6c8_limit_2"
    },
    "output": {
      "confidence": 0.53235,
      "content_id": "c35907fc-c5cb-4387-923a-51c33e64039e",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.5226,
      "status": "decided",
      "style_score": 0.5421
    },
    "http_status": 200,
    "duration_seconds": 0.16389640000033978
  },
  {
    "timestamp": "2026-11-23T07:00:02.334140+00:00",
    "request_id": "45925a10-7987-4c89-a4d4-9b187af44214",
    "method": "POST",
    "path": "/submit",
    "query": "",
    "input": {
      "text": "Our neighborhood library opened a small reading room beside the main entrance last spring. Volunteers arranged comfortable chairs near the windows and placed a collection of donated books on wooden shelves for visitors of different ages. I visit on Saturday mornings because the quiet space helps me concentrate on reading before the afternoon becomes busy.",
      "creator_id": "cap_ddcb3476c6c8_limit_2"
    },
    "output": {
      "confidence": 0.4515,
      "content_id": "0e8b32fa-c39b-4b2b-a7c9-7c2949571b94",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.3528,
      "status": "decided",
      "style_score": 0.5502
    },
    "http_status": 200,
    "duration_seconds": 0.15632120000009309
  },
  {
    "timestamp": "2026-11-23T07:00:02.514717+00:00",
    "request_id": "7701fd64-4e8d-4717-bd73-fb1eecb58962",
    "method": "POST",
    "path": "/submit",
    "query": "",
    "input": {
      "text": "The community garden has become a useful meeting place for people who live on our street. Each weekend several neighbors bring tools and spend an hour watering vegetables or removing weeds from the narrow paths between the planting beds. Working together gives everyone a chance to share practical advice while producing fresh food for their families.",
      "creator_id": "cap_ddcb3476c6c8_limit_2"
    },
    "output": {
      "error": "rate_limited",
      "limit": "10 per 1 minute",
      "message": "Too many submissions. Try again shortly."
    },
    "http_status": 429,
    "duration_seconds": 0.0020881999998891843
  },
  {
    "timestamp": "2026-11-23T07:00:02.637312+00:00",
    "request_id": "a5b83dc7-d925-4a71-a8bd-6f8ae7bbb5c4",
    "method": "POST",
    "path": "/submit",
    "query": "",
    "input": {
      "text": "Our neighborhood library opened a small reading room beside the main entrance last spring. Volunteers arranged comfortable chairs near the windows and placed a collection of donated books on wooden shelves for visitors of different ages. I visit on Saturday mornings because the quiet space helps me concentrate on reading before the afternoon becomes busy.",
      "creator_id": "cap_ddcb3476c6c8_warm_3"
    },
    "output": {
      "confidence": 0.4515,
      "content_id": "d0247df4-5277-480a-84fe-72e7a78c26a0",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.3528,
      "status": "decided",
      "style_score": 0.5502
    },
    "http_status": 200,
    "duration_seconds": 0.15540500000042812
  },
  {
    "timestamp": "2026-11-23T07:00:02.809384+00:00",
    "request_id": "d031fc27-a5e3-4ebf-a97c-81930bb1a8b5",
    "method": "POST",
    "path": "/submit",
    "query": "",
    "input": {
      "text": "Our neighborhood library opened a small reading room beside the main entrance last spring. Volunteers arranged comfortable chairs near the windows and placed a collection of donated books on wooden shelves for visitors of different ages. I visit on Saturday mornings because the quiet space helps me concentrate on reading before the afternoon becomes busy.",
      "creator_id": "cap_ddcb3476c6c8_valid_3_0"
    },
    "output": {
      "confidence": 0.4515,
      "content_id": "6400adb3-9cb4-4240-a508-fa5510a77bdc",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.3528,
      "status": "decided",
      "style_score": 0.5502
    },
    "http_status": 200,
    "duration_seconds": 0.15501859999949374
  },
  {
    "timestamp": "2026-11-23T07:00:02.990802+00:00",
    "request_id": "8af1da81-4fe7-4c2d-a383-f42cfebedeca",
    "method": "POST",
    "path": "/submit",
    "query": "",
    "input": {
      "text": "The community garden has become a useful meeting place for people who live on our street. Each weekend several neighbors bring tools and spend an hour watering vegetables or removing weeds from the narrow paths between the planting beds. Working together gives everyone a chance to share practical advice while producing fresh food for their families.",
      "creator_id": "cap_ddcb3476c6c8_valid_3_1"
    },
    "output": {
      "confidence": 0.48119999999999996,
      "content_id": "4e868a44-9c34-42c3-835b-47ba90c857e5",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.4332,
      "status": "decided",
      "style_score": 0.5292
    },
    "http_status": 200,
    "duration_seconds": 0.1979393000001437
  },
  {
    "timestamp": "2026-11-23T07:00:03.205025+00:00",
    "request_id": "da1e274d-285d-4c61-925f-944f586fb1f7",
    "method": "POST",
    "path": "/submit",
    "query": "",
    "input": {
      "text": "Preparing a weekly schedule helps me balance coursework with responsibilities at home and time with friends. I begin by listing important deadlines and then divide larger assignments into smaller tasks that fit into the available hours on different days. The plan sometimes changes, but having a clear starting point makes it easier to decide what needs attention.",
      "creator_id": "cap_ddcb3476c6c8_valid_3_2"
    },
    "output": {
      "confidence": 0.53235,
      "content_id": "4fb8b090-cf97-491c-ac6b-582eb524ac4f",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.5226,
      "status": "decided",
      "style_score": 0.5421
    },
    "http_status": 200,
    "duration_seconds": 0.16229500000008557
  },
  {
    "timestamp": "2026-11-23T07:00:03.383156+00:00",
    "request_id": "779bb083-888a-484f-a3f0-28a2a9843a0c",
    "method": "POST",
    "path": "/submit",
    "query": "",
    "input": {
      "text": "",
      "creator_id": "cap_ddcb3476c6c8_empty_3_0"
    },
    "output": {
      "error": "text must be a non-empty string."
    },
    "http_status": 400,
    "duration_seconds": 0.0021021000002292567
  },
  {
    "timestamp": "2026-11-23T07:00:03.401612+00:00",
    "request_id": "0b8e2a0d-acde-42c9-a47a-543268e36788",
    "method": "POST",
    "path": "/submit",
    "query": "",
    "input": {
      "text": "",
      "creator_id": "cap_ddcb3476c6c8_empty_3_1"
    },
    "output": {
      "error": "text must be a non-empty string."
    },
    "http_status": 400,
    "duration_seconds": 0.0027479999998831772
  },
  {
    "timestamp": "2026-11-23T07:00:03.421617+00:00",
    "request_id": "6c405d8b-96bf-4aba-a205-fef0ab9e5e44",
    "method": "POST",
    "path": "/submit",
    "query": "",
    "input": {
      "text": "",
      "creator_id": "cap_ddcb3476c6c8_empty_3_2"
    },
    "output": {
      "error": "text must be a non-empty string."
    },
    "http_status": 400,
    "duration_seconds": 0.0021810999996887404
  },
  {
    "timestamp": "2026-11-23T07:00:03.438334+00:00",
    "request_id": "42a7e7c3-bda3-434b-8422-31c7f7249fba",
    "method": "POST",
    "path": "/submit",
    "query": "",
    "input": {
      "text": "Our neighborhood library opened a small reading room beside the main entrance last spring. Volunteers arranged comfortable chairs near the windows and placed a collection of donated books on wooden shelves for visitors of different ages. I visit on Saturday mornings because the quiet space helps me concentrate on reading before the afternoon becomes busy.",
      "creator_id": "cap_ddcb3476c6c8_limit_3"
    },
    "output": {
      "confidence": 0.4515,
      "content_id": "5c87b446-d275-4833-b86c-15e597c32a95",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.3528,
      "status": "decided",
      "style_score": 0.5502
    },
    "http_status": 200,
    "duration_seconds": 0.1605184999998528
  },
  {
    "timestamp": "2026-11-23T07:00:03.601119+00:00",
    "request_id": "9b4e208e-146d-479f-9c8b-2dce0ca52c41",
    "method": "POST",
    "path": "/submit",
    "query": "",
    "input": {
      "text": "The community garden has become a useful meeting place for people who live on our street. Each weekend several neighbors bring tools and spend an hour watering vegetables or removing weeds from the narrow paths between the planting beds. Working together gives everyone a chance to share practical advice while producing fresh food for their families.",
      "creator_id": "cap_ddcb3476c6c8_limit_3"
    },
    "output": {
      "confidence": 0.48119999999999996,
      "content_id": "3bed61c8-0409-4474-a88d-70c7ffa98247",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.4332,
      "status": "decided",
      "style_score": 0.5292
    },
    "http_status": 200,
    "duration_seconds": 0.15712359999997716
  },
  {
    "timestamp": "2026-11-23T07:00:03.780660+00:00",
    "request_id": "73cbff79-bb05-4278-b002-edf267f84104",
    "method": "POST",
    "path": "/submit",
    "query": "",
    "input": {
      "text": "Preparing a weekly schedule helps me balance coursework with responsibilities at home and time with friends. I begin by listing important deadlines and then divide larger assignments into smaller tasks that fit into the available hours on different days. The plan sometimes changes, but having a clear starting point makes it easier to decide what needs attention.",
      "creator_id": "cap_ddcb3476c6c8_limit_3"
    },
    "output": {
      "confidence": 0.53235,
      "content_id": "c5200cdb-89b0-47c0-a0b7-163c6fb91caf",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.5226,
      "status": "decided",
      "style_score": 0.5421
    },
    "http_status": 200,
    "duration_seconds": 0.16510850000031496
  },
  {
    "timestamp": "2026-11-23T07:00:03.958852+00:00",
    "request_id": "a317f81d-9115-4a4e-a881-bc72c1974c68",
    "method": "POST",
    "path": "/submit",
    "query": "",
    "input": {
      "text": "Our neighborhood library opened a small reading room beside the main entrance last spring. Volunteers arranged comfortable chairs near the windows and placed a collection of donated books on wooden shelves for visitors of different ages. I visit on Saturday mornings because the quiet space helps me concentrate on reading before the afternoon becomes busy.",
      "creator_id": "cap_ddcb3476c6c8_limit_3"
    },
    "output": {
      "confidence": 0.4515,
      "content_id": "c06810a7-26bb-4130-b200-73cf419e6359",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.3528,
      "status": "decided",
      "style_score": 0.5502
    },
    "http_status": 200,
    "duration_seconds": 0.15072110000073735
  },
  {
    "timestamp": "2026-11-23T07:00:04.130646+00:00",
    "request_id": "20aa4b45-84dc-4b26-a7e9-3bb5d741a440",
    "method": "POST",
    "path": "/submit",
    "query": "",
    "input": {
      "text": "The community garden has become a useful meeting place for people who live on our street. Each weekend several neighbors bring tools and spend an hour watering vegetables or removing weeds from the narrow paths between the planting beds. Working together gives everyone a chance to share practical advice while producing fresh food for their families.",
      "creator_id": "cap_ddcb3476c6c8_limit_3"
    },
    "output": {
      "confidence": 0.48119999999999996,
      "content_id": "0457d880-9154-4b41-b700-d2937002123f",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.4332,
      "status": "decided",
      "style_score": 0.5292
    },
    "http_status": 200,
    "duration_seconds": 0.15755999999964843
  },
  {
    "timestamp": "2026-11-23T07:00:04.302818+00:00",
    "request_id": "3b1057aa-d6b8-4d30-9a40-cd8925a4749e",
    "method": "POST",
    "path": "/submit",
    "query": "",
    "input": {
      "text": "Preparing a weekly schedule helps me balance coursework with responsibilities at home and time with friends. I begin by listing important deadlines and then divide larger assignments into smaller tasks that fit into the available hours on different days. The plan sometimes changes, but having a clear starting point makes it easier to decide what needs attention.",
      "creator_id": "cap_ddcb3476c6c8_limit_3"
    },
    "output": {
      "confidence": 0.53235,
      "content_id": "7dc3700c-ebc6-4a30-ac1d-c26c7bb9ad14",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.5226,
      "status": "decided",
      "style_score": 0.5421
    },
    "http_status": 200,
    "duration_seconds": 0.15917630000058125
  },
  {
    "timestamp": "2026-11-23T07:00:04.479409+00:00",
    "request_id": "6cf5c6d2-0c0a-48b3-a398-8692d04ebda3",
    "method": "POST",
    "path": "/submit",
    "query": "",
    "input": {
      "text": "Our neighborhood library opened a small reading room beside the main entrance last spring. Volunteers arranged comfortable chairs near the windows and placed a collection of donated books on wooden shelves for visitors of different ages. I visit on Saturday mornings because the quiet space helps me concentrate on reading before the afternoon becomes busy.",
      "creator_id": "cap_ddcb3476c6c8_limit_3"
    },
    "output": {
      "confidence": 0.4515,
      "content_id": "d5b8d59a-95b4-417f-819b-359dc41a3e1e",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.3528,
      "status": "decided",
      "style_score": 0.5502
    },
    "http_status": 200,
    "duration_seconds": 0.15992850000020553
  },
  {
    "timestamp": "2026-11-23T07:00:04.652419+00:00",
    "request_id": "7c31994c-b2c4-44c0-9454-d2a3697cb53c",
    "method": "POST",
    "path": "/submit",
    "query": "",
    "input": {
      "text": "The community garden has become a useful meeting place for people who live on our street. Each weekend several neighbors bring tools and spend an hour watering vegetables or removing weeds from the narrow paths between the planting beds. Working together gives everyone a chance to share practical advice while producing fresh food for their families.",
      "creator_id": "cap_ddcb3476c6c8_limit_3"
    },
    "output": {
      "confidence": 0.48119999999999996,
      "content_id": "3ee8261e-f427-4f32-abc8-f7921dfd2e30",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.4332,
      "status": "decided",
      "style_score": 0.5292
    },
    "http_status": 200,
    "duration_seconds": 0.1579439999995884
  },
  {
    "timestamp": "2026-11-23T07:00:04.822970+00:00",
    "request_id": "1139474a-e87e-427d-9724-99bc4d1b3614",
    "method": "POST",
    "path": "/submit",
    "query": "",
    "input": {
      "text": "Preparing a weekly schedule helps me balance coursework with responsibilities at home and time with friends. I begin by listing important deadlines and then divide larger assignments into smaller tasks that fit into the available hours on different days. The plan sometimes changes, but having a clear starting point makes it easier to decide what needs attention.",
      "creator_id": "cap_ddcb3476c6c8_limit_3"
    },
    "output": {
      "confidence": 0.53235,
      "content_id": "65359bc1-4992-452e-a59f-2528922b5613",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.5226,
      "status": "decided",
      "style_score": 0.5421
    },
    "http_status": 200,
    "duration_seconds": 0.18496649999997317
  },
  {
    "timestamp": "2026-11-23T07:00:05.030156+00:00",
    "request_id": "24897bf4-96c1-4698-a348-968a1e49100c",
    "method": "POST",
    "path": "/submit",
    "query": "",
    "input": {
      "text": "Our neighborhood library opened a small reading room beside the main entrance last spring. Volunteers arranged comfortable chairs near the windows and placed a collection of donated books on wooden shelves for visitors of different ages. I visit on Saturday mornings because the quiet space helps me concentrate on reading before the afternoon becomes busy.",
      "creator_id": "cap_ddcb3476c6c8_limit_3"
    },
    "output": {
      "confidence": 0.4515,
      "content_id": "62916b99-145e-484e-b3e8-6a5ee8b80161",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.3528,
      "status": "decided",
      "style_score": 0.5502
    },
    "http_status": 200,
    "duration_seconds": 0.165551900000537
  },
  {
    "timestamp": "2026-11-23T07:00:05.215213+00:00",
    "request_id": "c010770c-4abe-4747-b71b-145ac746793b",
    "method": "POST",
    "path": "/submit",
    "query": "",
    "input": {
      "text": "The community garden has become a useful meeting place for people who live on our street. Each weekend several neighbors bring tools and spend an hour watering vegetables or removing weeds from the narrow paths between the planting beds. Working together gives everyone a chance to share practical advice while producing fresh food for their families.",
      "creator_id": "cap_ddcb3476c6c8_limit_3"
    },
    "output": {
      "error": "rate_limited",
      "limit": "10 per 1 minute",
      "message": "Too many submissions. Try again shortly."
    },
    "http_status": 429,
    "duration_seconds": 0.0021198999993430334
  },
  {
    "timestamp": "2026-11-23T07:00:05.329342+00:00",
    "request_id": "5b955d85-1081-4556-a03a-378d27bb4a62",
    "method": "POST",
    "path": "/submit",
    "query": "",
    "input": {
      "text": "Our neighborhood library opened a small reading room beside the main entrance last spring. Volunteers arranged comfortable chairs near the windows and placed a collection of donated books on wooden shelves for visitors of different ages. I visit on Saturday mornings because the quiet space helps me concentrate on reading before the afternoon becomes busy.",
      "creator_id": "cap_ddcb3476c6c8_cost_0"
    },
    "output": {
      "confidence": 0.4515,
      "content_id": "609ee6c1-9011-478e-a0d3-d734db41d729",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.3528,
      "status": "decided",
      "style_score": 0.5502
    },
    "http_status": 200,
    "duration_seconds": 0.15955229999963194
  },
  {
    "timestamp": "2026-11-23T07:00:05.509111+00:00",
    "request_id": "f0c0c125-ada4-402c-a523-b410dc2844cf",
    "method": "POST",
    "path": "/submit",
    "query": "",
    "input": {
      "text": "The community garden has become a useful meeting place for people who live on our street. Each weekend several neighbors bring tools and spend an hour watering vegetables or removing weeds from the narrow paths between the planting beds. Working together gives everyone a chance to share practical advice while producing fresh food for their families.",
      "creator_id": "cap_ddcb3476c6c8_cost_1"
    },
    "output": {
      "confidence": 0.48119999999999996,
      "content_id": "dc8093d8-3170-4900-95b7-d50e3c8039c3",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.4332,
      "status": "decided",
      "style_score": 0.5292
    },
    "http_status": 200,
    "duration_seconds": 0.16855469999973138
  },
  {
    "timestamp": "2026-11-23T07:00:05.705770+00:00",
    "request_id": "f1edac05-5f7d-4a00-9d7b-58cc6fb03755",
    "method": "POST",
    "path": "/submit",
    "query": "",
    "input": {
      "text": "Preparing a weekly schedule helps me balance coursework with responsibilities at home and time with friends. I begin by listing important deadlines and then divide larger assignments into smaller tasks that fit into the available hours on different days. The plan sometimes changes, but having a clear starting point makes it easier to decide what needs attention.",
      "creator_id": "cap_ddcb3476c6c8_cost_2"
    },
    "output": {
      "confidence": 0.53235,
      "content_id": "0cb4a89d-0ae5-4230-b0d6-6e17bd36629e",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.5226,
      "status": "decided",
      "style_score": 0.5421
    },
    "http_status": 200,
    "duration_seconds": 0.16455759999917063
  },
  {
    "timestamp": "2026-11-23T07:00:05.876489+00:00",
    "request_id": "8e289d89-5abd-4525-bdbd-300aeae39f0e",
    "method": "POST",
    "path": "/submit",
    "query": "",
    "input": {
      "text": "Our neighborhood library opened a small reading room beside the main entrance last spring. Volunteers arranged comfortable chairs near the windows and placed a collection of donated books on wooden shelves for visitors of different ages. I visit on Saturday mornings because the quiet space helps me concentrate on reading before the afternoon becomes busy.",
      "creator_id": "cap_ddcb3476c6c8_cost_3"
    },
    "output": {
      "confidence": 0.4515,
      "content_id": "affb5616-4f17-40b8-9bbf-10671fba54bb",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.3528,
      "status": "decided",
      "style_score": 0.5502
    },
    "http_status": 200,
    "duration_seconds": 0.19250169999941136
  },
  {
    "timestamp": "2026-11-23T07:00:06.085016+00:00",
    "request_id": "c8a71b2b-c065-439a-ad8a-cc27726ade93",
    "method": "POST",
    "path": "/submit",
    "query": "",
    "input": {
      "text": "The community garden has become a useful meeting place for people who live on our street. Each weekend several neighbors bring tools and spend an hour watering vegetables or removing weeds from the narrow paths between the planting beds. Working together gives everyone a chance to share practical advice while producing fresh food for their families.",
      "creator_id": "cap_ddcb3476c6c8_cost_4"
    },
    "output": {
      "confidence": 0.48119999999999996,
      "content_id": "21b05217-dfaa-4bd0-bca8-0fad94a493c8",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.4332,
      "status": "decided",
      "style_score": 0.5292
    },
    "http_status": 200,
    "duration_seconds": 0.1785161000007065
  },
  {
    "timestamp": "2026-11-23T07:00:06.287972+00:00",
    "request_id": "e2ed5ca0-f194-4b36-ac17-df51fd0d04d0",
    "method": "POST",
    "path": "/submit",
    "query": "",
    "input": {
      "text": "Preparing a weekly schedule helps me balance coursework with responsibilities at home and time with friends. I begin by listing important deadlines and then divide larger assignments into smaller tasks that fit into the available hours on different days. The plan sometimes changes, but having a clear starting point makes it easier to decide what needs attention.",
      "creator_id": "cap_ddcb3476c6c8_cost_5"
    },
    "output": {
      "confidence": 0.53235,
      "content_id": "3f629a3b-ee7b-4735-b4e4-46b00d1f1ac8",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.5226,
      "status": "decided",
      "style_score": 0.5421
    },
    "http_status": 200,
    "duration_seconds": 0.1644360999998753
  },
  {
    "timestamp": "2026-11-23T07:00:06.474186+00:00",
    "request_id": "5bd025a9-9215-4b38-980f-3ad2f635d8b4",
    "method": "POST",
    "path": "/submit",
    "query": "",
    "input": {
      "text": "Our neighborhood library opened a small reading room beside the main entrance last spring. Volunteers arranged comfortable chairs near the windows and placed a collection of donated books on wooden shelves for visitors of different ages. I visit on Saturday mornings because the quiet space helps me concentrate on reading before the afternoon becomes busy.",
      "creator_id": "cap_ddcb3476c6c8_cost_6"
    },
    "output": {
      "confidence": 0.4515,
      "content_id": "9b8f8c10-cd36-4300-8bf8-59f98f21ab12",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.3528,
      "status": "decided",
      "style_score": 0.5502
    },
    "http_status": 200,
    "duration_seconds": 0.15391060000001744
  },
  {
    "timestamp": "2026-11-23T07:00:06.630074+00:00",
    "request_id": "0f091ebc-5146-46f2-9cb4-d6187939f6c1",
    "method": "POST",
    "path": "/submit",
    "query": "",
    "input": {
      "text": "The community garden has become a useful meeting place for people who live on our street. Each weekend several neighbors bring tools and spend an hour watering vegetables or removing weeds from the narrow paths between the planting beds. Working together gives everyone a chance to share practical advice while producing fresh food for their families.",
      "creator_id": "cap_ddcb3476c6c8_cost_7"
    },
    "output": {
      "confidence": 0.48119999999999996,
      "content_id": "93b3a741-5906-453d-992c-5c3b435000fa",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.4332,
      "status": "decided",
      "style_score": 0.5292
    },
    "http_status": 200,
    "duration_seconds": 0.15180039999995643
  },
  {
    "timestamp": "2026-11-23T07:00:06.800628+00:00",
    "request_id": "0115db11-5ea0-4e16-8345-59f87358177c",
    "method": "POST",
    "path": "/submit",
    "query": "",
    "input": {
      "text": "Preparing a weekly schedule helps me balance coursework with responsibilities at home and time with friends. I begin by listing important deadlines and then divide larger assignments into smaller tasks that fit into the available hours on different days. The plan sometimes changes, but having a clear starting point makes it easier to decide what needs attention.",
      "creator_id": "cap_ddcb3476c6c8_cost_8"
    },
    "output": {
      "confidence": 0.53235,
      "content_id": "f75bff50-a29d-4a21-aad3-1764f9aca197",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.5226,
      "status": "decided",
      "style_score": 0.5421
    },
    "http_status": 200,
    "duration_seconds": 0.15969330000007176
  },
  {
    "timestamp": "2026-11-23T07:00:06.978685+00:00",
    "request_id": "050436b1-deb1-4f3c-b9bf-6f86cab427bd",
    "method": "POST",
    "path": "/submit",
    "query": "",
    "input": {
      "text": "Our neighborhood library opened a small reading room beside the main entrance last spring. Volunteers arranged comfortable chairs near the windows and placed a collection of donated books on wooden shelves for visitors of different ages. I visit on Saturday mornings because the quiet space helps me concentrate on reading before the afternoon becomes busy.",
      "creator_id": "cap_ddcb3476c6c8_cost_9"
    },
    "output": {
      "confidence": 0.4515,
      "content_id": "7b46f7f6-edfd-42ef-b8fb-a67eea80380c",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.3528,
      "status": "decided",
      "style_score": 0.5502
    },
    "http_status": 200,
    "duration_seconds": 0.15025100000002567
  }
]
```

### Full After Report

Capstone after results

Producer: capstone_eval.py::main, run_trial, send.

| Criterion | Target | Run 1 | Run 2 | Run 3 | Verdict |
|---|---|---|---|---|---|
| 1. Logging coverage | 3/3 exactly once | 3/3 exactly once | 3/3 exactly once | 3/3 exactly once | MET |
| 2. Record contents | 3/3 complete and matching | 3/3 complete and matching | 3/3 complete and matching | 3/3 complete and matching | MET |
| 3. Empty-input visibility | 3/3 HTTP 400 and logged | 3/3 rejected and logged | 3/3 rejected and logged | 3/3 rejected and logged | MET |
| 4. Warm latency | 3/3 HTTP 200 within 90s after warmup | 3/3 within 90s; warmup=True; max=0.1848s | 3/3 within 90s; warmup=True; max=0.2018s | 3/3 within 90s; warmup=True; max=0.2038s | MET |
| 5. Rate-limit regression | 10 HTTP 200 then 429; sequence under 60s | codes=[200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 429]; elapsed=1.9975s | codes=[200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 429]; elapsed=1.9905s | codes=[200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 429]; elapsed=1.9025s | MET |

Cost measurement complete: True
Mean warm client elapsed seconds: 0.18985289000002012
100 people x 1 request each x mean seconds: 18.985289000002012

Actual first-trial HTTP output for criteria 1, 2, and 4:
```json
[
  {
    "request_id": "5a149713-12ed-4c53-a585-42ffd5604ecf",
    "method": "POST",
    "path": "/submit",
    "input": {
      "text": "Our neighborhood library opened a small reading room beside the main entrance last spring. Volunteers arranged comfortable chairs near the windows and placed a collection of donated books on wooden shelves for visitors of different ages. I visit on Saturday mornings because the quiet space helps me concentrate on reading before the afternoon becomes busy.",
      "creator_id": "cap_a0c542bd72a3_valid_1_0"
    },
    "http_status": 200,
    "output": {
      "confidence": 0.4515,
      "content_id": "367dfd8e-85e7-400b-b974-9612c856a57e",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.3528,
      "status": "decided",
      "style_score": 0.5502
    },
    "client_seconds": 0.14874500000041735
  },
  {
    "request_id": "32beabec-16ce-49ce-a7c1-6e7f6eac99ca",
    "method": "POST",
    "path": "/submit",
    "input": {
      "text": "The community garden has become a useful meeting place for people who live on our street. Each weekend several neighbors bring tools and spend an hour watering vegetables or removing weeds from the narrow paths between the planting beds. Working together gives everyone a chance to share practical advice while producing fresh food for their families.",
      "creator_id": "cap_a0c542bd72a3_valid_1_1"
    },
    "http_status": 200,
    "output": {
      "confidence": 0.48119999999999996,
      "content_id": "4d1275a8-a5e9-4329-ba01-3460b0fdba1d",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.4332,
      "status": "decided",
      "style_score": 0.5292
    },
    "client_seconds": 0.1848320999997668
  },
  {
    "request_id": "bab3cce2-503a-414e-9451-4af7c41c23b0",
    "method": "POST",
    "path": "/submit",
    "input": {
      "text": "Preparing a weekly schedule helps me balance coursework with responsibilities at home and time with friends. I begin by listing important deadlines and then divide larger assignments into smaller tasks that fit into the available hours on different days. The plan sometimes changes, but having a clear starting point makes it easier to decide what needs attention.",
      "creator_id": "cap_a0c542bd72a3_valid_1_2"
    },
    "http_status": 200,
    "output": {
      "confidence": 0.53235,
      "content_id": "d8bd7049-2026-4b10-a9da-ce408b2f1921",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.5226,
      "status": "decided",
      "style_score": 0.5421
    },
    "client_seconds": 0.17820899999969697
  }
]
```
Actual first-trial HTTP output for criterion 3:
```json
[
  {
    "request_id": "c23d2ceb-eebc-473c-921e-c734e5c95c7b",
    "method": "POST",
    "path": "/submit",
    "input": {
      "text": "",
      "creator_id": "cap_a0c542bd72a3_empty_1_0"
    },
    "http_status": 400,
    "output": {
      "error": "text must be a non-empty string."
    },
    "client_seconds": 0.018856599999708124
  },
  {
    "request_id": "28cd7e25-0bb4-4506-95b0-3c3346591db2",
    "method": "POST",
    "path": "/submit",
    "input": {
      "text": "",
      "creator_id": "cap_a0c542bd72a3_empty_1_1"
    },
    "http_status": 400,
    "output": {
      "error": "text must be a non-empty string."
    },
    "client_seconds": 0.008134200000313285
  },
  {
    "request_id": "344c4a95-d1d8-4a67-b4b0-b08405116b11",
    "method": "POST",
    "path": "/submit",
    "input": {
      "text": "",
      "creator_id": "cap_a0c542bd72a3_empty_1_2"
    },
    "http_status": 400,
    "output": {
      "error": "text must be a non-empty string."
    },
    "client_seconds": 0.008532300000297255
  }
]
```
Actual first-trial HTTP output for criterion 5:
```json
[
  {
    "request_id": "894de5ff-b65c-418c-8054-b7f554a139d0",
    "method": "POST",
    "path": "/submit",
    "input": {
      "text": "Our neighborhood library opened a small reading room beside the main entrance last spring. Volunteers arranged comfortable chairs near the windows and placed a collection of donated books on wooden shelves for visitors of different ages. I visit on Saturday mornings because the quiet space helps me concentrate on reading before the afternoon becomes busy.",
      "creator_id": "cap_a0c542bd72a3_limit_1"
    },
    "http_status": 200,
    "output": {
      "confidence": 0.4515,
      "content_id": "c10f0ab0-54c3-4e24-812a-498274d532b9",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.3528,
      "status": "decided",
      "style_score": 0.5502
    },
    "client_seconds": 0.16972609999993438
  },
  {
    "request_id": "3f074d3d-1928-492a-9ec8-0f3e9a69e7ba",
    "method": "POST",
    "path": "/submit",
    "input": {
      "text": "The community garden has become a useful meeting place for people who live on our street. Each weekend several neighbors bring tools and spend an hour watering vegetables or removing weeds from the narrow paths between the planting beds. Working together gives everyone a chance to share practical advice while producing fresh food for their families.",
      "creator_id": "cap_a0c542bd72a3_limit_1"
    },
    "http_status": 200,
    "output": {
      "confidence": 0.48119999999999996,
      "content_id": "85529340-2e76-416b-b1e6-0fc6e5490b17",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.4332,
      "status": "decided",
      "style_score": 0.5292
    },
    "client_seconds": 0.21134559999973135
  },
  {
    "request_id": "7ddc4225-af4a-4eb4-bc5f-cdd508170380",
    "method": "POST",
    "path": "/submit",
    "input": {
      "text": "Preparing a weekly schedule helps me balance coursework with responsibilities at home and time with friends. I begin by listing important deadlines and then divide larger assignments into smaller tasks that fit into the available hours on different days. The plan sometimes changes, but having a clear starting point makes it easier to decide what needs attention.",
      "creator_id": "cap_a0c542bd72a3_limit_1"
    },
    "http_status": 200,
    "output": {
      "confidence": 0.53235,
      "content_id": "a6ba07fe-7c23-4570-850f-d039c4753530",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.5226,
      "status": "decided",
      "style_score": 0.5421
    },
    "client_seconds": 0.19642950000070414
  },
  {
    "request_id": "293e78d2-eda4-47a4-910c-3d4e93c66d85",
    "method": "POST",
    "path": "/submit",
    "input": {
      "text": "Our neighborhood library opened a small reading room beside the main entrance last spring. Volunteers arranged comfortable chairs near the windows and placed a collection of donated books on wooden shelves for visitors of different ages. I visit on Saturday mornings because the quiet space helps me concentrate on reading before the afternoon becomes busy.",
      "creator_id": "cap_a0c542bd72a3_limit_1"
    },
    "http_status": 200,
    "output": {
      "confidence": 0.4515,
      "content_id": "9fb1e760-7514-460c-8997-e47d49c353d8",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.3528,
      "status": "decided",
      "style_score": 0.5502
    },
    "client_seconds": 0.16265539999949397
  },
  {
    "request_id": "87b37417-4123-4295-aba3-210bab93801b",
    "method": "POST",
    "path": "/submit",
    "input": {
      "text": "The community garden has become a useful meeting place for people who live on our street. Each weekend several neighbors bring tools and spend an hour watering vegetables or removing weeds from the narrow paths between the planting beds. Working together gives everyone a chance to share practical advice while producing fresh food for their families.",
      "creator_id": "cap_a0c542bd72a3_limit_1"
    },
    "http_status": 200,
    "output": {
      "confidence": 0.48119999999999996,
      "content_id": "cd02925b-1b01-4e2e-a355-b02f67122e61",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.4332,
      "status": "decided",
      "style_score": 0.5292
    },
    "client_seconds": 0.17828319999989617
  },
  {
    "request_id": "23b7ff17-db6d-46ac-a225-b4ef52d512f6",
    "method": "POST",
    "path": "/submit",
    "input": {
      "text": "Preparing a weekly schedule helps me balance coursework with responsibilities at home and time with friends. I begin by listing important deadlines and then divide larger assignments into smaller tasks that fit into the available hours on different days. The plan sometimes changes, but having a clear starting point makes it easier to decide what needs attention.",
      "creator_id": "cap_a0c542bd72a3_limit_1"
    },
    "http_status": 200,
    "output": {
      "confidence": 0.53235,
      "content_id": "badf5a1c-66ab-40f3-84f2-933d64be04f4",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.5226,
      "status": "decided",
      "style_score": 0.5421
    },
    "client_seconds": 0.20278550000057294
  },
  {
    "request_id": "2a4396e3-bfdc-4f6c-9073-f97ee5c4fb81",
    "method": "POST",
    "path": "/submit",
    "input": {
      "text": "Our neighborhood library opened a small reading room beside the main entrance last spring. Volunteers arranged comfortable chairs near the windows and placed a collection of donated books on wooden shelves for visitors of different ages. I visit on Saturday mornings because the quiet space helps me concentrate on reading before the afternoon becomes busy.",
      "creator_id": "cap_a0c542bd72a3_limit_1"
    },
    "http_status": 200,
    "output": {
      "confidence": 0.4515,
      "content_id": "76eb2c77-f93e-4d09-9a69-df1a333b3c5b",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.3528,
      "status": "decided",
      "style_score": 0.5502
    },
    "client_seconds": 0.27465099999972153
  },
  {
    "request_id": "644f412a-6075-49c2-9007-c02a6b998e3a",
    "method": "POST",
    "path": "/submit",
    "input": {
      "text": "The community garden has become a useful meeting place for people who live on our street. Each weekend several neighbors bring tools and spend an hour watering vegetables or removing weeds from the narrow paths between the planting beds. Working together gives everyone a chance to share practical advice while producing fresh food for their families.",
      "creator_id": "cap_a0c542bd72a3_limit_1"
    },
    "http_status": 200,
    "output": {
      "confidence": 0.48119999999999996,
      "content_id": "33505e3f-71e2-43ca-8c4b-65856645be58",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.4332,
      "status": "decided",
      "style_score": 0.5292
    },
    "client_seconds": 0.20267340000009426
  },
  {
    "request_id": "8646f36f-2972-4f0f-9103-5cadd23d583b",
    "method": "POST",
    "path": "/submit",
    "input": {
      "text": "Preparing a weekly schedule helps me balance coursework with responsibilities at home and time with friends. I begin by listing important deadlines and then divide larger assignments into smaller tasks that fit into the available hours on different days. The plan sometimes changes, but having a clear starting point makes it easier to decide what needs attention.",
      "creator_id": "cap_a0c542bd72a3_limit_1"
    },
    "http_status": 200,
    "output": {
      "confidence": 0.53235,
      "content_id": "91da2096-86ae-468e-bef3-d0d7e8d4d0c5",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.5226,
      "status": "decided",
      "style_score": 0.5421
    },
    "client_seconds": 0.20106659999964904
  },
  {
    "request_id": "facfd4e7-c7e5-44cc-bfba-9510d3321057",
    "method": "POST",
    "path": "/submit",
    "input": {
      "text": "Our neighborhood library opened a small reading room beside the main entrance last spring. Volunteers arranged comfortable chairs near the windows and placed a collection of donated books on wooden shelves for visitors of different ages. I visit on Saturday mornings because the quiet space helps me concentrate on reading before the afternoon becomes busy.",
      "creator_id": "cap_a0c542bd72a3_limit_1"
    },
    "http_status": 200,
    "output": {
      "confidence": 0.4515,
      "content_id": "2321863e-68f6-411e-8d5b-015768d90074",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.3528,
      "status": "decided",
      "style_score": 0.5502
    },
    "client_seconds": 0.18662380000023404
  },
  {
    "request_id": "80d17a24-83e0-46cf-9e96-59a249daf134",
    "method": "POST",
    "path": "/submit",
    "input": {
      "text": "The community garden has become a useful meeting place for people who live on our street. Each weekend several neighbors bring tools and spend an hour watering vegetables or removing weeds from the narrow paths between the planting beds. Working together gives everyone a chance to share practical advice while producing fresh food for their families.",
      "creator_id": "cap_a0c542bd72a3_limit_1"
    },
    "http_status": 429,
    "output": {
      "error": "rate_limited",
      "limit": "10 per 1 minute",
      "message": "Too many submissions. Try again shortly."
    },
    "client_seconds": 0.010334200000215787
  }
]
```
Operational records produced by operational.py::install.<locals>.finish_operational_request:
```json
[
  {
    "timestamp": "2026-11-23T07:26:37.317840+00:00",
    "request_id": "cc511750-802d-4732-aecb-5461b8199939",
    "method": "POST",
    "path": "/submit",
    "query": "",
    "input": {
      "text": "Our neighborhood library opened a small reading room beside the main entrance last spring. Volunteers arranged comfortable chairs near the windows and placed a collection of donated books on wooden shelves for visitors of different ages. I visit on Saturday mornings because the quiet space helps me concentrate on reading before the afternoon becomes busy.",
      "creator_id": "cap_a0c542bd72a3_warm_1"
    },
    "output": {
      "confidence": 0.4515,
      "content_id": "07940172-fd85-437c-9965-45a6711b3d7b",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.3528,
      "status": "decided",
      "style_score": 0.5502
    },
    "http_status": 200,
    "duration_seconds": 0.35335810000015044
  },
  {
    "timestamp": "2026-11-23T07:26:37.677210+00:00",
    "request_id": "5a149713-12ed-4c53-a585-42ffd5604ecf",
    "method": "POST",
    "path": "/submit",
    "query": "",
    "input": {
      "text": "Our neighborhood library opened a small reading room beside the main entrance last spring. Volunteers arranged comfortable chairs near the windows and placed a collection of donated books on wooden shelves for visitors of different ages. I visit on Saturday mornings because the quiet space helps me concentrate on reading before the afternoon becomes busy.",
      "creator_id": "cap_a0c542bd72a3_valid_1_0"
    },
    "output": {
      "confidence": 0.4515,
      "content_id": "367dfd8e-85e7-400b-b974-9612c856a57e",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.3528,
      "status": "decided",
      "style_score": 0.5502
    },
    "http_status": 200,
    "duration_seconds": 0.14354400000047463
  },
  {
    "timestamp": "2026-11-23T07:26:37.841637+00:00",
    "request_id": "32beabec-16ce-49ce-a7c1-6e7f6eac99ca",
    "method": "POST",
    "path": "/submit",
    "query": "",
    "input": {
      "text": "The community garden has become a useful meeting place for people who live on our street. Each weekend several neighbors bring tools and spend an hour watering vegetables or removing weeds from the narrow paths between the planting beds. Working together gives everyone a chance to share practical advice while producing fresh food for their families.",
      "creator_id": "cap_a0c542bd72a3_valid_1_1"
    },
    "output": {
      "confidence": 0.48119999999999996,
      "content_id": "4d1275a8-a5e9-4329-ba01-3460b0fdba1d",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.4332,
      "status": "decided",
      "style_score": 0.5292
    },
    "http_status": 200,
    "duration_seconds": 0.1636916999996174
  },
  {
    "timestamp": "2026-11-23T07:26:38.020687+00:00",
    "request_id": "bab3cce2-503a-414e-9451-4af7c41c23b0",
    "method": "POST",
    "path": "/submit",
    "query": "",
    "input": {
      "text": "Preparing a weekly schedule helps me balance coursework with responsibilities at home and time with friends. I begin by listing important deadlines and then divide larger assignments into smaller tasks that fit into the available hours on different days. The plan sometimes changes, but having a clear starting point makes it easier to decide what needs attention.",
      "creator_id": "cap_a0c542bd72a3_valid_1_2"
    },
    "output": {
      "confidence": 0.53235,
      "content_id": "d8bd7049-2026-4b10-a9da-ce408b2f1921",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.5226,
      "status": "decided",
      "style_score": 0.5421
    },
    "http_status": 200,
    "duration_seconds": 0.16307500000039
  },
  {
    "timestamp": "2026-11-23T07:26:38.200021+00:00",
    "request_id": "c23d2ceb-eebc-473c-921e-c734e5c95c7b",
    "method": "POST",
    "path": "/submit",
    "query": "",
    "input": {
      "text": "",
      "creator_id": "cap_a0c542bd72a3_empty_1_0"
    },
    "output": {
      "error": "text must be a non-empty string."
    },
    "http_status": 400,
    "duration_seconds": 0.0029586999999082764
  },
  {
    "timestamp": "2026-11-23T07:26:38.208743+00:00",
    "request_id": "28cd7e25-0bb4-4506-95b0-3c3346591db2",
    "method": "POST",
    "path": "/submit",
    "query": "",
    "input": {
      "text": "",
      "creator_id": "cap_a0c542bd72a3_empty_1_1"
    },
    "output": {
      "error": "text must be a non-empty string."
    },
    "http_status": 400,
    "duration_seconds": 0.0015012999992904952
  },
  {
    "timestamp": "2026-11-23T07:26:38.216790+00:00",
    "request_id": "344c4a95-d1d8-4a67-b4b0-b08405116b11",
    "method": "POST",
    "path": "/submit",
    "query": "",
    "input": {
      "text": "",
      "creator_id": "cap_a0c542bd72a3_empty_1_2"
    },
    "output": {
      "error": "text must be a non-empty string."
    },
    "http_status": 400,
    "duration_seconds": 0.0018232000002171844
  },
  {
    "timestamp": "2026-11-23T07:26:38.225896+00:00",
    "request_id": "894de5ff-b65c-418c-8054-b7f554a139d0",
    "method": "POST",
    "path": "/submit",
    "query": "",
    "input": {
      "text": "Our neighborhood library opened a small reading room beside the main entrance last spring. Volunteers arranged comfortable chairs near the windows and placed a collection of donated books on wooden shelves for visitors of different ages. I visit on Saturday mornings because the quiet space helps me concentrate on reading before the afternoon becomes busy.",
      "creator_id": "cap_a0c542bd72a3_limit_1"
    },
    "output": {
      "confidence": 0.4515,
      "content_id": "c10f0ab0-54c3-4e24-812a-498274d532b9",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.3528,
      "status": "decided",
      "style_score": 0.5502
    },
    "http_status": 200,
    "duration_seconds": 0.16389999999955762
  },
  {
    "timestamp": "2026-11-23T07:26:38.393811+00:00",
    "request_id": "3f074d3d-1928-492a-9ec8-0f3e9a69e7ba",
    "method": "POST",
    "path": "/submit",
    "query": "",
    "input": {
      "text": "The community garden has become a useful meeting place for people who live on our street. Each weekend several neighbors bring tools and spend an hour watering vegetables or removing weeds from the narrow paths between the planting beds. Working together gives everyone a chance to share practical advice while producing fresh food for their families.",
      "creator_id": "cap_a0c542bd72a3_limit_1"
    },
    "output": {
      "confidence": 0.48119999999999996,
      "content_id": "85529340-2e76-416b-b1e6-0fc6e5490b17",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.4332,
      "status": "decided",
      "style_score": 0.5292
    },
    "http_status": 200,
    "duration_seconds": 0.20601589999932912
  },
  {
    "timestamp": "2026-11-23T07:26:38.620544+00:00",
    "request_id": "7ddc4225-af4a-4eb4-bc5f-cdd508170380",
    "method": "POST",
    "path": "/submit",
    "query": "",
    "input": {
      "text": "Preparing a weekly schedule helps me balance coursework with responsibilities at home and time with friends. I begin by listing important deadlines and then divide larger assignments into smaller tasks that fit into the available hours on different days. The plan sometimes changes, but having a clear starting point makes it easier to decide what needs attention.",
      "creator_id": "cap_a0c542bd72a3_limit_1"
    },
    "output": {
      "confidence": 0.53235,
      "content_id": "a6ba07fe-7c23-4570-850f-d039c4753530",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.5226,
      "status": "decided",
      "style_score": 0.5421
    },
    "http_status": 200,
    "duration_seconds": 0.17688940000061848
  },
  {
    "timestamp": "2026-11-23T07:26:38.802505+00:00",
    "request_id": "293e78d2-eda4-47a4-910c-3d4e93c66d85",
    "method": "POST",
    "path": "/submit",
    "query": "",
    "input": {
      "text": "Our neighborhood library opened a small reading room beside the main entrance last spring. Volunteers arranged comfortable chairs near the windows and placed a collection of donated books on wooden shelves for visitors of different ages. I visit on Saturday mornings because the quiet space helps me concentrate on reading before the afternoon becomes busy.",
      "creator_id": "cap_a0c542bd72a3_limit_1"
    },
    "output": {
      "confidence": 0.4515,
      "content_id": "9fb1e760-7514-460c-8997-e47d49c353d8",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.3528,
      "status": "decided",
      "style_score": 0.5502
    },
    "http_status": 200,
    "duration_seconds": 0.15727609999976266
  },
  {
    "timestamp": "2026-11-23T07:26:38.978775+00:00",
    "request_id": "87b37417-4123-4295-aba3-210bab93801b",
    "method": "POST",
    "path": "/submit",
    "query": "",
    "input": {
      "text": "The community garden has become a useful meeting place for people who live on our street. Each weekend several neighbors bring tools and spend an hour watering vegetables or removing weeds from the narrow paths between the planting beds. Working together gives everyone a chance to share practical advice while producing fresh food for their families.",
      "creator_id": "cap_a0c542bd72a3_limit_1"
    },
    "output": {
      "confidence": 0.48119999999999996,
      "content_id": "cd02925b-1b01-4e2e-a355-b02f67122e61",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.4332,
      "status": "decided",
      "style_score": 0.5292
    },
    "http_status": 200,
    "duration_seconds": 0.15981920000012906
  },
  {
    "timestamp": "2026-11-23T07:26:39.152918+00:00",
    "request_id": "23b7ff17-db6d-46ac-a225-b4ef52d512f6",
    "method": "POST",
    "path": "/submit",
    "query": "",
    "input": {
      "text": "Preparing a weekly schedule helps me balance coursework with responsibilities at home and time with friends. I begin by listing important deadlines and then divide larger assignments into smaller tasks that fit into the available hours on different days. The plan sometimes changes, but having a clear starting point makes it easier to decide what needs attention.",
      "creator_id": "cap_a0c542bd72a3_limit_1"
    },
    "output": {
      "confidence": 0.53235,
      "content_id": "badf5a1c-66ab-40f3-84f2-933d64be04f4",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.5226,
      "status": "decided",
      "style_score": 0.5421
    },
    "http_status": 200,
    "duration_seconds": 0.18685119999918243
  },
  {
    "timestamp": "2026-11-23T07:26:39.349135+00:00",
    "request_id": "2a4396e3-bfdc-4f6c-9073-f97ee5c4fb81",
    "method": "POST",
    "path": "/submit",
    "query": "",
    "input": {
      "text": "Our neighborhood library opened a small reading room beside the main entrance last spring. Volunteers arranged comfortable chairs near the windows and placed a collection of donated books on wooden shelves for visitors of different ages. I visit on Saturday mornings because the quiet space helps me concentrate on reading before the afternoon becomes busy.",
      "creator_id": "cap_a0c542bd72a3_limit_1"
    },
    "output": {
      "confidence": 0.4515,
      "content_id": "76eb2c77-f93e-4d09-9a69-df1a333b3c5b",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.3528,
      "status": "decided",
      "style_score": 0.5502
    },
    "http_status": 200,
    "duration_seconds": 0.2664086999993742
  },
  {
    "timestamp": "2026-11-23T07:26:39.634793+00:00",
    "request_id": "644f412a-6075-49c2-9007-c02a6b998e3a",
    "method": "POST",
    "path": "/submit",
    "query": "",
    "input": {
      "text": "The community garden has become a useful meeting place for people who live on our street. Each weekend several neighbors bring tools and spend an hour watering vegetables or removing weeds from the narrow paths between the planting beds. Working together gives everyone a chance to share practical advice while producing fresh food for their families.",
      "creator_id": "cap_a0c542bd72a3_limit_1"
    },
    "output": {
      "confidence": 0.48119999999999996,
      "content_id": "33505e3f-71e2-43ca-8c4b-65856645be58",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.4332,
      "status": "decided",
      "style_score": 0.5292
    },
    "http_status": 200,
    "duration_seconds": 0.1836406000002171
  },
  {
    "timestamp": "2026-11-23T07:26:39.835564+00:00",
    "request_id": "8646f36f-2972-4f0f-9103-5cadd23d583b",
    "method": "POST",
    "path": "/submit",
    "query": "",
    "input": {
      "text": "Preparing a weekly schedule helps me balance coursework with responsibilities at home and time with friends. I begin by listing important deadlines and then divide larger assignments into smaller tasks that fit into the available hours on different days. The plan sometimes changes, but having a clear starting point makes it easier to decide what needs attention.",
      "creator_id": "cap_a0c542bd72a3_limit_1"
    },
    "output": {
      "confidence": 0.53235,
      "content_id": "91da2096-86ae-468e-bef3-d0d7e8d4d0c5",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.5226,
      "status": "decided",
      "style_score": 0.5421
    },
    "http_status": 200,
    "duration_seconds": 0.18498120000003837
  },
  {
    "timestamp": "2026-11-23T07:26:40.035961+00:00",
    "request_id": "facfd4e7-c7e5-44cc-bfba-9510d3321057",
    "method": "POST",
    "path": "/submit",
    "query": "",
    "input": {
      "text": "Our neighborhood library opened a small reading room beside the main entrance last spring. Volunteers arranged comfortable chairs near the windows and placed a collection of donated books on wooden shelves for visitors of different ages. I visit on Saturday mornings because the quiet space helps me concentrate on reading before the afternoon becomes busy.",
      "creator_id": "cap_a0c542bd72a3_limit_1"
    },
    "output": {
      "confidence": 0.4515,
      "content_id": "2321863e-68f6-411e-8d5b-015768d90074",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.3528,
      "status": "decided",
      "style_score": 0.5502
    },
    "http_status": 200,
    "duration_seconds": 0.1711433999998917
  },
  {
    "timestamp": "2026-11-23T07:26:40.212910+00:00",
    "request_id": "80d17a24-83e0-46cf-9e96-59a249daf134",
    "method": "POST",
    "path": "/submit",
    "query": "",
    "input": {
      "text": "The community garden has become a useful meeting place for people who live on our street. Each weekend several neighbors bring tools and spend an hour watering vegetables or removing weeds from the narrow paths between the planting beds. Working together gives everyone a chance to share practical advice while producing fresh food for their families.",
      "creator_id": "cap_a0c542bd72a3_limit_1"
    },
    "output": {
      "error": "rate_limited",
      "limit": "10 per 1 minute",
      "message": "Too many submissions. Try again shortly."
    },
    "http_status": 429,
    "duration_seconds": 0.0023158000003604684
  },
  {
    "timestamp": "2026-11-23T07:26:40.346266+00:00",
    "request_id": "2f63c562-7e67-4c01-bd86-8297b39bb6be",
    "method": "POST",
    "path": "/submit",
    "query": "",
    "input": {
      "text": "Our neighborhood library opened a small reading room beside the main entrance last spring. Volunteers arranged comfortable chairs near the windows and placed a collection of donated books on wooden shelves for visitors of different ages. I visit on Saturday mornings because the quiet space helps me concentrate on reading before the afternoon becomes busy.",
      "creator_id": "cap_a0c542bd72a3_warm_2"
    },
    "output": {
      "confidence": 0.4515,
      "content_id": "168675ab-aa45-4d2c-8fa6-4a110786c3f0",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.3528,
      "status": "decided",
      "style_score": 0.5502
    },
    "http_status": 200,
    "duration_seconds": 0.20422039999994013
  },
  {
    "timestamp": "2026-11-23T07:26:40.558501+00:00",
    "request_id": "cf6ea546-6361-437e-92b9-b15e0586cfad",
    "method": "POST",
    "path": "/submit",
    "query": "",
    "input": {
      "text": "Our neighborhood library opened a small reading room beside the main entrance last spring. Volunteers arranged comfortable chairs near the windows and placed a collection of donated books on wooden shelves for visitors of different ages. I visit on Saturday mornings because the quiet space helps me concentrate on reading before the afternoon becomes busy.",
      "creator_id": "cap_a0c542bd72a3_valid_2_0"
    },
    "output": {
      "confidence": 0.4515,
      "content_id": "38ad1a93-87fa-443f-88a6-fa3711e3bd05",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.3528,
      "status": "decided",
      "style_score": 0.5502
    },
    "http_status": 200,
    "duration_seconds": 0.19460030000027473
  },
  {
    "timestamp": "2026-11-23T07:26:40.759023+00:00",
    "request_id": "1d9d2df3-d7c9-4254-b1dd-5d82c9ecb531",
    "method": "POST",
    "path": "/submit",
    "query": "",
    "input": {
      "text": "The community garden has become a useful meeting place for people who live on our street. Each weekend several neighbors bring tools and spend an hour watering vegetables or removing weeds from the narrow paths between the planting beds. Working together gives everyone a chance to share practical advice while producing fresh food for their families.",
      "creator_id": "cap_a0c542bd72a3_valid_2_1"
    },
    "output": {
      "confidence": 0.48119999999999996,
      "content_id": "21f78e44-a3b9-436c-9394-144f13af4c63",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.4332,
      "status": "decided",
      "style_score": 0.5292
    },
    "http_status": 200,
    "duration_seconds": 0.19042499999977736
  },
  {
    "timestamp": "2026-11-23T07:26:40.970929+00:00",
    "request_id": "d27bdf45-4435-4c52-bff7-58c77e2cfc83",
    "method": "POST",
    "path": "/submit",
    "query": "",
    "input": {
      "text": "Preparing a weekly schedule helps me balance coursework with responsibilities at home and time with friends. I begin by listing important deadlines and then divide larger assignments into smaller tasks that fit into the available hours on different days. The plan sometimes changes, but having a clear starting point makes it easier to decide what needs attention.",
      "creator_id": "cap_a0c542bd72a3_valid_2_2"
    },
    "output": {
      "confidence": 0.53235,
      "content_id": "e6ce3165-79b4-42eb-95ec-3f51243cec26",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.5226,
      "status": "decided",
      "style_score": 0.5421
    },
    "http_status": 200,
    "duration_seconds": 0.18067380000047706
  },
  {
    "timestamp": "2026-11-23T07:26:41.171345+00:00",
    "request_id": "6bf38166-cddc-4b03-bcd8-f5aefcce2336",
    "method": "POST",
    "path": "/submit",
    "query": "",
    "input": {
      "text": "",
      "creator_id": "cap_a0c542bd72a3_empty_2_0"
    },
    "output": {
      "error": "text must be a non-empty string."
    },
    "http_status": 400,
    "duration_seconds": 0.0024041999995461083
  },
  {
    "timestamp": "2026-11-23T07:26:41.179816+00:00",
    "request_id": "553a8763-f6c4-4782-8d95-b593e03e6b6c",
    "method": "POST",
    "path": "/submit",
    "query": "",
    "input": {
      "text": "",
      "creator_id": "cap_a0c542bd72a3_empty_2_1"
    },
    "output": {
      "error": "text must be a non-empty string."
    },
    "http_status": 400,
    "duration_seconds": 0.0017397999999957392
  },
  {
    "timestamp": "2026-11-23T07:26:41.207866+00:00",
    "request_id": "3593da56-eeb3-48ee-9c0c-44befd2cbfb1",
    "method": "POST",
    "path": "/submit",
    "query": "",
    "input": {
      "text": "",
      "creator_id": "cap_a0c542bd72a3_empty_2_2"
    },
    "output": {
      "error": "text must be a non-empty string."
    },
    "http_status": 400,
    "duration_seconds": 0.002612000000226544
  },
  {
    "timestamp": "2026-11-23T07:26:41.215063+00:00",
    "request_id": "666555e4-bdb1-4f22-88f3-086fc1a982eb",
    "method": "POST",
    "path": "/submit",
    "query": "",
    "input": {
      "text": "Our neighborhood library opened a small reading room beside the main entrance last spring. Volunteers arranged comfortable chairs near the windows and placed a collection of donated books on wooden shelves for visitors of different ages. I visit on Saturday mornings because the quiet space helps me concentrate on reading before the afternoon becomes busy.",
      "creator_id": "cap_a0c542bd72a3_limit_2"
    },
    "output": {
      "confidence": 0.4515,
      "content_id": "dfe25ea3-f408-496a-a8b9-ed54baa07037",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.3528,
      "status": "decided",
      "style_score": 0.5502
    },
    "http_status": 200,
    "duration_seconds": 0.1985591000002387
  },
  {
    "timestamp": "2026-11-23T07:26:41.434591+00:00",
    "request_id": "9c9fa5f2-9b77-47de-8e92-415125a5d6e1",
    "method": "POST",
    "path": "/submit",
    "query": "",
    "input": {
      "text": "The community garden has become a useful meeting place for people who live on our street. Each weekend several neighbors bring tools and spend an hour watering vegetables or removing weeds from the narrow paths between the planting beds. Working together gives everyone a chance to share practical advice while producing fresh food for their families.",
      "creator_id": "cap_a0c542bd72a3_limit_2"
    },
    "output": {
      "confidence": 0.48119999999999996,
      "content_id": "0f5264c9-b536-46fe-94fd-caf5649b6828",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.4332,
      "status": "decided",
      "style_score": 0.5292
    },
    "http_status": 200,
    "duration_seconds": 0.1940375000003769
  },
  {
    "timestamp": "2026-11-23T07:26:41.635092+00:00",
    "request_id": "aa526fa6-9aa2-462e-b30b-83a53e3c4614",
    "method": "POST",
    "path": "/submit",
    "query": "",
    "input": {
      "text": "Preparing a weekly schedule helps me balance coursework with responsibilities at home and time with friends. I begin by listing important deadlines and then divide larger assignments into smaller tasks that fit into the available hours on different days. The plan sometimes changes, but having a clear starting point makes it easier to decide what needs attention.",
      "creator_id": "cap_a0c542bd72a3_limit_2"
    },
    "output": {
      "confidence": 0.53235,
      "content_id": "0cf4131d-04b0-4cb5-ad58-f5daa77462fc",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.5226,
      "status": "decided",
      "style_score": 0.5421
    },
    "http_status": 200,
    "duration_seconds": 0.19854829999985668
  },
  {
    "timestamp": "2026-11-23T07:26:41.860857+00:00",
    "request_id": "9fd62b40-f81b-496a-a32a-77c16a0b1320",
    "method": "POST",
    "path": "/submit",
    "query": "",
    "input": {
      "text": "Our neighborhood library opened a small reading room beside the main entrance last spring. Volunteers arranged comfortable chairs near the windows and placed a collection of donated books on wooden shelves for visitors of different ages. I visit on Saturday mornings because the quiet space helps me concentrate on reading before the afternoon becomes busy.",
      "creator_id": "cap_a0c542bd72a3_limit_2"
    },
    "output": {
      "confidence": 0.4515,
      "content_id": "b6465a46-9080-49c2-a8cb-24656cfbcec8",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.3528,
      "status": "decided",
      "style_score": 0.5502
    },
    "http_status": 200,
    "duration_seconds": 0.17629459999989194
  },
  {
    "timestamp": "2026-11-23T07:26:42.044450+00:00",
    "request_id": "8f11347c-de56-4d15-9c98-57a97c031bc8",
    "method": "POST",
    "path": "/submit",
    "query": "",
    "input": {
      "text": "The community garden has become a useful meeting place for people who live on our street. Each weekend several neighbors bring tools and spend an hour watering vegetables or removing weeds from the narrow paths between the planting beds. Working together gives everyone a chance to share practical advice while producing fresh food for their families.",
      "creator_id": "cap_a0c542bd72a3_limit_2"
    },
    "output": {
      "confidence": 0.48119999999999996,
      "content_id": "a25335b5-2df5-4958-a155-e5be6d3291a5",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.4332,
      "status": "decided",
      "style_score": 0.5292
    },
    "http_status": 200,
    "duration_seconds": 0.176456700000017
  },
  {
    "timestamp": "2026-11-23T07:26:42.239456+00:00",
    "request_id": "47bb07b5-27eb-429c-8393-746e4a3ffa7b",
    "method": "POST",
    "path": "/submit",
    "query": "",
    "input": {
      "text": "Preparing a weekly schedule helps me balance coursework with responsibilities at home and time with friends. I begin by listing important deadlines and then divide larger assignments into smaller tasks that fit into the available hours on different days. The plan sometimes changes, but having a clear starting point makes it easier to decide what needs attention.",
      "creator_id": "cap_a0c542bd72a3_limit_2"
    },
    "output": {
      "confidence": 0.53235,
      "content_id": "5903157f-c72b-41da-b51d-a9fc851f668e",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.5226,
      "status": "decided",
      "style_score": 0.5421
    },
    "http_status": 200,
    "duration_seconds": 0.1806827999998859
  },
  {
    "timestamp": "2026-11-23T07:26:42.440297+00:00",
    "request_id": "a5a0b3f5-4713-4cf2-9971-6186f2f1e99b",
    "method": "POST",
    "path": "/submit",
    "query": "",
    "input": {
      "text": "Our neighborhood library opened a small reading room beside the main entrance last spring. Volunteers arranged comfortable chairs near the windows and placed a collection of donated books on wooden shelves for visitors of different ages. I visit on Saturday mornings because the quiet space helps me concentrate on reading before the afternoon becomes busy.",
      "creator_id": "cap_a0c542bd72a3_limit_2"
    },
    "output": {
      "confidence": 0.4515,
      "content_id": "076aaad4-3ded-40e4-a251-ccfe87d72589",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.3528,
      "status": "decided",
      "style_score": 0.5502
    },
    "http_status": 200,
    "duration_seconds": 0.17307700000037585
  },
  {
    "timestamp": "2026-11-23T07:26:42.628105+00:00",
    "request_id": "76baa133-e61d-48d9-8a82-7d1ea129127d",
    "method": "POST",
    "path": "/submit",
    "query": "",
    "input": {
      "text": "The community garden has become a useful meeting place for people who live on our street. Each weekend several neighbors bring tools and spend an hour watering vegetables or removing weeds from the narrow paths between the planting beds. Working together gives everyone a chance to share practical advice while producing fresh food for their families.",
      "creator_id": "cap_a0c542bd72a3_limit_2"
    },
    "output": {
      "confidence": 0.48119999999999996,
      "content_id": "914f3db0-ac0e-400c-aeee-db8a3e783b51",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.4332,
      "status": "decided",
      "style_score": 0.5292
    },
    "http_status": 200,
    "duration_seconds": 0.17251889999988634
  },
  {
    "timestamp": "2026-11-23T07:26:42.806793+00:00",
    "request_id": "8e6a0240-57a6-4dc0-9bab-72e9b3682798",
    "method": "POST",
    "path": "/submit",
    "query": "",
    "input": {
      "text": "Preparing a weekly schedule helps me balance coursework with responsibilities at home and time with friends. I begin by listing important deadlines and then divide larger assignments into smaller tasks that fit into the available hours on different days. The plan sometimes changes, but having a clear starting point makes it easier to decide what needs attention.",
      "creator_id": "cap_a0c542bd72a3_limit_2"
    },
    "output": {
      "confidence": 0.53235,
      "content_id": "762b3b49-850b-4e40-846e-a4a9ba0f5543",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.5226,
      "status": "decided",
      "style_score": 0.5421
    },
    "http_status": 200,
    "duration_seconds": 0.18346670000028098
  },
  {
    "timestamp": "2026-11-23T07:26:43.010669+00:00",
    "request_id": "b41ff976-8da4-4ac4-89b9-9738b2d41a6a",
    "method": "POST",
    "path": "/submit",
    "query": "",
    "input": {
      "text": "Our neighborhood library opened a small reading room beside the main entrance last spring. Volunteers arranged comfortable chairs near the windows and placed a collection of donated books on wooden shelves for visitors of different ages. I visit on Saturday mornings because the quiet space helps me concentrate on reading before the afternoon becomes busy.",
      "creator_id": "cap_a0c542bd72a3_limit_2"
    },
    "output": {
      "confidence": 0.4515,
      "content_id": "fbc62f9e-1c1c-49c0-a8f5-3e9bd0a79f4c",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.3528,
      "status": "decided",
      "style_score": 0.5502
    },
    "http_status": 200,
    "duration_seconds": 0.16769050000038987
  },
  {
    "timestamp": "2026-11-23T07:26:43.199176+00:00",
    "request_id": "a4adae5e-a07f-4598-a66f-1432e48a7821",
    "method": "POST",
    "path": "/submit",
    "query": "",
    "input": {
      "text": "The community garden has become a useful meeting place for people who live on our street. Each weekend several neighbors bring tools and spend an hour watering vegetables or removing weeds from the narrow paths between the planting beds. Working together gives everyone a chance to share practical advice while producing fresh food for their families.",
      "creator_id": "cap_a0c542bd72a3_limit_2"
    },
    "output": {
      "error": "rate_limited",
      "limit": "10 per 1 minute",
      "message": "Too many submissions. Try again shortly."
    },
    "http_status": 429,
    "duration_seconds": 0.0024179000001822715
  },
  {
    "timestamp": "2026-11-23T07:26:43.339517+00:00",
    "request_id": "18da6ad1-7049-4cff-b3a5-f3a31276bc6f",
    "method": "POST",
    "path": "/submit",
    "query": "",
    "input": {
      "text": "Our neighborhood library opened a small reading room beside the main entrance last spring. Volunteers arranged comfortable chairs near the windows and placed a collection of donated books on wooden shelves for visitors of different ages. I visit on Saturday mornings because the quiet space helps me concentrate on reading before the afternoon becomes busy.",
      "creator_id": "cap_a0c542bd72a3_warm_3"
    },
    "output": {
      "confidence": 0.4515,
      "content_id": "467d9828-f211-4b45-9903-aab195ffc7b4",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.3528,
      "status": "decided",
      "style_score": 0.5502
    },
    "http_status": 200,
    "duration_seconds": 0.17726190000030329
  },
  {
    "timestamp": "2026-11-23T07:26:43.533511+00:00",
    "request_id": "54fc9479-0032-4d2d-ba6a-821f27a65eac",
    "method": "POST",
    "path": "/submit",
    "query": "",
    "input": {
      "text": "Our neighborhood library opened a small reading room beside the main entrance last spring. Volunteers arranged comfortable chairs near the windows and placed a collection of donated books on wooden shelves for visitors of different ages. I visit on Saturday mornings because the quiet space helps me concentrate on reading before the afternoon becomes busy.",
      "creator_id": "cap_a0c542bd72a3_valid_3_0"
    },
    "output": {
      "confidence": 0.4515,
      "content_id": "9ea51b37-3528-45f0-8b61-a324e3762116",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.3528,
      "status": "decided",
      "style_score": 0.5502
    },
    "http_status": 200,
    "duration_seconds": 0.1679439999998067
  },
  {
    "timestamp": "2026-11-23T07:26:43.707152+00:00",
    "request_id": "0f52a222-9103-448b-8763-7b8420cf6d0c",
    "method": "POST",
    "path": "/submit",
    "query": "",
    "input": {
      "text": "The community garden has become a useful meeting place for people who live on our street. Each weekend several neighbors bring tools and spend an hour watering vegetables or removing weeds from the narrow paths between the planting beds. Working together gives everyone a chance to share practical advice while producing fresh food for their families.",
      "creator_id": "cap_a0c542bd72a3_valid_3_1"
    },
    "output": {
      "confidence": 0.48119999999999996,
      "content_id": "70ac3a28-98de-45da-96c3-f18197a845da",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.4332,
      "status": "decided",
      "style_score": 0.5292
    },
    "http_status": 200,
    "duration_seconds": 0.17781819999981963
  },
  {
    "timestamp": "2026-11-23T07:26:43.910184+00:00",
    "request_id": "6ebc90ab-c7ad-4cbb-81de-f59c98ce06ac",
    "method": "POST",
    "path": "/submit",
    "query": "",
    "input": {
      "text": "Preparing a weekly schedule helps me balance coursework with responsibilities at home and time with friends. I begin by listing important deadlines and then divide larger assignments into smaller tasks that fit into the available hours on different days. The plan sometimes changes, but having a clear starting point makes it easier to decide what needs attention.",
      "creator_id": "cap_a0c542bd72a3_valid_3_2"
    },
    "output": {
      "confidence": 0.53235,
      "content_id": "2e76d6a8-2629-4bbd-b880-f8f6e4ea86f9",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.5226,
      "status": "decided",
      "style_score": 0.5421
    },
    "http_status": 200,
    "duration_seconds": 0.1785184999998819
  },
  {
    "timestamp": "2026-11-23T07:26:44.113186+00:00",
    "request_id": "5afe59a1-0a4b-4c31-a6f6-baf7e801cd6d",
    "method": "POST",
    "path": "/submit",
    "query": "",
    "input": {
      "text": "",
      "creator_id": "cap_a0c542bd72a3_empty_3_0"
    },
    "output": {
      "error": "text must be a non-empty string."
    },
    "http_status": 400,
    "duration_seconds": 0.0026090999999723863
  },
  {
    "timestamp": "2026-11-23T07:26:44.123456+00:00",
    "request_id": "4e86bbd8-d8c4-40d9-a30b-b4e1bbcef653",
    "method": "POST",
    "path": "/submit",
    "query": "",
    "input": {
      "text": "",
      "creator_id": "cap_a0c542bd72a3_empty_3_1"
    },
    "output": {
      "error": "text must be a non-empty string."
    },
    "http_status": 400,
    "duration_seconds": 0.00179649999972753
  },
  {
    "timestamp": "2026-11-23T07:26:44.130917+00:00",
    "request_id": "d616230b-85f5-48b5-ba94-4c08064e1fa6",
    "method": "POST",
    "path": "/submit",
    "query": "",
    "input": {
      "text": "",
      "creator_id": "cap_a0c542bd72a3_empty_3_2"
    },
    "output": {
      "error": "text must be a non-empty string."
    },
    "http_status": 400,
    "duration_seconds": 0.0023584000000482774
  },
  {
    "timestamp": "2026-11-23T07:26:44.153401+00:00",
    "request_id": "14ae1bc5-ec16-41a2-91da-6967bdac30fe",
    "method": "POST",
    "path": "/submit",
    "query": "",
    "input": {
      "text": "Our neighborhood library opened a small reading room beside the main entrance last spring. Volunteers arranged comfortable chairs near the windows and placed a collection of donated books on wooden shelves for visitors of different ages. I visit on Saturday mornings because the quiet space helps me concentrate on reading before the afternoon becomes busy.",
      "creator_id": "cap_a0c542bd72a3_limit_3"
    },
    "output": {
      "confidence": 0.4515,
      "content_id": "be9775d8-39c9-41e9-a4a0-0e4048c48f0c",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.3528,
      "status": "decided",
      "style_score": 0.5502
    },
    "http_status": 200,
    "duration_seconds": 0.17085429999951884
  },
  {
    "timestamp": "2026-11-23T07:26:44.331033+00:00",
    "request_id": "d56ad1d4-b4f8-4283-bf73-63dbaea8069e",
    "method": "POST",
    "path": "/submit",
    "query": "",
    "input": {
      "text": "The community garden has become a useful meeting place for people who live on our street. Each weekend several neighbors bring tools and spend an hour watering vegetables or removing weeds from the narrow paths between the planting beds. Working together gives everyone a chance to share practical advice while producing fresh food for their families.",
      "creator_id": "cap_a0c542bd72a3_limit_3"
    },
    "output": {
      "confidence": 0.48119999999999996,
      "content_id": "31d73e06-c4a9-4c81-b227-2a6c27f70bab",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.4332,
      "status": "decided",
      "style_score": 0.5292
    },
    "http_status": 200,
    "duration_seconds": 0.1764895999995133
  },
  {
    "timestamp": "2026-11-23T07:26:44.528974+00:00",
    "request_id": "49277b2e-c8cc-4bd2-935f-86706d0c4ba2",
    "method": "POST",
    "path": "/submit",
    "query": "",
    "input": {
      "text": "Preparing a weekly schedule helps me balance coursework with responsibilities at home and time with friends. I begin by listing important deadlines and then divide larger assignments into smaller tasks that fit into the available hours on different days. The plan sometimes changes, but having a clear starting point makes it easier to decide what needs attention.",
      "creator_id": "cap_a0c542bd72a3_limit_3"
    },
    "output": {
      "confidence": 0.53235,
      "content_id": "a8bf71ca-b885-492b-8f51-59982956b820",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.5226,
      "status": "decided",
      "style_score": 0.5421
    },
    "http_status": 200,
    "duration_seconds": 0.1812370000006922
  },
  {
    "timestamp": "2026-11-23T07:26:44.716221+00:00",
    "request_id": "5ae24f5e-f062-4d19-a620-3897d6c91596",
    "method": "POST",
    "path": "/submit",
    "query": "",
    "input": {
      "text": "Our neighborhood library opened a small reading room beside the main entrance last spring. Volunteers arranged comfortable chairs near the windows and placed a collection of donated books on wooden shelves for visitors of different ages. I visit on Saturday mornings because the quiet space helps me concentrate on reading before the afternoon becomes busy.",
      "creator_id": "cap_a0c542bd72a3_limit_3"
    },
    "output": {
      "confidence": 0.4515,
      "content_id": "d2733976-edf8-4266-99fc-1d1a4addf891",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.3528,
      "status": "decided",
      "style_score": 0.5502
    },
    "http_status": 200,
    "duration_seconds": 0.17072559999996884
  },
  {
    "timestamp": "2026-11-23T07:26:44.905603+00:00",
    "request_id": "cdebdbcc-00ae-4aa4-9dc7-9e2993b9847a",
    "method": "POST",
    "path": "/submit",
    "query": "",
    "input": {
      "text": "The community garden has become a useful meeting place for people who live on our street. Each weekend several neighbors bring tools and spend an hour watering vegetables or removing weeds from the narrow paths between the planting beds. Working together gives everyone a chance to share practical advice while producing fresh food for their families.",
      "creator_id": "cap_a0c542bd72a3_limit_3"
    },
    "output": {
      "confidence": 0.48119999999999996,
      "content_id": "eb39169a-e976-4eb0-8366-905d8a5b5e66",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.4332,
      "status": "decided",
      "style_score": 0.5292
    },
    "http_status": 200,
    "duration_seconds": 0.16826429999946413
  },
  {
    "timestamp": "2026-11-23T07:26:45.087840+00:00",
    "request_id": "dddc6a07-b1a3-479f-b010-f292c2dd8215",
    "method": "POST",
    "path": "/submit",
    "query": "",
    "input": {
      "text": "Preparing a weekly schedule helps me balance coursework with responsibilities at home and time with friends. I begin by listing important deadlines and then divide larger assignments into smaller tasks that fit into the available hours on different days. The plan sometimes changes, but having a clear starting point makes it easier to decide what needs attention.",
      "creator_id": "cap_a0c542bd72a3_limit_3"
    },
    "output": {
      "confidence": 0.53235,
      "content_id": "056a6684-5fa1-4d3e-bad2-63b61d2fc958",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.5226,
      "status": "decided",
      "style_score": 0.5421
    },
    "http_status": 200,
    "duration_seconds": 0.17758599999979197
  },
  {
    "timestamp": "2026-11-23T07:26:45.282087+00:00",
    "request_id": "0639f51b-c586-418f-9654-d7d3223fbe63",
    "method": "POST",
    "path": "/submit",
    "query": "",
    "input": {
      "text": "Our neighborhood library opened a small reading room beside the main entrance last spring. Volunteers arranged comfortable chairs near the windows and placed a collection of donated books on wooden shelves for visitors of different ages. I visit on Saturday mornings because the quiet space helps me concentrate on reading before the afternoon becomes busy.",
      "creator_id": "cap_a0c542bd72a3_limit_3"
    },
    "output": {
      "confidence": 0.4515,
      "content_id": "f65f8b56-9e66-4bde-a97c-aa1063442831",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.3528,
      "status": "decided",
      "style_score": 0.5502
    },
    "http_status": 200,
    "duration_seconds": 0.16870180000023538
  },
  {
    "timestamp": "2026-11-23T07:26:45.464088+00:00",
    "request_id": "0fb212bb-412d-46e9-9995-43a428b04f4b",
    "method": "POST",
    "path": "/submit",
    "query": "",
    "input": {
      "text": "The community garden has become a useful meeting place for people who live on our street. Each weekend several neighbors bring tools and spend an hour watering vegetables or removing weeds from the narrow paths between the planting beds. Working together gives everyone a chance to share practical advice while producing fresh food for their families.",
      "creator_id": "cap_a0c542bd72a3_limit_3"
    },
    "output": {
      "confidence": 0.48119999999999996,
      "content_id": "489ec658-d3a2-4f7f-a93f-4ea58fe0ecad",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.4332,
      "status": "decided",
      "style_score": 0.5292
    },
    "http_status": 200,
    "duration_seconds": 0.1700881999995545
  },
  {
    "timestamp": "2026-11-23T07:26:45.652177+00:00",
    "request_id": "aa7b44a9-ed99-4f17-8db2-b5adf13979cb",
    "method": "POST",
    "path": "/submit",
    "query": "",
    "input": {
      "text": "Preparing a weekly schedule helps me balance coursework with responsibilities at home and time with friends. I begin by listing important deadlines and then divide larger assignments into smaller tasks that fit into the available hours on different days. The plan sometimes changes, but having a clear starting point makes it easier to decide what needs attention.",
      "creator_id": "cap_a0c542bd72a3_limit_3"
    },
    "output": {
      "confidence": 0.53235,
      "content_id": "8d44b73e-b167-4965-b1d6-5daddc369ddd",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.5226,
      "status": "decided",
      "style_score": 0.5421
    },
    "http_status": 200,
    "duration_seconds": 0.17594499999995605
  },
  {
    "timestamp": "2026-11-23T07:26:45.846676+00:00",
    "request_id": "45b21783-5a23-4bbe-8681-1eb244927751",
    "method": "POST",
    "path": "/submit",
    "query": "",
    "input": {
      "text": "Our neighborhood library opened a small reading room beside the main entrance last spring. Volunteers arranged comfortable chairs near the windows and placed a collection of donated books on wooden shelves for visitors of different ages. I visit on Saturday mornings because the quiet space helps me concentrate on reading before the afternoon becomes busy.",
      "creator_id": "cap_a0c542bd72a3_limit_3"
    },
    "output": {
      "confidence": 0.4515,
      "content_id": "20e4b250-4c0d-46ba-b625-ef213717a000",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.3528,
      "status": "decided",
      "style_score": 0.5502
    },
    "http_status": 200,
    "duration_seconds": 0.16991890000008425
  },
  {
    "timestamp": "2026-11-23T07:26:46.034796+00:00",
    "request_id": "6ce666d7-d558-4cd2-8219-ddd9e6b046dd",
    "method": "POST",
    "path": "/submit",
    "query": "",
    "input": {
      "text": "The community garden has become a useful meeting place for people who live on our street. Each weekend several neighbors bring tools and spend an hour watering vegetables or removing weeds from the narrow paths between the planting beds. Working together gives everyone a chance to share practical advice while producing fresh food for their families.",
      "creator_id": "cap_a0c542bd72a3_limit_3"
    },
    "output": {
      "error": "rate_limited",
      "limit": "10 per 1 minute",
      "message": "Too many submissions. Try again shortly."
    },
    "http_status": 429,
    "duration_seconds": 0.002331199999389355
  },
  {
    "timestamp": "2026-11-23T07:26:46.178451+00:00",
    "request_id": "35b0dad3-c3a0-4bdd-bfcf-8d93ac62f53d",
    "method": "POST",
    "path": "/submit",
    "query": "",
    "input": {
      "text": "Our neighborhood library opened a small reading room beside the main entrance last spring. Volunteers arranged comfortable chairs near the windows and placed a collection of donated books on wooden shelves for visitors of different ages. I visit on Saturday mornings because the quiet space helps me concentrate on reading before the afternoon becomes busy.",
      "creator_id": "cap_a0c542bd72a3_cost_0"
    },
    "output": {
      "confidence": 0.4515,
      "content_id": "0c577435-1de6-48e1-9851-760a802d895e",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.3528,
      "status": "decided",
      "style_score": 0.5502
    },
    "http_status": 200,
    "duration_seconds": 0.17849529999966762
  },
  {
    "timestamp": "2026-11-23T07:26:46.362930+00:00",
    "request_id": "e6ab6956-30c7-4d6d-bc11-641ef44ca720",
    "method": "POST",
    "path": "/submit",
    "query": "",
    "input": {
      "text": "The community garden has become a useful meeting place for people who live on our street. Each weekend several neighbors bring tools and spend an hour watering vegetables or removing weeds from the narrow paths between the planting beds. Working together gives everyone a chance to share practical advice while producing fresh food for their families.",
      "creator_id": "cap_a0c542bd72a3_cost_1"
    },
    "output": {
      "confidence": 0.48119999999999996,
      "content_id": "7431da64-4e38-4550-8f61-7e18f2cbe8b5",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.4332,
      "status": "decided",
      "style_score": 0.5292
    },
    "http_status": 200,
    "duration_seconds": 0.16969129999961297
  },
  {
    "timestamp": "2026-11-23T07:26:46.550443+00:00",
    "request_id": "b5a50b79-67ff-45eb-b76e-0c0361d7ee7f",
    "method": "POST",
    "path": "/submit",
    "query": "",
    "input": {
      "text": "Preparing a weekly schedule helps me balance coursework with responsibilities at home and time with friends. I begin by listing important deadlines and then divide larger assignments into smaller tasks that fit into the available hours on different days. The plan sometimes changes, but having a clear starting point makes it easier to decide what needs attention.",
      "creator_id": "cap_a0c542bd72a3_cost_2"
    },
    "output": {
      "confidence": 0.53235,
      "content_id": "6177d181-917c-484b-a66d-3119622b5b73",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.5226,
      "status": "decided",
      "style_score": 0.5421
    },
    "http_status": 200,
    "duration_seconds": 0.18327059999955964
  },
  {
    "timestamp": "2026-11-23T07:26:46.739567+00:00",
    "request_id": "8e2d5adf-aa66-4023-aa1a-04570213a8e9",
    "method": "POST",
    "path": "/submit",
    "query": "",
    "input": {
      "text": "Our neighborhood library opened a small reading room beside the main entrance last spring. Volunteers arranged comfortable chairs near the windows and placed a collection of donated books on wooden shelves for visitors of different ages. I visit on Saturday mornings because the quiet space helps me concentrate on reading before the afternoon becomes busy.",
      "creator_id": "cap_a0c542bd72a3_cost_3"
    },
    "output": {
      "confidence": 0.4515,
      "content_id": "51039a52-3d1e-4aa2-9ef3-66a5efb5bbe7",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.3528,
      "status": "decided",
      "style_score": 0.5502
    },
    "http_status": 200,
    "duration_seconds": 0.1731707999997525
  },
  {
    "timestamp": "2026-11-23T07:26:46.927206+00:00",
    "request_id": "9d1f80b4-697f-44ca-b55d-10d0b48757b4",
    "method": "POST",
    "path": "/submit",
    "query": "",
    "input": {
      "text": "The community garden has become a useful meeting place for people who live on our street. Each weekend several neighbors bring tools and spend an hour watering vegetables or removing weeds from the narrow paths between the planting beds. Working together gives everyone a chance to share practical advice while producing fresh food for their families.",
      "creator_id": "cap_a0c542bd72a3_cost_4"
    },
    "output": {
      "confidence": 0.48119999999999996,
      "content_id": "f5408c99-3213-4f71-be2a-5888d9c8c5f6",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.4332,
      "status": "decided",
      "style_score": 0.5292
    },
    "http_status": 200,
    "duration_seconds": 0.17301140000017767
  },
  {
    "timestamp": "2026-11-23T07:26:47.115884+00:00",
    "request_id": "3b1f6354-07cb-40a6-9bd3-65c9d7ac4d1e",
    "method": "POST",
    "path": "/submit",
    "query": "",
    "input": {
      "text": "Preparing a weekly schedule helps me balance coursework with responsibilities at home and time with friends. I begin by listing important deadlines and then divide larger assignments into smaller tasks that fit into the available hours on different days. The plan sometimes changes, but having a clear starting point makes it easier to decide what needs attention.",
      "creator_id": "cap_a0c542bd72a3_cost_5"
    },
    "output": {
      "confidence": 0.53235,
      "content_id": "983ab80d-93c1-4bb3-8592-32c9fe1d0e73",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.5226,
      "status": "decided",
      "style_score": 0.5421
    },
    "http_status": 200,
    "duration_seconds": 0.18168960000002699
  },
  {
    "timestamp": "2026-11-23T07:26:47.316262+00:00",
    "request_id": "5360efbe-b36e-46d5-bc10-9f7a99896eef",
    "method": "POST",
    "path": "/submit",
    "query": "",
    "input": {
      "text": "Our neighborhood library opened a small reading room beside the main entrance last spring. Volunteers arranged comfortable chairs near the windows and placed a collection of donated books on wooden shelves for visitors of different ages. I visit on Saturday mornings because the quiet space helps me concentrate on reading before the afternoon becomes busy.",
      "creator_id": "cap_a0c542bd72a3_cost_6"
    },
    "output": {
      "confidence": 0.4515,
      "content_id": "da5988ee-35cb-45fc-b0db-ee41cf5ff0a0",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.3528,
      "status": "decided",
      "style_score": 0.5502
    },
    "http_status": 200,
    "duration_seconds": 0.18868569999995088
  },
  {
    "timestamp": "2026-11-23T07:26:47.510459+00:00",
    "request_id": "78987031-c489-4d70-b35a-8d424f44c3e9",
    "method": "POST",
    "path": "/submit",
    "query": "",
    "input": {
      "text": "The community garden has become a useful meeting place for people who live on our street. Each weekend several neighbors bring tools and spend an hour watering vegetables or removing weeds from the narrow paths between the planting beds. Working together gives everyone a chance to share practical advice while producing fresh food for their families.",
      "creator_id": "cap_a0c542bd72a3_cost_7"
    },
    "output": {
      "confidence": 0.48119999999999996,
      "content_id": "ae5ae8e6-799c-42a7-ada9-99409d90b6f1",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.4332,
      "status": "decided",
      "style_score": 0.5292
    },
    "http_status": 200,
    "duration_seconds": 0.18897259999994276
  },
  {
    "timestamp": "2026-11-23T07:26:47.708115+00:00",
    "request_id": "61053914-41dc-4da2-b1ce-1c86ba33d4b5",
    "method": "POST",
    "path": "/submit",
    "query": "",
    "input": {
      "text": "Preparing a weekly schedule helps me balance coursework with responsibilities at home and time with friends. I begin by listing important deadlines and then divide larger assignments into smaller tasks that fit into the available hours on different days. The plan sometimes changes, but having a clear starting point makes it easier to decide what needs attention.",
      "creator_id": "cap_a0c542bd72a3_cost_8"
    },
    "output": {
      "confidence": 0.53235,
      "content_id": "e2707d8f-00d3-4faf-9639-bc64d029d408",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.5226,
      "status": "decided",
      "style_score": 0.5421
    },
    "http_status": 200,
    "duration_seconds": 0.18230099999982485
  },
  {
    "timestamp": "2026-11-23T07:26:47.895570+00:00",
    "request_id": "c2adfb7f-8de7-4ab6-bc41-24964b14b350",
    "method": "POST",
    "path": "/submit",
    "query": "",
    "input": {
      "text": "Our neighborhood library opened a small reading room beside the main entrance last spring. Volunteers arranged comfortable chairs near the windows and placed a collection of donated books on wooden shelves for visitors of different ages. I visit on Saturday mornings because the quiet space helps me concentrate on reading before the afternoon becomes busy.",
      "creator_id": "cap_a0c542bd72a3_cost_9"
    },
    "output": {
      "confidence": 0.4515,
      "content_id": "a732bbb6-a5d5-42b6-853c-5e4619d4c6f9",
      "guess": "unsure",
      "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
      "model_score": 0.3528,
      "status": "decided",
      "style_score": 0.5502
    },
    "http_status": 200,
    "duration_seconds": 0.15894339999977092
  }
]
```
