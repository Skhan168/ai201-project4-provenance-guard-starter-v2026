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