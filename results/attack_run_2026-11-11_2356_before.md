# Attack run — before

- Produced by: `run_attacks.py::main`
- Service: `app.py::submit`
- 56 attacks · 2026-11-11 23:56
- Auto-marked BROKE (5xx, crash, no response): **0**
- Left for you to judge: **56**

The Verdict column is blank where a script can't honestly decide. Whether
an evasion worked depends on where you put your thresholds — read the
`targets` column, look at what came back, and write HELD or BROKE yourself.

Each attack submits as creator_id `attacker_<id>`, and the content_id it
came back with is in the table — either one will match this run against your
audit log when you go looking for the ten entries to paste.

| ID | Family | Targeting | Status | Content ID | Guess | Score | Verdict |
|---|---|---|---|---|---|---|---|
| EV01 | evasion | signal two: typos raise word variety | 200 | `3afd3622-3aed-4eca-9122-3fce532e1a23` | unsure | 0.363 |  |
| EV02 | evasion | signal two: broken-up sentences raise length spread | 200 | `e504a427-ea02-4baa-8bfa-113a2e554a6a` | unsure | 0.388 |  |
| EV03 | evasion | signal two: a pasted quotation changes the shape | 200 | `caeaa55f-d33f-4821-9551-c16e76975f85` | unsure | 0.538 |  |
| EV04 | evasion | signal one: unusual words raise perplexity | 200 | `f9f91526-ea7b-45fd-ba9f-060e6f7830c5` | unsure | 0.583 |  |
| EV05 | evasion | both signals: heavy human editing pass | 200 | `ef78b088-d1fe-46ad-9ff8-f43ef06ee206` | human | 0.319 |  |
| EV06 | evasion | signal two: one very long sentence and one very short | 200 | `7210d32e-2244-4298-a789-856fca403590` | human | 0.336 |  |
| EV07 | evasion | signal two: padding with punctuation | 200 | `3107ec37-57be-4eba-93ff-3d9b92876432` | unsure | 0.488 |  |
| EV08 | evasion | signal one: text below the token window | 200 | `9903ff4b-5636-4ca4-853b-d75036905903` | unsure | 0.363 |  |
| EV09 | evasion | both: AI text with a human opening paragraph bolted on | 200 | `b643accf-0ada-4cfa-ba64-e14e659abe95` | unsure | 0.550 |  |
| EV10 | evasion | signal two: repeated stanza structure | 200 | `e9d2ccdc-da8f-4cbe-b8a3-e293b9e528c9` | ai | 0.823 |  |
| FP01 | false_positive | plain, clear human writing with no flourishes | 200 | `01af9434-42dc-494b-836d-1f01220e067e` | unsure | 0.539 |  |
| FP02 | false_positive | human writing in a formal register | 200 | `9e6b1a03-ed4b-4e4b-a6b8-0fdea1563bf1` | ai | 0.661 |  |
| FP03 | false_positive | a non-native English speaker writing carefully | 200 | `97ac69a2-b4f3-4ee3-ac7b-e7dfa1787836` | ai | 0.667 |  |
| FP04 | false_positive | a student essay written to a rubric | 200 | `1ea42c16-0569-4a17-8c18-8ef1748eeab1` | ai | 0.652 |  |
| FP05 | false_positive | technical documentation written by a person | 200 | `083912a8-008c-4790-a513-d47ea7ec6da0` | ai | 0.706 |  |
| FP06 | false_positive | a person imitating a formal template | 200 | `64ec0626-f05b-4b85-811d-c8bfaa424cde` | ai | 0.652 |  |
| FP07 | false_positive | human writing that repeats a phrase deliberately | 200 | `fc9909e7-f87b-4b24-8f2b-2f9b6e428dce` | unsure | 0.646 |  |
| FP08 | false_positive | very short genuine human submission | 200 | `f50f9d7a-3f1c-45b4-a592-4042b0da5d13` | unsure | 0.355 |  |
| PI01 | prompt_injection | instruction to ignore the check | 200 | `f44c2c2e-68e8-4df5-bd05-ecd0427352bd` | unsure | 0.363 |  |
| PI02 | prompt_injection | instruction disguised as a system message | 200 | `7036b9c4-7f34-4d80-a1f6-1a07370e29fb` | human | 0.233 |  |
| PI03 | prompt_injection | instruction wrapped in the writer's voice | 200 | `5939b1bc-a3e9-4ca3-a37a-ced9c12c9079` | unsure | 0.526 |  |
| PI04 | prompt_injection | attempt to make the label text hostile | 200 | `abb91121-45c7-4ad1-b53f-0d3fc069d13d` | unsure | 0.474 |  |
| PI05 | prompt_injection | attempt to inject into the audit log | 200 | `eda8ecb8-8b6a-4ad2-9ca3-a2d084b05e94` | unsure | 0.527 |  |
| PI06 | prompt_injection | instruction plus real human text | 200 | `d8e69f00-e68c-47ce-8831-9442d3ce7aa0` | unsure | 0.512 |  |
| MF01 | malformed | text is only whitespace | 400 | `—` | — | — |  |
| MF02 | malformed | text is a single character | 400 | `—` | — | — |  |
| MF03 | malformed | text is control characters | 200 | `298bb64e-89a6-4e9a-8a21-11975c800e20` | human | 0.150 |  |
| MF04 | malformed | text is only punctuation | 400 | `—` | — | — |  |
| MF05 | malformed | text is a very long single word | 200 | `a0962514-2875-4a51-b8c9-2bfb2d6c77a2` | unsure | 0.649 |  |
| MF06 | malformed | text is emoji only | 400 | `—` | — | — |  |
| MF07 | malformed | text is right-to-left script | 400 | `—` | — | — |  |
| MF08 | malformed | text is 60,000 characters | 413 | `—` | — | — |  |
| RQ01 | malformed | no text field at all | 400 | `—` | — | — |  |
| RQ02 | malformed | no creator_id | 400 | `—` | — | — |  |
| RQ03 | malformed | text is a number | 400 | `—` | — | — |  |
| RQ04 | malformed | text is a list | 400 | `—` | — | — |  |
| RQ05 | malformed | text is null | 400 | `—` | — | — |  |
| RQ06 | malformed | creator_id is an object | 400 | `—` | — | — |  |
| RQ07 | malformed | body is a JSON array, not an object | 400 | `—` | — | — |  |
| RQ08 | malformed | body is unparseable JSON | 400 | `—` | — | — |  |
| RQ09 | malformed | body is empty | 400 | `—` | — | — |  |
| RQ10 | malformed | body is form-encoded, not JSON | 400 | `—` | — | — |  |
| RQ11 | malformed | body is JSON claiming to be plain text | 400 | `—` | — | — |  |
| RQ12 | malformed | deeply nested JSON | 400 | `—` | — | — |  |
| FL01_01 | flood_same_creator | 20 rapid submissions from one creator | 200 | `5cf36efd-46f6-40ea-8c4f-824aed15dae3` | human | 0.164 |  |
| FL01_02 | flood_same_creator | 20 rapid submissions from one creator | 200 | `45b1a41f-b1d0-44db-a8f1-67f9ecf06cef` | human | 0.164 |  |
| FL01_03 | flood_same_creator | 20 rapid submissions from one creator | 200 | `5c947989-d074-4ad5-a895-dc3c103b5e3c` | human | 0.164 |  |
| FL01_04 | flood_same_creator | 20 rapid submissions from one creator | 200 | `8e798ac4-6ad3-4176-ab95-4308feb608c8` | human | 0.164 |  |
| FL01_05 | flood_same_creator | 20 rapid submissions from one creator | 200 | `3bede21b-f3fb-4980-88c0-c967275c11bd` | human | 0.164 |  |
| FL01_06 | flood_same_creator | 20 rapid submissions from one creator | 200 | `2e959734-4c73-4fc1-8d5f-0b91e113cb1c` | human | 0.164 |  |
| FL01_07 | flood_same_creator | 20 rapid submissions from one creator | 200 | `290e4a73-b5f7-419e-bf8e-748cc0324c55` | human | 0.164 |  |
| FL01_08 | flood_same_creator | 20 rapid submissions from one creator | 200 | `0e8eb887-3248-4134-8551-89784568d9d0` | human | 0.164 |  |
| FL01_09 | flood_same_creator | 20 rapid submissions from one creator | 200 | `ecfb4378-fb35-47f4-a91c-812799a98378` | human | 0.164 |  |
| FL01_10 | flood_same_creator | 20 rapid submissions from one creator | 200 | `78f437ad-99ca-43d5-9017-2695d703f51c` | human | 0.164 |  |
| FL01_11 | flood_same_creator | 20 rapid submissions from one creator | 429 | `—` | — | — |  |
| FL01_12 | flood_same_creator | 20 rapid submissions from one creator | 429 | `—` | — | — |  |

