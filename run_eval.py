"""Three real HTTP trials per original criterion, with full response evidence."""
import argparse
import datetime as dt
import json
import math
import uuid
from pathlib import Path
from statistics import mean
import requests
import scenarios

ROOT = Path(__file__).resolve().parent

def call(method, url, body=None):
    try:
        response = requests.request(method, url, json=body, timeout=120)
        try:
            payload = response.json()
        except ValueError:
            payload = {"non_json_response": response.text}
        return {"http_status": response.status_code, "response": payload}
    except requests.RequestException as exc:
        return {"http_status": None, "response": {}, "transport_error": str(exc)}

def scored(record):
    payload = record["response"]
    value = payload.get("confidence") if isinstance(payload, dict) else None
    return (record["http_status"] == 200 and isinstance(value, (int, float))
            and not isinstance(value, bool) and math.isfinite(value)
            and 0 <= value <= 1 and payload.get("guess") in ("human", "unsure", "ai"))

def run_trial(scenario, url, run_id, trial):
    number = scenario["criterion"]
    records = []
    bodies = scenario.get("bodies") or [{"text": text} for text in scenario["texts"]]
    for i, original in enumerate(bodies, 1):
        body = dict(original)
        body["creator_id"] = f"eval_{run_id}_c{number}_t{trial}_i{i}"
        record = call("POST", url + "/submit", body)
        record["request"] = body
        records.append(record)
    valid = all(scored(r) for r in records)
    if number == 1:
        accusations = sum(r["response"].get("guess") == "ai" for r in records)
        passed = valid and len(records) == 10 and accusations <= 3
        metric = f"{accusations}/10 AI; {sum(scored(r) for r in records)}/10 scored"
    elif number == 2:
        if valid and len(records) == 20:
            human_mean = mean(r["response"]["confidence"] for r in records[:10])
            ai_mean = mean(r["response"]["confidence"] for r in records[10:])
            gap = ai_mean - human_mean
            passed = gap >= 0.50
            metric = f"gap {gap:.5f} (human {human_mean:.5f}, AI {ai_mean:.5f})"
        else:
            passed, metric = False, "Incomplete scoring; no valid group comparison"
    elif number == 3:
        guesses = [r["response"].get("guess") for r in records]
        labels_ok = all(isinstance(r["response"].get("label"), str)
                        and r["response"]["label"].strip()
                        and "placeholder" not in r["response"]["label"].lower()
                        for r in records)
        passed = valid and sorted(guesses, key=str) == ["ai", "human", "unsure"] and labels_ok
        metric = ", ".join(str(g) for g in guesses) + f"; labels valid: {bool(labels_ok)}"
    elif number == 4:
        content_id = records[0]["response"].get("content_id")
        reasoning = "I wrote this passage myself and request review of its automated assessment."
        appeal = call("POST", url + "/appeal", {"content_id": content_id, "reasoning": reasoning})
        log = call("GET", url + "/log")
        entries = log["response"].get("entries", [])
        history = [e for e in entries if e.get("content_id") == content_id] if content_id else []
        original_index = next((i for i,e in enumerate(history) if e.get("status") == "decided"), None)
        later_appeal = original_index is not None and any(
            e.get("event") == "appeal" and e.get("status") == "under_review"
            and e.get("reasoning") == reasoning for e in history[original_index + 1:])
        payload = appeal["response"]
        passed = (valid and bool(content_id) and appeal["http_status"] == 200
                  and payload.get("content_id") == content_id
                  and payload.get("status") == "under_review"
                  and log["http_status"] == 200 and later_appeal)
        metric = f"appeal {appeal['http_status']}; original + later appeal: {bool(later_appeal)}"
        records.append({"appeal_request": {"content_id": content_id, "reasoning": reasoning},
                        "appeal_result": appeal, "log_http_status": log["http_status"], "matching_log_entries": history})
    else:
        checks = [r["http_status"] == expected
                  and isinstance(r["response"].get("error"), str)
                  and bool(r["response"]["error"].strip())
                  and "guess" not in r["response"]
                  for r, expected in zip(records, (400,400,413))]
        passed = len(checks) == 3 and all(checks)
        metric = f"{sum(checks)}/3 correct; codes " + ", ".join(str(r["http_status"]) for r in records)
    return {"trial": trial, "metric": metric, "passed": bool(passed), "evidence": records}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", required=True, choices=["before", "after"])
    parser.add_argument("--url", default="http://127.0.0.1:5000")
    args = parser.parse_args()
    problems = scenarios.validate()
    if problems:
        raise SystemExit("\n".join(problems))
    health = call("GET", args.url + "/health")
    if health["http_status"] != 200:
        raise SystemExit("Start python app.py first.")
    run_id = uuid.uuid4().hex[:10]
    targets = {1: "At most 3/10 AI; all ten scored", 2: "AI mean minus human mean >= 0.50; all 20 scored",
               3: "human, unsure, ai exactly once; valid labels", 4: "200, same ID, under_review; original + later appeal in log",
               5: "400, 400, 413; error messages; no guess"}
    rows = []
    for scenario in scenarios.SCENARIOS:
        trials = []
        for trial in range(1,4):
            result = run_trial(scenario,args.url,run_id,trial)
            trials.append(result)
            print(f"Criterion {scenario['criterion']} trial {trial}: {result['metric']} | {'MET' if result['passed'] else 'MISSED'}",flush=True)
        rows.append({"criterion":scenario["criterion"],"name":scenario["name"],
                     "target":targets[scenario["criterion"]],"trials":trials,
                     "verdict":"MET" if all(t["passed"] for t in trials) else "MISSED"})
    directory = ROOT / "results"
    directory.mkdir(exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y-%m-%d_%H%M%S")
    base = directory / f"eval_{stamp}_{args.label}"
    data = {"label":args.label,"run_id":run_id,"health":health,"criteria":rows,
            "method":"Three HTTP trials per criterion. Unique synthetic creator IDs isolate content tests from flood tests. Same inputs and harness must be used before and after."}
    base.with_suffix(".json").write_text(json.dumps(data,indent=2,ensure_ascii=False),encoding="utf-8")
    lines = [f"# Run Log and Verdicts - {args.label}","", "Produced by `run_eval.py::run_trial` using `scenarios.py::SCENARIOS`.","",
             data["method"],"", "| Criterion | Target | Run 1 | Run 2 | Run 3 | Verdict |", "|---|---|---|---|---|---|"]
    for row in rows:
        cells = [t["metric"].replace("|","/") for t in row["trials"]]
        lines.append(f"| {row['criterion']}. {row['name']} | {row['target']} | " + " | ".join(cells) + f" | {row['verdict']} |")
    for row in rows:
        lines.extend(["",f"## {row['criterion']}. {row['name']} - actual output"])
        for trial in row["trials"]:
            lines.extend(["",f"### Trial {trial['trial']}","", "```json", json.dumps(trial,indent=2,ensure_ascii=False),"```"])
    base.with_suffix(".md").write_text("\n".join(lines),encoding="utf-8")
    print(f"Saved {base.name}.json and {base.name}.md in results/",flush=True)

if __name__ == "__main__":
    main()
