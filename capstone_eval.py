"""Real HTTP evaluation of the committed capstone criteria."""

import argparse
import json
import math
import statistics
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent
LOG = ROOT / "logs" / "operational.jsonl"
BASE = "http://127.0.0.1:5000"

PASSAGES = [
    (
        "Our neighborhood library opened a small reading room beside the main entrance last spring. "
        "Volunteers arranged comfortable chairs near the windows and placed a collection of donated books on wooden shelves for visitors of different ages. "
        "I visit on Saturday mornings because the quiet space helps me concentrate on reading before the afternoon becomes busy."
    ),
    (
        "The community garden has become a useful meeting place for people who live on our street. "
        "Each weekend several neighbors bring tools and spend an hour watering vegetables or removing weeds from the narrow paths between the planting beds. "
        "Working together gives everyone a chance to share practical advice while producing fresh food for their families."
    ),
    (
        "Preparing a weekly schedule helps me balance coursework with responsibilities at home and time with friends. "
        "I begin by listing important deadlines and then divide larger assignments into smaller tasks that fit into the available hours on different days. "
        "The plan sometimes changes, but having a clear starting point makes it easier to decide what needs attention."
    ),
]


def read_records():
    records = []
    if LOG.exists():
        for line in LOG.read_text(encoding="utf-8").splitlines():
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return records


def send(text, creator):
    request_id = str(uuid.uuid4())
    payload = {"text": text, "creator_id": creator}
    started = time.perf_counter()
    result = {
        "request_id": request_id,
        "method": "POST",
        "path": "/submit",
        "input": payload,
    }
    try:
        response = requests.post(
            BASE + "/submit",
            json=payload,
            headers={"X-Request-ID": request_id},
            timeout=(5, 180),
        )
        result["http_status"] = response.status_code
        try:
            result["output"] = response.json()
        except ValueError:
            result["output"] = response.text
    except requests.RequestException as exc:
        result["http_status"] = None
        result["output"] = {"client_error": str(exc)}
    result["client_seconds"] = time.perf_counter() - started
    return result


def matched(item, records):
    return [
        row for row in records
        if row.get("request_id") == item["request_id"]
    ]


def valid_duration(value):
    return (
        type(value) in (int, float)
        and math.isfinite(value)
        and value >= 0
    )


def correct_record(item, record):
    try:
        stamp = datetime.fromisoformat(record["timestamp"])
        timestamp_ok = stamp.utcoffset() is not None
    except (KeyError, TypeError, ValueError):
        timestamp_ok = False
    return (
        timestamp_ok
        and record.get("method") == item["method"]
        and record.get("path") == item["path"]
        and record.get("input") == item["input"]
        and record.get("output") == item["output"]
        and type(record.get("http_status")) is int
        and record["http_status"] == item["http_status"]
        and valid_duration(record.get("duration_seconds"))
    )