---

## By family

| Family | Attacks | Auto-BROKE | Left to judge |
|---|---|---|---|
| `evasion` | 10 | 0 | 10 |
| `false_positive` | 8 | 0 | 8 |
| `flood_same_creator` | 12 | 0 | 12 |
| `malformed` | 20 | 0 | 20 |
| `prompt_injection` | 6 | 0 | 6 |

> The **false_positive** family is the one to look at hardest. Those are
> written to be genuine human writing that reads as machine-like. Every one
> your service calls AI is a real writer it would have accused.

---

## What came back

The detail behind the table. Paste the interesting failures into your
README — the ones that show something, not the ten easiest.

### EV01 — `evasion`

*Targeting:* signal two: typos raise word variety

```json
{
  "id": "EV01",
  "status": 200,
  "content_id": "3afd3622-3aed-4eca-9122-3fce532e1a23",
  "creator_id": "attacker_EV01",
  "guess": "unsure",
  "confidence": 0.363,
  "model_score": 0.1635,
  "style_score": 0.5625,
  "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
  "error": null,
  "verdict": ""
}
```

### EV02 — `evasion`

*Targeting:* signal two: broken-up sentences raise length spread

```json
{
  "id": "EV02",
  "status": 200,
  "content_id": "e504a427-ea02-4baa-8bfa-113a2e554a6a",
  "creator_id": "attacker_EV02",
  "guess": "unsure",
  "confidence": 0.38755,
  "model_score": 0.5943,
  "style_score": 0.1808,
  "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
  "error": null,
  "verdict": ""
}
```

