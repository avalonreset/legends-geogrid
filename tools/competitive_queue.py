"""Durable Standard queue submission and retrieval for the competitive collector."""
from concurrent.futures import ThreadPoolExecutor, as_completed
import datetime as dt
import json
import math
import re
from pathlib import Path
from study_contract import digest

POST_ENDPOINT = "/serp/google/maps/task_post"


def load_submissions(ledger: Path):
    submissions = {}
    if ledger.exists():
        for line in ledger.read_text(encoding="utf-8").splitlines():
            event = json.loads(line)
            if event["event"] != "queued":
                continue
            raw = ledger.parent / "submissions" / f"{event['request_sha256']}.json"
            if not raw.is_file() or digest(raw) != event["envelope_sha256"]:
                raise ValueError("Saved queue submission missing or changed; do not resubmit")
            if not re.fullmatch(r"[A-Za-z0-9-]+", str(event["task_id"])):
                raise ValueError("Invalid saved provider task ID")
            submissions[event["request_sha256"]] = event
    return submissions


def process_queue(*, tasks, completed, submissions, output, append_event,
                  api_request, check_plan, budget, task_cost, workers, normalize):
    """Submit once, then make one retrieval pass. Pending tasks resume by GET only."""
    output = Path(output)
    (output / "submissions").mkdir(exist_ok=True)
    new_cost = 0.0
    fresh = [(task, fp) for task, fp in tasks if fp not in completed and fp not in submissions]
    for start in range(0, len(fresh), 100):
        check_plan()
        if (output / "STOP").exists():
            raise ValueError("STOP requested; no more queue tasks submitted")
        batch = fresh[start:start + 100]
        estimate = round(len(batch) * task_cost, 6)
        if new_cost + estimate > budget + 1e-9:
            raise ValueError("Actual queue cost plus next reservations exceeds budget")
        for task, fp in batch:
            with (output / "requests" / f"{fp}.json").open("x", encoding="utf-8") as f:
                json.dump({"endpoint": POST_ENDPOINT, "tasks": [task]}, f)
            append_event({"event": "reserve", "request_sha256": fp, "tag": task["tag"],
                          "reserved_usd": task_cost, "observed_at": dt.datetime.now(dt.timezone.utc).isoformat()})
        # A failed/ambiguous POST is never retried. Its reservations survive.
        envelope = api_request(POST_ENDPOINT, [t for t, _ in batch], timeout=90,
                               confirm=True, consumer="legends-geogrid",
                               estimated_cost_usd=estimate, max_cost_usd=estimate)
        for _, fp in batch:
            with (output / "submissions" / f"{fp}.json").open("x", encoding="utf-8") as f:
                json.dump(envelope, f, allow_nan=False)
        results = envelope.get("tasks") or []
        def key(task):
            return task.get("keyword"), task.get("tag")
        by_tag = {key(r.get("data", {})): r for r in results}
        if (envelope.get("status_code") != 20000 or len(results) != len(batch)
                or len(by_tag) != len(batch) or set(by_tag) != {key(t) for t, _ in batch}):
            raise ValueError("Queue acknowledgement mismatch; inspect saved submission before recovery")
        costs = [float(r.get("cost") or 0) for r in results]
        if any(not math.isfinite(c) or c < 0 for c in costs):
            raise ValueError("Invalid provider queue cost")
        if abs(sum(costs) - float(envelope.get("cost") or 0)) > 1e-8:
            raise ValueError("Queue cost mismatch; inspect saved receipt")
        for task, fp in batch:
            result = by_tag[key(task)]
            if result.get("status_code") != 20100 or not re.fullmatch(r"[A-Za-z0-9-]+", str(result.get("id") or "")):
                raise ValueError("Queue submission rejected; saved responses require review")
            event = {"event": "queued", "request_sha256": fp, "tag": task["tag"],
                     "task_id": result["id"], "actual_usd": float(result.get("cost") or 0),
                     "observed_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                     "envelope_sha256": digest(output / "submissions" / f"{fp}.json")}
            append_event(event)
            submissions[fp] = event
            new_cost += event["actual_usd"]
        if new_cost > budget + 1e-9:
            raise ValueError("Provider queue charge exceeded estimate; stopped before more tasks")

    pending = [(task, fp) for task, fp in tasks if fp not in completed]
    def retrieve(pair):
        task, fp = pair
        task_id = submissions[fp]["task_id"]
        envelope = api_request(f"/serp/google/maps/task_get/advanced/{task_id}", None,
                               timeout=90, confirm=False, consumer="legends-geogrid",
                               estimated_cost_usd=0, max_cost_usd=0)
        return task, fp, envelope

    failures = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for future in as_completed([pool.submit(retrieve, p) for p in pending]):
            try:
                task, fp, envelope = future.result()
                returned = envelope.get("tasks") or []
                if len(returned) != 1 or returned[0].get("id") != submissions[fp]["task_id"]:
                    raise ValueError("Queue retrieval identity mismatch")
                response = normalize(envelope, task)
                if response.get("status_code") in (20100, 20101, 20102, 40601, 40602):
                    continue
                # Submission is billed once; retrieval does not count it again.
                response["_actual_cost"] = submissions[fp]["actual_usd"]
                raw = output / "responses" / f"{fp}.json"
                with raw.open("x", encoding="utf-8") as f:
                    json.dump(envelope, f, allow_nan=False)
                append_event({"event": "response", "request_sha256": fp, "tag": task["tag"],
                              "actual_usd": 0, "submission_cost_usd": submissions[fp]["actual_usd"],
                              "observed_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                              "envelope_sha256": digest(raw), "response": response})
                completed[fp] = response
                if response.get("status_code") not in (20000, 40102):
                    raise ValueError("Provider queue task failed; no automatic repurchase")
            except Exception as exc:
                failures.append(str(exc))
    if failures:
        raise ValueError("; ".join(failures))
    return round(new_cost, 6)