def run_trial(number, prefix):
    warmup = send(PASSAGES[0], f"{prefix}_warm_{number}")
    valid = [
        send(text, f"{prefix}_valid_{number}_{i}")
        for i, text in enumerate(PASSAGES)
    ]
    invalid = [
        send("", f"{prefix}_empty_{number}_{i}")
        for i in range(3)
    ]
    creator = f"{prefix}_limit_{number}"
    started = time.perf_counter()
    flood = [send(PASSAGES[i % 3], creator) for i in range(11)]
    flood_seconds = time.perf_counter() - started

    time.sleep(0.1)
    records = read_records()
    coverage = sum(len(matched(item, records)) == 1 for item in valid)
    contents = sum(
        len(rows := matched(item, records)) == 1
        and correct_record(item, rows[0])
        for item in valid
    )
    rejected = 0
    for item in invalid:
        rows = matched(item, records)
        output = item["output"]
        rejected += (
            item["http_status"] == 400
            and isinstance(output, dict)
            and isinstance(output.get("error"), str)
            and bool(output["error"].strip())
            and "guess" not in output
            and len(rows) == 1
            and correct_record(item, rows[0])
        )
    latency = sum(
        item["http_status"] == 200 and item["client_seconds"] <= 90
        for item in valid
    )
    warm_ok = warmup["http_status"] == 200
    codes = [item["http_status"] for item in flood]
    rate_ok = (
        codes == [200] * 10 + [429]
        and flood_seconds < 60
        and isinstance(flood[-1]["output"], dict)
        and bool(flood[-1]["output"].get("error"))
    )
    passed = [
        coverage == 3,
        contents == 3,
        rejected == 3,
        warm_ok and latency == 3,
        rate_ok,
    ]
    metrics = [
        f"{coverage}/3 exactly once",
        f"{contents}/3 complete and matching",
        f"{rejected}/3 rejected and logged",
        f"{latency}/3 within 90s; warmup={warm_ok}; "
        f"max={max(x['client_seconds'] for x in valid):.4f}s",
        f"codes={codes}; elapsed={flood_seconds:.4f}s",
    ]
    return {
        "trial": number,
        "passed": passed,
        "metrics": metrics,
        "warmup": warmup,
        "valid": valid,
        "invalid": invalid,
        "rate_limit": flood,
        "rate_limit_seconds": flood_seconds,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", required=True, choices=["before", "after"])
    args = parser.parse_args()
    for text in PASSAGES:
        assert 50 <= len(text.split()) <= 100

    requests.get(BASE + "/health", timeout=10).raise_for_status()
    prefix = "cap_" + uuid.uuid4().hex[:12]
    trials = []
    for number in range(1, 4):
        print(f"Running trial {number}/3...", flush=True)
        trial = run_trial(number, prefix)
        trials.append(trial)
        for index, metric in enumerate(trial["metrics"], 1):
            print(f"  Criterion {index}: {metric}", flush=True)

    print("Measuring ten additional warm requests...", flush=True)
    cost_runs = [
        send(PASSAGES[i % 3], f"{prefix}_cost_{i}")
        for i in range(10)
    ]
    time.sleep(0.1)
    all_records = read_records()
    own_records = [
        row for row in all_records
        if isinstance(row.get("input"), dict)
        and str(row["input"].get("creator_id", "")).startswith(prefix)
    ]
    successful_cost = [
        item for item in cost_runs if item["http_status"] == 200
    ]
    cost_complete = len(successful_cost) == 10
    mean_seconds = (
        statistics.mean(x["client_seconds"] for x in successful_cost)
        if cost_complete else None
    )
    report = {
        "label": args.label,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "producer": "capstone_eval.py::main, run_trial, send",
        "prefix": prefix,
        "passages": PASSAGES,
        "trials": trials,
        "cost_runs": cost_runs,
        "cost_measure": "Warm client elapsed seconds, not CPU time or dollars",
        "cost_complete": cost_complete,
        "mean_seconds": mean_seconds,
        "seconds_for_100_single_request_users": (
            100 * mean_seconds if mean_seconds is not None else None
        ),
        "operational_records": own_records,
    }
    folder = ROOT / "results"
    folder.mkdir(exist_ok=True)
    stem = f"capstone_{args.label}_{prefix}"
    (folder / f"{stem}.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    names = [
        "1. Logging coverage",
        "2. Record contents",
        "3. Empty-input visibility",
        "4. Warm latency",
        "5. Rate-limit regression",
    ]
    targets = [
        "3/3 exactly once",
        "3/3 complete and matching",
        "3/3 HTTP 400 and logged",
        "3/3 HTTP 200 within 90s after warmup",
        "10 HTTP 200 then 429; sequence under 60s",
    ]
    lines = [
        f"Capstone {args.label} results",
        "",
        "Producer: capstone_eval.py::main, run_trial, send.",
        "",
        "| Criterion | Target | Run 1 | Run 2 | Run 3 | Verdict |",
        "|---|---|---|---|---|---|",
    ]
    for index in range(5):
        verdict = (
            "MET" if all(t["passed"][index] for t in trials) else "MISSED"
        )
        cells = [t["metrics"][index] for t in trials]
        lines.append(
            "| " + " | ".join(
                [names[index], targets[index], *cells, verdict]
            ) + " |"
        )
    lines += [
        "",
        f"Cost measurement complete: {cost_complete}",
        f"Mean warm client elapsed seconds: {mean_seconds}",
        f"100 people x 1 request each x mean seconds: "
        f"{report['seconds_for_100_single_request_users']}",
        "",
        "Actual first-trial HTTP output for criteria 1, 2, and 4:",
        "```json",
        json.dumps(trials["valid"], indent=2),[0]
        "```",
        "Actual first-trial HTTP output for criterion 3:",
        "```json",
        json.dumps(trials["invalid"], indent=2),[0]
        "```",
        "Actual first-trial HTTP output for criterion 5:",
        "```json",
        json.dumps(trials["rate_limit"], indent=2),[0]
        "```",
        "Operational records produced by operational.py::"
        "install.<locals>.finish_operational_request:",
        "```json",
        json.dumps(own_records, indent=2),
        "```",
    ]
    markdown = "\n".join(lines)
    (folder / f"{stem}.md").write_text(markdown, encoding="utf-8")
    print("\n".join(lines[:13]), flush=True)
    print(f"Saved results/{stem}.json and results/{stem}.md")


if __name__ == "__main__":
    main()