### EV03 — `evasion`

*Targeting:* signal two: a pasted quotation changes the shape

```json
{
  "id": "EV03",
  "status": 200,
  "content_id": "caeaa55f-d33f-4821-9551-c16e76975f85",
  "creator_id": "attacker_EV03",
  "guess": "unsure",
  "confidence": 0.53835,
  "model_score": 0.6662,
  "style_score": 0.4105,
  "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
  "error": null,
  "verdict": ""
}
```

### EV04 — `evasion`

*Targeting:* signal one: unusual words raise perplexity

```json
{
  "id": "EV04",
  "status": 200,
  "content_id": "f9f91526-ea7b-45fd-ba9f-060e6f7830c5",
  "creator_id": "attacker_EV04",
  "guess": "unsure",
  "confidence": 0.5829500000000001,
  "model_score": 0.6114,
  "style_score": 0.5545,
  "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
  "error": null,
  "verdict": ""
}
```

### EV05 — `evasion`

*Targeting:* both signals: heavy human editing pass

```json
{
  "id": "EV05",
  "status": 200,
  "content_id": "ef78b088-d1fe-46ad-9ff8-f43ef06ee206",
  "creator_id": "attacker_EV05",
  "guess": "human",
  "confidence": 0.3194,
  "model_score": 0.3212,
  "style_score": 0.3176,
  "label": "This text shows patterns associated with human writing. This assessment does not verify who wrote it.",
  "error": null,
  "verdict": ""
}
```

### EV06 — `evasion`

*Targeting:* signal two: one very long sentence and one very short

```json
{
  "id": "EV06",
  "status": 200,
  "content_id": "7210d32e-2244-4298-a789-856fca403590",
  "creator_id": "attacker_EV06",
  "guess": "human",
  "confidence": 0.33635,
  "model_score": 0.5727,
  "style_score": 0.1,
  "label": "This text shows patterns associated with human writing. This assessment does not verify who wrote it.",
  "error": null,
  "verdict": ""
}
```

### EV07 — `evasion`

*Targeting:* signal two: padding with punctuation

```json
{
  "id": "EV07",
  "status": 200,
  "content_id": "3107ec37-57be-4eba-93ff-3d9b92876432",
  "creator_id": "attacker_EV07",
  "guess": "unsure",
  "confidence": 0.48845000000000005,
  "model_score": 0.5862,
  "style_score": 0.3907,
  "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
  "error": null,
  "verdict": ""
}
```

### EV08 — `evasion`

*Targeting:* signal one: text below the token window

