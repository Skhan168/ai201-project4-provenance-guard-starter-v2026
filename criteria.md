# Capstone acceptance criteria — Provenance Guard
These criteria cover the request-level operational logging extension. They are recorded before capstone implementation measurements and acceptance results. The original project criteria are preserved in criteria_unit7_unit8.md.


Test conventions: A valid submission contains a JSON object with a nonempty creator_id and an English passage of three complete sentences totaling 50–100 whitespace-separated words. Use fixed synthetic passages, unchanged between before and after tests. Send each request identifier in the X-Request-ID header and match it against the request_id field in the operational log. Use a fresh creator_id for each request except the shared-creator sequence required by criterion 5.

Trial procedure: Perform three independent trials of every criterion before the improvement and three afterward. In each trial, perform the warm-up from criterion 4 before sending the three submissions shared by criteria 1, 2, and 4. A criterion is MET only if its target holds in all three trials.

## 1. Valid-submission logging coverage
In each trial, send three valid English writing submissions to POST /submit, using a distinct request identifier for each submission. After all responses return, inspect the operational log. Each submitted request identifier must appear in exactly one record: three matching records total, with none missing and none duplicated.

Reason: I want every actual submission to remain traceable without wasting space on accidental duplicate records. Repeated submissions are separate requests and must not be merged.


## 2. Operational record contents
Inspect the three valid-submission records from criterion 1. All three must contain a nonempty timestamp, request method, request path, submitted JSON input, returned JSON output, integer HTTP status, and numeric duration in seconds greater than or equal to zero. The method, path, input, output, and status must match the requests sent and responses received. The timestamp must be parseable as an ISO 8601 date and time with a timezone.

Reason: I need enough information to reconstruct what request occurred, when it occurred, what the service returned, and how long it took. These records describe requests, not authenticated people.


## 3. Empty-input rejection visibility
In each trial, send three requests to POST /submit with text set to an empty string and a valid, nonempty creator_id. Use distinct request identifiers. All three must return HTTP 400 with a nonempty error message and no guess field. Each request must have exactly one operational record showing the submitted empty text, returned error response, HTTP 400 status, and a numeric duration in seconds greater than or equal to zero.


Reason: Rejected requests must remain traceable rather than disappear because no authorship decision was produced.


## 4. Warm-request response time
First, send one valid warm-up submission and wait for a successful response so the model is loaded. Do not include that request in the timing results. Then send the three valid submissions from criterion 1 one at a time, waiting for each response before sending the next. Measure each request from immediately before the client sends it until the full response is received. All three must return HTTP 200 within 90 seconds each. Faster responses pass; there is no minimum wait.

Reason: Ninety seconds is the longest I would personally accept waiting for a writing assessment. I am willing to allow processing time for the local model and style analysis, but a longer wait would make the service impractical for me to use.


## 5. Rate-limit regression
In each trial, use a fresh creator_id and send 11 sequential valid submissions to POST /submit, all using that same creator_id. All 11 requests must complete within a 60-second interval measured by the client. The first ten must return HTTP 200 and the eleventh must return HTTP 429 with an error response. If the sequence takes 60 seconds or longer, this criterion is MISSED rather than treated as proof that the per-minute limit worked.

Reason: I want to preserve the existing protection against rapid repeated submissions while adding operational logging. Ten allowed submissions and rejection of the next one checks the configured limit without changing it.