```json
{
  "id": "EV08",
  "status": 200,
  "content_id": "9903ff4b-5636-4ca4-853b-d75036905903",
  "creator_id": "attacker_EV08",
  "guess": "unsure",
  "confidence": 0.3626,
  "model_score": 0.2452,
  "style_score": 0.48,
  "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
  "error": null,
  "verdict": ""
}
```

### EV09 — `evasion`

*Targeting:* both: AI text with a human opening paragraph bolted on

```json
{
  "id": "EV09",
  "status": 200,
  "content_id": "b643accf-0ada-4cfa-ba64-e14e659abe95",
  "creator_id": "attacker_EV09",
  "guess": "unsure",
  "confidence": 0.5505,
  "model_score": 0.7042,
  "style_score": 0.3968,
  "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
  "error": null,
  "verdict": ""
}
```

### EV10 — `evasion`

*Targeting:* signal two: repeated stanza structure

```json
{
  "id": "EV10",
  "status": 200,
  "content_id": "e9d2ccdc-da8f-4cbe-b8a3-e293b9e528c9",
  "creator_id": "attacker_EV10",
  "guess": "ai",
  "confidence": 0.82315,
  "model_score": 0.9792,
  "style_score": 0.6671,
  "label": "This text shows patterns associated with AI-generated writing. This is not proof of AI use. If you wrote it yourself, you can request a review using the content ID.",
  "error": null,
  "verdict": ""
}
```

### FP01 — `false_positive`

*Targeting:* plain, clear human writing with no flourishes

```json
{
  "id": "FP01",
  "status": 200,
  "content_id": "01af9434-42dc-494b-836d-1f01220e067e",
  "creator_id": "attacker_FP01",
  "guess": "unsure",
  "confidence": 0.5386,
  "model_score": 0.6175,
  "style_score": 0.4597,
  "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
  "error": null,
  "verdict": ""
}
```

### FP02 — `false_positive`

*Targeting:* human writing in a formal register

```json
{
  "id": "FP02",
  "status": 200,
  "content_id": "9e6b1a03-ed4b-4e4b-a6b8-0fdea1563bf1",
  "creator_id": "attacker_FP02",
  "guess": "ai",
  "confidence": 0.6605000000000001,
  "model_score": 0.7387,
  "style_score": 0.5823,
  "label": "This text shows patterns associated with AI-generated writing. This is not proof of AI use. If you wrote it yourself, you can request a review using the content ID.",
  "error": null,
  "verdict": ""
}
```

### FP03 — `false_positive`

*Targeting:* a non-native English speaker writing carefully

```json
{
  "id": "FP03",
  "status": 200,
  "content_id": "97ac69a2-b4f3-4ee3-ac7b-e7dfa1787836",
  "creator_id": "attacker_FP03",
  "guess": "ai",
  "confidence": 0.6668000000000001,
  "model_score": 0.8051,
  "style_score": 0.5285,
  "label": "This text shows patterns associated with AI-generated writing. This is not proof of AI use. If you wrote it yourself, you can request a review using the content ID.",
  "error": null,
  "verdict": ""
}
```

### FP04 — `false_positive`

*Targeting:* a student essay written to a rubric

```json
{
  "id": "FP04",
  "status": 200,
  "content_id": "1ea42c16-0569-4a17-8c18-8ef1748eeab1",
  "creator_id": "attacker_FP04",
  "guess": "ai",
  "confidence": 0.6517999999999999,
  "model_score": 0.8329,
  "style_score": 0.4707,
  "label": "This text shows patterns associated with AI-generated writing. This is not proof of AI use. If you wrote it yourself, you can request a review using the content ID.",
  "error": null,
  "verdict": ""
}
```

### FP05 — `false_positive`

*Targeting:* technical documentation written by a person

```json
{
  "id": "FP05",
  "status": 200,
  "content_id": "083912a8-008c-4790-a513-d47ea7ec6da0",
  "creator_id": "attacker_FP05",
  "guess": "ai",
  "confidence": 0.7061999999999999,
  "model_score": 0.8005,
  "style_score": 0.6119,
  "label": "This text shows patterns associated with AI-generated writing. This is not proof of AI use. If you wrote it yourself, you can request a review using the content ID.",
  "error": null,
  "verdict": ""
}
```

### FP06 — `false_positive`

*Targeting:* a person imitating a formal template

```json
{
  "id": "FP06",
  "status": 200,
  "content_id": "64ec0626-f05b-4b85-811d-c8bfaa424cde",
  "creator_id": "attacker_FP06",
  "guess": "ai",
  "confidence": 0.65165,
  "model_score": 0.8814,
  "style_score": 0.4219,
  "label": "This text shows patterns associated with AI-generated writing. This is not proof of AI use. If you wrote it yourself, you can request a review using the content ID.",
  "error": null,
  "verdict": ""
}
```

### FP07 — `false_positive`

*Targeting:* human writing that repeats a phrase deliberately

```json
{
  "id": "FP07",
  "status": 200,
  "content_id": "fc9909e7-f87b-4b24-8f2b-2f9b6e428dce",
  "creator_id": "attacker_FP07",
  "guess": "unsure",
  "confidence": 0.64625,
  "model_score": 0.8816,
  "style_score": 0.4109,
  "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
  "error": null,
  "verdict": ""
}
```

### FP08 — `false_positive`

*Targeting:* very short genuine human submission

```json
{
  "id": "FP08",
  "status": 200,
  "content_id": "f50f9d7a-3f1c-45b4-a592-4042b0da5d13",
  "creator_id": "attacker_FP08",
  "guess": "unsure",
  "confidence": 0.35509999999999997,
  "model_score": 0.3223,
  "style_score": 0.3879,
  "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
  "error": null,
  "verdict": ""
}
```

### PI01 — `prompt_injection`

*Targeting:* instruction to ignore the check

```json
{
  "id": "PI01",
  "status": 200,
  "content_id": "f44c2c2e-68e8-4df5-bd05-ecd0427352bd",
  "creator_id": "attacker_PI01",
  "guess": "unsure",
  "confidence": 0.3631,
  "model_score": 0.4625,
  "style_score": 0.2637,
  "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
  "error": null,
  "verdict": ""
}
```

### PI02 — `prompt_injection`

*Targeting:* instruction disguised as a system message

```json
{
  "id": "PI02",
  "status": 200,
  "content_id": "7036b9c4-7f34-4d80-a1f6-1a07370e29fb",
  "creator_id": "attacker_PI02",
  "guess": "human",
  "confidence": 0.23259999999999997,
  "model_score": 0.2044,
  "style_score": 0.2608,
  "label": "This text shows patterns associated with human writing. This assessment does not verify who wrote it.",
  "error": null,
  "verdict": ""
}
```

### PI03 — `prompt_injection`

*Targeting:* instruction wrapped in the writer's voice

```json
{
  "id": "PI03",
  "status": 200,
  "content_id": "5939b1bc-a3e9-4ca3-a37a-ced9c12c9079",
  "creator_id": "attacker_PI03",
  "guess": "unsure",
  "confidence": 0.5262,
  "model_score": 0.5943,
  "style_score": 0.4581,
  "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
  "error": null,
  "verdict": ""
}
```

### PI04 — `prompt_injection`

*Targeting:* attempt to make the label text hostile

```json
{
  "id": "PI04",
  "status": 200,
  "content_id": "abb91121-45c7-4ad1-b53f-0d3fc069d13d",
  "creator_id": "attacker_PI04",
  "guess": "unsure",
  "confidence": 0.4743,
  "model_score": 0.4998,
  "style_score": 0.4488,
  "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
  "error": null,
  "verdict": ""
}
```

### PI05 — `prompt_injection`

*Targeting:* attempt to inject into the audit log

```json
{
  "id": "PI05",
  "status": 200,
  "content_id": "eda8ecb8-8b6a-4ad2-9ca3-a2d084b05e94",
  "creator_id": "attacker_PI05",
  "guess": "unsure",
  "confidence": 0.5267,
  "model_score": 0.6401,
  "style_score": 0.4133,
  "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
  "error": null,
  "verdict": ""
}
```

### PI06 — `prompt_injection`

*Targeting:* instruction plus real human text

```json
{
  "id": "PI06",
  "status": 200,
  "content_id": "d8e69f00-e68c-47ce-8831-9442d3ce7aa0",
  "creator_id": "attacker_PI06",
  "guess": "unsure",
  "confidence": 0.51155,
  "model_score": 0.5583,
  "style_score": 0.4648,
  "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
  "error": null,
  "verdict": ""
}
```

### MF01 — `malformed`

*Targeting:* text is only whitespace

```json
{
  "id": "MF01",
  "status": 400,
  "content_id": null,
  "creator_id": "attacker_MF01",
  "guess": null,
  "confidence": null,
  "model_score": null,
  "style_score": null,
  "label": null,
  "error": null,
  "verdict": ""
}
```

### MF02 — `malformed`

*Targeting:* text is a single character

```json
{
  "id": "MF02",
  "status": 400,
  "content_id": null,
  "creator_id": "attacker_MF02",
  "guess": null,
  "confidence": null,
  "model_score": null,
  "style_score": null,
  "label": null,
  "error": null,
  "verdict": ""
}
```

### MF03 — `malformed`

*Targeting:* text is control characters

```json
{
  "id": "MF03",
  "status": 200,
  "content_id": "298bb64e-89a6-4e9a-8a21-11975c800e20",
  "creator_id": "attacker_MF03",
  "guess": "human",
  "confidence": 0.15,
  "model_score": 0.0,
  "style_score": 0.3,
  "label": "This text shows patterns associated with human writing. This assessment does not verify who wrote it.",
  "error": null,
  "verdict": ""
}
```

### MF04 — `malformed`

*Targeting:* text is only punctuation

```json
{
  "id": "MF04",
  "status": 400,
  "content_id": null,
  "creator_id": "attacker_MF04",
  "guess": null,
  "confidence": null,
  "model_score": null,
  "style_score": null,
  "label": null,
  "error": null,
  "verdict": ""
}
```

### MF05 — `malformed`

*Targeting:* text is a very long single word

```json
{
  "id": "MF05",
  "status": 200,
  "content_id": "a0962514-2875-4a51-b8c9-2bfb2d6c77a2",
  "creator_id": "attacker_MF05",
  "guess": "unsure",
  "confidence": 0.6488,
  "model_score": 0.9976,
  "style_score": 0.3,
  "label": "We cannot confidently distinguish human-written from AI-generated writing in this text. This is not an accusation of AI use. You can request a review using the content ID.",
  "error": null,
  "verdict": ""
}
```

### MF06 — `malformed`

*Targeting:* text is emoji only

```json
{
  "id": "MF06",
  "status": 400,
  "content_id": null,
  "creator_id": "attacker_MF06",
  "guess": null,
  "confidence": null,
  "model_score": null,
  "style_score": null,
  "label": null,
  "error": null,
  "verdict": ""
}
```

### MF07 — `malformed`

*Targeting:* text is right-to-left script

```json
{
  "id": "MF07",
  "status": 400,
  "content_id": null,
  "creator_id": "attacker_MF07",
  "guess": null,
  "confidence": null,
  "model_score": null,
  "style_score": null,
  "label": null,
  "error": null,
  "verdict": ""
}
```

### MF08 — `malformed`

*Targeting:* text is 60,000 characters

```json
{
  "id": "MF08",
  "status": 413,
  "content_id": null,
  "creator_id": "attacker_MF08",
  "guess": null,
  "confidence": null,
  "model_score": null,
  "style_score": null,
  "label": null,
  "error": null,
  "verdict": ""
}
```

### RQ01 — `malformed`

*Targeting:* no text field at all

```json
{
  "id": "RQ01",
  "status": 400,
  "content_id": null,
  "creator_id": "attacker_RQ01",
  "guess": null,
  "confidence": null,
  "model_score": null,
  "style_score": null,
  "label": null,
  "error": null,
  "verdict": ""
}
```

### RQ02 — `malformed`

*Targeting:* no creator_id

```json
{
  "id": "RQ02",
  "status": 400,
  "content_id": null,
  "creator_id": null,
  "guess": null,
  "confidence": null,
  "model_score": null,
  "style_score": null,
  "label": null,
  "error": null,
  "verdict": ""
}
```

### RQ03 — `malformed`

*Targeting:* text is a number

```json
{
  "id": "RQ03",
  "status": 400,
  "content_id": null,
  "creator_id": "attacker_RQ03",
  "guess": null,
  "confidence": null,
  "model_score": null,
  "style_score": null,
  "label": null,
  "error": null,
  "verdict": ""
}
```

### RQ04 — `malformed`

*Targeting:* text is a list

```json
{
  "id": "RQ04",
  "status": 400,
  "content_id": null,
  "creator_id": "attacker_RQ04",
  "guess": null,
  "confidence": null,
  "model_score": null,
  "style_score": null,
  "label": null,
  "error": null,
  "verdict": ""
}
```

### RQ05 — `malformed`

*Targeting:* text is null

```json
{
  "id": "RQ05",
  "status": 400,
  "content_id": null,
  "creator_id": "attacker_RQ05",
  "guess": null,
  "confidence": null,
  "model_score": null,
  "style_score": null,
  "label": null,
  "error": null,
  "verdict": ""
}
```

### RQ06 — `malformed`

*Targeting:* creator_id is an object

```json
{
  "id": "RQ06",
  "status": 400,
  "content_id": null,
  "creator_id": {
    "id": "x"
  },
  "guess": null,
  "confidence": null,
  "model_score": null,
  "style_score": null,
  "label": null,
  "error": null,
  "verdict": ""
}
```

### RQ07 — `malformed`

*Targeting:* body is a JSON array, not an object

```json
{
  "id": "RQ07",
  "status": 400,
  "content_id": null,
  "creator_id": null,
  "guess": null,
  "confidence": null,
  "model_score": null,
  "style_score": null,
  "label": null,
  "error": null,
  "verdict": ""
}
```

### RQ08 — `malformed`

*Targeting:* body is unparseable JSON

```json
{
  "id": "RQ08",
  "status": 400,
  "content_id": null,
  "creator_id": null,
  "guess": null,
  "confidence": null,
  "model_score": null,
  "style_score": null,
  "label": null,
  "error": null,
  "verdict": ""
}
```

### RQ09 — `malformed`

*Targeting:* body is empty

```json
{
  "id": "RQ09",
  "status": 400,
  "content_id": null,
  "creator_id": null,
  "guess": null,
  "confidence": null,
  "model_score": null,
  "style_score": null,
  "label": null,
  "error": null,
  "verdict": ""
}
```

### RQ10 — `malformed`

*Targeting:* body is form-encoded, not JSON

```json
{
  "id": "RQ10",
  "status": 400,
  "content_id": null,
  "creator_id": null,
  "guess": null,
  "confidence": null,
  "model_score": null,
  "style_score": null,
  "label": null,
  "error": null,
  "verdict": ""
}
```

### RQ11 — `malformed`

*Targeting:* body is JSON claiming to be plain text

```json
{
  "id": "RQ11",
  "status": 400,
  "content_id": null,
  "creator_id": null,
  "guess": null,
  "confidence": null,
  "model_score": null,
  "style_score": null,
  "label": null,
  "error": null,
  "verdict": ""
}
```

### RQ12 — `malformed`

*Targeting:* deeply nested JSON

```json
{
  "id": "RQ12",
  "status": 400,
  "content_id": null,
  "creator_id": "attacker_RQ12",
  "guess": null,
  "confidence": null,
  "model_score": null,
  "style_score": null,
  "label": null,
  "error": null,
  "verdict": ""
}
```

### FL01_01 — `flood_same_creator`

*Targeting:* 20 rapid submissions from one creator

```json
{
  "id": "FL01_01",
  "status": 200,
  "content_id": "5cf36efd-46f6-40ea-8c4f-824aed15dae3",
  "creator_id": "attacker_flood",
  "guess": "human",
  "confidence": 0.16435,
  "model_score": 0.0287,
  "style_score": 0.3,
  "label": "This text shows patterns associated with human writing. This assessment does not verify who wrote it.",
  "error": null,
  "verdict": ""
}
```

### FL01_02 — `flood_same_creator`

*Targeting:* 20 rapid submissions from one creator

```json
{
  "id": "FL01_02",
  "status": 200,
  "content_id": "45b1a41f-b1d0-44db-a8f1-67f9ecf06cef",
  "creator_id": "attacker_flood",
  "guess": "human",
  "confidence": 0.16435,
  "model_score": 0.0287,
  "style_score": 0.3,
  "label": "This text shows patterns associated with human writing. This assessment does not verify who wrote it.",
  "error": null,
  "verdict": ""
}
```

### FL01_03 — `flood_same_creator`

*Targeting:* 20 rapid submissions from one creator

```json
{
  "id": "FL01_03",
  "status": 200,
  "content_id": "5c947989-d074-4ad5-a895-dc3c103b5e3c",
  "creator_id": "attacker_flood",
  "guess": "human",
  "confidence": 0.16435,
  "model_score": 0.0287,
  "style_score": 0.3,
  "label": "This text shows patterns associated with human writing. This assessment does not verify who wrote it.",
  "error": null,
  "verdict": ""
}
```

### FL01_04 — `flood_same_creator`

*Targeting:* 20 rapid submissions from one creator

```json
{
  "id": "FL01_04",
  "status": 200,
  "content_id": "8e798ac4-6ad3-4176-ab95-4308feb608c8",
  "creator_id": "attacker_flood",
  "guess": "human",
  "confidence": 0.16435,
  "model_score": 0.0287,
  "style_score": 0.3,
  "label": "This text shows patterns associated with human writing. This assessment does not verify who wrote it.",
  "error": null,
  "verdict": ""
}
```

### FL01_05 — `flood_same_creator`

*Targeting:* 20 rapid submissions from one creator

```json
{
  "id": "FL01_05",
  "status": 200,
  "content_id": "3bede21b-f3fb-4980-88c0-c967275c11bd",
  "creator_id": "attacker_flood",
  "guess": "human",
  "confidence": 0.16435,
  "model_score": 0.0287,
  "style_score": 0.3,
  "label": "This text shows patterns associated with human writing. This assessment does not verify who wrote it.",
  "error": null,
  "verdict": ""
}
```

### FL01_06 — `flood_same_creator`

*Targeting:* 20 rapid submissions from one creator

```json
{
  "id": "FL01_06",
  "status": 200,
  "content_id": "2e959734-4c73-4fc1-8d5f-0b91e113cb1c",
  "creator_id": "attacker_flood",
  "guess": "human",
  "confidence": 0.16435,
  "model_score": 0.0287,
  "style_score": 0.3,
  "label": "This text shows patterns associated with human writing. This assessment does not verify who wrote it.",
  "error": null,
  "verdict": ""
}
```

### FL01_07 — `flood_same_creator`

*Targeting:* 20 rapid submissions from one creator

```json
{
  "id": "FL01_07",
  "status": 200,
  "content_id": "290e4a73-b5f7-419e-bf8e-748cc0324c55",
  "creator_id": "attacker_flood",
  "guess": "human",
  "confidence": 0.16435,
  "model_score": 0.0287,
  "style_score": 0.3,
  "label": "This text shows patterns associated with human writing. This assessment does not verify who wrote it.",
  "error": null,
  "verdict": ""
}
```

### FL01_08 — `flood_same_creator`

*Targeting:* 20 rapid submissions from one creator

```json
{
  "id": "FL01_08",
  "status": 200,
  "content_id": "0e8eb887-3248-4134-8551-89784568d9d0",
  "creator_id": "attacker_flood",
  "guess": "human",
  "confidence": 0.16435,
  "model_score": 0.0287,
  "style_score": 0.3,
  "label": "This text shows patterns associated with human writing. This assessment does not verify who wrote it.",
  "error": null,
  "verdict": ""
}
```

### FL01_09 — `flood_same_creator`

*Targeting:* 20 rapid submissions from one creator

```json
{
  "id": "FL01_09",
  "status": 200,
  "content_id": "ecfb4378-fb35-47f4-a91c-812799a98378",
  "creator_id": "attacker_flood",
  "guess": "human",
  "confidence": 0.16435,
  "model_score": 0.0287,
  "style_score": 0.3,
  "label": "This text shows patterns associated with human writing. This assessment does not verify who wrote it.",
  "error": null,
  "verdict": ""
}
```

### FL01_10 — `flood_same_creator`

*Targeting:* 20 rapid submissions from one creator

```json
{
  "id": "FL01_10",
  "status": 200,
  "content_id": "78f437ad-99ca-43d5-9017-2695d703f51c",
  "creator_id": "attacker_flood",
  "guess": "human",
  "confidence": 0.16435,
  "model_score": 0.0287,
  "style_score": 0.3,
  "label": "This text shows patterns associated with human writing. This assessment does not verify who wrote it.",
  "error": null,
  "verdict": ""
}
```

### FL01_11 — `flood_same_creator`

*Targeting:* 20 rapid submissions from one creator

```json
{
  "id": "FL01_11",
  "status": 429,
  "content_id": null,
  "creator_id": "attacker_flood",
  "guess": null,
  "confidence": null,
  "model_score": null,
  "style_score": null,
  "label": null,
  "error": null,
  "verdict": ""
}
```

### FL01_12 — `flood_same_creator`

*Targeting:* 20 rapid submissions from one creator

```json
{
  "id": "FL01_12",
  "status": 429,
  "content_id": null,
  "creator_id": "attacker_flood",
  "guess": null,
  "confidence": null,
  "model_score": null,
  "style_score": null,
  "label": null,
  "error": null,
  "verdict": ""
}
```
