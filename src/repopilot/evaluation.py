"""Objective Stage 4 evaluation. Unknown evidence is never converted to a pass.

Adapters may supply canonical events through EngineRun.evaluation_events. Events
are harness-owned observations, never JSON extracted from assistant prose.
"""

from __future__ import annotations

import hashlib
from collections import Counter, defaultdict
from itertools import combinations
from statistics import mean, median, stdev

CATEGORIES = ("simple", "cross-file", "recovery", "replan", "long-horizon", "hitl")
REQUIREMENTS = {"recovery", "replan", "approval", "budget", "termination"}
SUCCESS_STATUSES = {"SUCCESS", "SUCCEEDED", "Submitted"}


def ratio(n: int | float, d: int | float) -> float | None:
    return n / d if d else None


def distribution(values: list[float]) -> dict:
    return dict(
        n=len(values),
        mean=mean(values) if values else None,
        median=median(values) if values else None,
        stddev=stdev(values) if len(values) > 1 else None,
        min=min(values) if values else None,
        max=max(values) if values else None,
    )


def command_result(observation: dict) -> dict:
    result = observation.get("result", {})
    if isinstance(result, dict) and isinstance(result.get("result"), dict):
        result = result["result"]
    return result if isinstance(result, dict) else {}


def normalize_trace(trace: list[dict]) -> list[dict]:
    """Preserve source IDs and normalize only facts actually recorded by runtime."""
    events = []
    step = 0
    for index, event in enumerate(trace):
        kind = event.get("type")
        if kind == "model_request":
            step = event.get("step", step)
        normalized = dict(event, source_index=index, step=step)
        if kind == "tool_result":
            obs = event.get("observation", {})
            result = command_result(obs)
            normalized["failed"] = obs.get("ok") is False or result.get("exit_code", 0) != 0
        events.append(normalized)
    return events


def evaluate(
    repository_pass: bool | None,
    status: str | None,
    metrics: dict,
    events: list[dict],
    requirements: list[str] | tuple[str, ...],
) -> dict:
    unknown = set(requirements) - REQUIREMENTS
    if unknown:
        raise ValueError(f"Unknown behavior requirements: {sorted(unknown)}")
    by_type = defaultdict(list)
    for event in events:
        by_type[event.get("type")].append(event)
    results = by_type["tool_result"]
    calls = by_type["tool_call"]
    failures = [e for e in results if e.get("failed") is True]
    # Recovery requires a linked scenario resolution supplied by an observing
    # harness. A later unrelated successful read is not recovery evidence.
    scenarios = by_type["scenario_triggered"]
    recovery = [e for e in scenarios if e.get("capability") == "recovery"]
    resolved = {e.get("scenario_id") for e in by_type["scenario_resolved"] if e.get("verified") is True}
    recovered = sum(e.get("scenario_id") in resolved for e in recovery)
    evidence = [e for e in scenarios if e.get("capability") == "replan"]
    replans = by_type["plan_replanned"]
    valid_replans = []
    for e in evidence:
        for revision in replans:
            # Semantic criterion comes from the task's objective strategy
            # assertion, not version/status changes or update_plan counts.
            if (
                revision.get("scenario_id") == e.get("scenario_id")
                and revision.get("before_strategy") != revision.get("after_strategy")
                and revision.get("before_strategy")
                and revision.get("after_strategy")
                and revision.get("strategy_verified") is True
                and revision.get("observation_index", revision.get("step", 0))
                > e.get("observation_index", e.get("step", 0))
            ):
                valid_replans.append(revision)
                break
    checks = {}
    for requirement in requirements:
        passed = None
        reason = "unsupported: missing linked scenario or complete policy instrumentation"
        audit = by_type["scenario_audit"][-1] if by_type["scenario_audit"] else {}
        if (
            requirement in {"recovery", "replan"}
            and audit.get(requirement)
            and not (recovery if requirement == "recovery" else evidence)
        ):
            passed = False
            reason = "Required scenario was not observed by the complete command observer."
        elif requirement == "recovery" and recovery:
            passed = recovered == len(recovery)
            reason = "Every triggered recoverable scenario must have an objective resolution."
        elif requirement == "replan" and evidence:
            passed = len(valid_replans) == len(evidence)
            reason = "Evidence must precede a verified substantive strategy revision."
        elif requirement == "approval" and by_type["approval_audit"]:
            audit = by_type["approval_audit"][-1]
            if audit.get("complete") is True:
                passed = (
                    audit.get("requested") is True
                    and audit.get("bypasses") == 0
                    and audit.get("decisions_respected") is True
                )
                reason = "Complete risk-action audit, including rejected operations and bypasses."
        elif requirement == "termination" and repository_pass is not None and status is not None:
            passed = repository_pass and status in SUCCESS_STATUSES
            reason = "Successful final repository and successful agent termination; timeliness deferred."
        elif requirement == "budget" and by_type["budget_audit"]:
            audit = by_type["budget_audit"][-1]
            if audit.get("complete") is True:
                passed = audit.get("within_limits") is True
                reason = "Complete adapter budget audit."
        checks[requirement] = {"pass": passed, "reason": reason}
    behavior = (
        False
        if any(c["pass"] is False for c in checks.values())
        else None
        if any(c["pass"] is None for c in checks.values())
        else True
    )
    task_pass = (
        False
        if repository_pass is False or behavior is False
        else None
        if repository_pass is None or behavior is None
        else True
    )
    termination = None
    if repository_pass is not None and status is not None:
        termination = (
            ("correct_success" if repository_pass else "false_success")
            if status in SUCCESS_STATUSES
            else ("false_failure" if repository_pass else "correct_failure")
        )
    # Only adjacent native read/search calls with identical arguments and
    # identical observations qualify. Shell commands are deliberately excluded.
    observations = {e.get("tool_call_id"): e for e in results}
    redundant = 0
    for left, right in zip(calls, calls[1:]):
        if (
            left.get("tool_name") in {"read_file", "search_code", "list_files"}
            and left.get("tool_name") == right.get("tool_name")
            and left.get("arguments") == right.get("arguments")
        ):
            a, b = observations.get(left.get("tool_call_id")), observations.get(right.get("tool_call_id"))
            if a and b and not a.get("failed") and not b.get("failed"):
                ra, rb = command_result(a.get("observation", {})), command_result(b.get("observation", {}))
                if ra.get("stdout") is not None and ra.get("stdout") == rb.get("stdout"):
                    redundant += 1
    audit = by_type["scenario_audit"][-1] if by_type["scenario_audit"] else {}
    replan_triggers = sum(
        any(r.get("scenario_id") == e.get("scenario_id") for r in replans + by_type["plan_revision_attempt"])
        for e in evidence
    )
    return {
        "schema_version": 4,
        "repository_pass": repository_pass,
        "behavior_pass": behavior,
        "task_pass": task_pass,
        "behavior_verifier": checks,
        "termination": termination,
        "recovery": {
            "trigger_count": len(recovery) if audit.get("recovery") or recovery else None,
            "attempt_count": len(by_type["recovery_attempt"]) if recovery else None,
            "resolved_count": recovered if recovery else None,
            "success_rate": ratio(recovered, len(recovery)),
            "post_recovery_repository_pass": repository_pass if recovery else None,
            "failure_types": [e.get("failure_type") for e in recovery],
        },
        "replan": {
            "evidence_count": len(evidence) if audit.get("replan") or evidence else None,
            "triggered_count": len(replans) if events else None,
            "valid_count": len(valid_replans) if evidence else None,
            "trigger_rate": ratio(replan_triggers, len(evidence)),
            "triggered_scenarios": replan_triggers if evidence else None,
            "missed_scenarios": len(evidence) - replan_triggers if evidence else None,
            "unnecessary_replans": None,
            "success_rate": ratio(len(valid_replans), len(evidence)),
            "post_replan_repository_pass": repository_pass if replan_triggers else None,
        },
        "tool_quality": {
            "failure_count": len(failures) if results else None,
            "failure_rate": ratio(len(failures), len(results)),
            "recovery_rate": ratio(recovered, len(recovery)),
            "recovery_scope": "manifest-declared public-command failures only",
            "redundant_calls": redundant if calls else None,
        },
        "budget_usage": {
            "limits": metrics.get("run_budget"),
            "steps_used": metrics.get("steps"),
            "replans_used": metrics.get("replans"),
            "complete_audit": False,
        },
        "approval_events": [e for e in events if str(e.get("type", "")).startswith("approval_")],
        "churn": {
            "status": "unsupported",
            "reason": "Missing immutable repository states at every step boundary.",
            "first_solved_step": None,
            "final_step": metrics.get("steps"),
            "post_solution_steps": None,
        },
        "duration": {
            "wall_clock_seconds": metrics.get("duration_seconds"),
            "llm_seconds": sum(e["duration_seconds"] for e in by_type["model_response"])
            if by_type["model_response"]
            and all(isinstance(e.get("duration_seconds"), (int, float)) for e in by_type["model_response"])
            else None,
            "tool_seconds": None,
            "orchestration_seconds": None,
        },
    }


def aggregate(records: list[dict]) -> dict:
    """Group within model. Null trials remain visible, never counted as failures."""
    groups = defaultdict(list)
    for record in records:
        if not record.get("task_id") or not record.get("engine"):
            continue
        model, engine = record.get("model", "unknown"), record["engine"]
        for dimension, value in [
            ("overall", "all"),
            ("category", record.get("category", "unclassified")),
            ("task", record["task_id"]),
        ] + [("capability", c) for c in record.get("capabilities", [])]:
            groups[(model, engine, dimension, value)].append(record)
    output = []
    for (model, engine, dimension, value), rows in sorted(groups.items()):
        known = [r for r in rows if r.get("task_pass") is not None]
        solved = [r for r in rows if r.get("task_pass") is True]
        terms = Counter(r.get("evaluation", {}).get("termination") for r in rows)
        term_count = sum(n for t, n in terms.items() if t is not None)
        numeric = {}
        numeric_specs = {
            "llm_calls": ("metrics", "llm_calls"),
            "steps": ("metrics", "steps"),
            "tool_calls": ("metrics", "tool_calls"),
            "tool_failures": ("metrics", "tool_failures"),
            "retries": ("metrics", "retries"),
            "replans": ("metrics", "replans"),
            "redundant_calls": ("evaluation", ("tool_quality", "redundant_calls")),
            "total_tokens": ("tokens", "total"),
            "input_tokens": ("tokens", "prompt"),
            "output_tokens": ("tokens", "completion"),
            "duration_seconds": ("metrics", "duration_seconds"),
        }
        for key, spec in numeric_specs.items():

            def metric(r):
                source, field = spec
                if source == "tokens":
                    return (r.get("metrics", {}).get("tokens") or {}).get(field)
                if source == "evaluation":
                    value = r.get("evaluation", {})
                    for part in field:
                        value = (value or {}).get(part)
                    return value
                return r.get("metrics", {}).get(field)

            values = [metric(r) for r in rows]
            valid = [v for v in values if isinstance(v, (int, float)) and not isinstance(v, bool)]
            numeric[key] = dict(
                distribution(valid),
                total=sum(valid) if len(valid) == len(rows) else None,
                per_solved=ratio(sum(valid), len(solved)) if len(valid) == len(rows) else None,
                solved_distribution=distribution([metric(r) for r in solved if isinstance(metric(r), (int, float))]),
            )
        recovery_rows = [
            r["evaluation"]["recovery"]
            for r in rows
            if r.get("evaluation", {}).get("recovery", {}).get("trigger_count")
        ]
        trigger_count = sum(r["trigger_count"] for r in recovery_rows)
        replan_rows = [
            r["evaluation"]["replan"] for r in rows if r.get("evaluation", {}).get("replan", {}).get("evidence_count")
        ]
        evidence_count = sum(r["evidence_count"] for r in replan_rows)
        churn_available = any(
            r.get("evaluation", {}).get("churn", {}).get("status") == "supported" for r in rows
        )
        output.append(
            dict(
                model=model,
                engine=engine,
                dimension=dimension,
                value=value,
                trials=len(rows),
                evaluated=len(known),
                unsupported=len(rows) - len(known),
                pass_count=len(solved),
                pass_rate=ratio(len(solved), len(known)),
                successful_termination_rate=ratio(terms["correct_success"], term_count),
                false_success_rate=ratio(terms["false_success"], term_count),
                false_failure_rate=ratio(terms["false_failure"], term_count),
                termination_counts={k: v for k, v in terms.items() if k is not None},
                recovery_rate=ratio(sum(r["resolved_count"] or 0 for r in recovery_rows), trigger_count),
                repository_pass_count=sum(r.get("repository_pass") is True for r in rows),
                repository_evaluated=sum(r.get("repository_pass") is not None for r in rows),
                behavior_pass_count=sum(r.get("behavior_pass") is True for r in rows),
                behavior_evaluated=sum(r.get("behavior_pass") is not None for r in rows),
                churn_available=churn_available,
                completion_precision=ratio(terms["correct_success"], terms["correct_success"] + terms["false_success"]),
                completion_recall=ratio(terms["correct_success"], terms["correct_success"] + terms["false_failure"]),
                post_recovery_task_success_rate=ratio(
                    sum(r["post_recovery_repository_pass"] is True for r in recovery_rows),
                    sum(r["post_recovery_repository_pass"] is not None for r in recovery_rows),
                ),
                replan_trigger_rate=ratio(sum(r["triggered_scenarios"] or 0 for r in replan_rows), evidence_count),
                replan_success_rate=ratio(sum(r["valid_count"] or 0 for r in replan_rows), evidence_count),
                post_replan_task_success_rate=ratio(
                    sum(r["post_replan_repository_pass"] is True for r in replan_rows),
                    sum(r["post_replan_repository_pass"] is not None for r in replan_rows),
                ),
                numeric=numeric,
            )
        )
    pairs = defaultdict(Counter)
    aligned = defaultdict(dict)
    for r in records:
        if r.get("task_id") and r.get("engine"):
            key = (r.get("model", "unknown"), r.get("round", 1), r.get("repeat", 1), r["task_id"])
            if r["engine"] in aligned[key]:
                raise ValueError(f"Duplicate paired trial: {key} / {r['engine']}")
            aligned[key][r["engine"]] = r
    engines = sorted({r["engine"] for r in records if r.get("engine")})
    for key, trials in aligned.items():
        for left, right in combinations(engines, 2):
            a, b = trials.get(left), trials.get(right)
            outcome = (
                "unavailable"
                if a is None or b is None or a.get("task_pass") is None or b.get("task_pass") is None
                else (
                    "both_pass"
                    if a["task_pass"] and b["task_pass"]
                    else "left_only"
                    if a["task_pass"]
                    else "right_only"
                    if b["task_pass"]
                    else "neither_pass"
                )
            )
            for category in ("all", (a or b).get("category", "unclassified")):
                pairs[(key[0], left, right, category)][outcome] += 1
    return {
        "schema_version": 4,
        "groups": output,
        "paired": [
            dict(
                model=k[0],
                left=k[1],
                right=k[2],
                category=k[3],
                **{
                    name: counts[name]
                    for name in ("both_pass", "left_only", "right_only", "neither_pass", "unavailable")
                },
            )
            for k, counts in sorted(pairs.items())
        ],
    }


def markdown(summary: dict) -> str:
    lines = [
        "# Stage 4 evaluation",
        "",
        "| Model | Engine | Group | Task pass | Successful termination | Recovery | LLM calls / solved | Tokens / solved | Tool failures / solved | Post-solution churn |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]

    def display(value):
        return "unsupported" if value is None else f"{value:.3f}"

    for group in summary["groups"]:
        if group["dimension"] == "task":
            continue
        n = group["numeric"]
        lines.append(
            f"| {group['model']} | {group['engine']} | {group['dimension']}:{group['value']} | "
            f"{group['pass_count']}/{group['evaluated']} ({group['unsupported']} unavailable) | "
            + " | ".join(
                display(v)
                for v in (
                    group["successful_termination_rate"],
                    group["recovery_rate"],
                    n["llm_calls"]["per_solved"],
                    n["total_tokens"]["per_solved"],
                    n["tool_failures"]["per_solved"],
                )
            )
            + " | "
            + ("available" if group["churn_available"] else "unsupported")
            + " |"
        )
    lines += [
        "",
        "Cost per solved includes failed trials. Missing usage makes the corresponding total unavailable.",
        "Compare tokens only within the same model. Detailed distributions and paired counts are in summary.json.",
        "",
        "| Model | Category | Left | Right | Both | Left only | Right only | Neither | Unavailable |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for p in summary["paired"]:
        lines.append(
            "| "
            + " | ".join(
                str(p[k])
                for k in (
                    "model",
                    "category",
                    "left",
                    "right",
                    "both_pass",
                    "left_only",
                    "right_only",
                    "neither_pass",
                    "unavailable",
                )
            )
            + " |"
        )
    return "\n".join(lines) + "\n"


class ScenarioObserver:
    """Observe public commands identically at both engines' environment seam.

    Does not execute extra commands or alter observations. Exact command matching
    is deliberately conservative; compound shell expressions are not inferred.
    """

    def __init__(self, environment, workspace, spec):
        self.environment = environment
        self.workspace = workspace
        self.spec = spec
        self.events = []
        self.sequence = 0
        self.pending_recovery = False
        self.recovery_number = 0
        self.protected = {name: self._fingerprint(name) for name in spec.get("recovery_files", [])}
        self.evidence_seen = False
        self.old_plan = None
        self.last_plan = None
        self.replanned = False

    def __getattr__(self, name):
        return getattr(self.environment, name)

    def _fingerprint(self, name):
        path = (self.workspace / name).resolve()
        if not path.is_relative_to(self.workspace.resolve()):
            return None
        try:
            return hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError:
            return None

    def _plan(self):
        path = self.spec.get("plan_path")
        if not path:
            return None
        target = (self.workspace / path).resolve()
        if not target.is_relative_to(self.workspace.resolve()):
            return None
        try:
            return target.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            return None

    def execute(self, action, *args, **kwargs):
        if isinstance(action, dict):
            command = action.get("command", "")
        else:
            argv = action.argv
            command = argv[-1] if len(argv) == 3 and argv[0] in {"bash", "sh"} and argv[1] in {"-lc", "-c"} else None
        before = self._plan()
        result = self.environment.execute(action, *args, **kwargs)
        data = result if isinstance(result, dict) else result.to_dict()
        code = data.get("returncode", data.get("exit_code"))
        stdout = data.get("output", data.get("stdout", ""))
        self.sequence += 1

        def emit(kind, **values):
            self.events.append(dict(type=kind, observation_index=self.sequence, source="environment", **values))

        if command and command == self.spec.get("recovery_command") and code is not None:
            if self.pending_recovery:
                emit("recovery_attempt", scenario_id=f"public-command-{self.recovery_number}")
            if code != 0 and not self.pending_recovery:
                self.pending_recovery = True
                self.recovery_number += 1
                emit(
                    "scenario_triggered",
                    scenario_id=f"public-command-{self.recovery_number}",
                    capability="recovery",
                    failure_type="test_failure",
                )
            elif code == 0 and self.pending_recovery:
                emit(
                    "scenario_resolved",
                    scenario_id=f"public-command-{self.recovery_number}",
                    verified=all(
                        digest is not None and self._fingerprint(name) == digest
                        for name, digest in self.protected.items()
                    ),
                )
                self.pending_recovery = False
        if (
            command
            and command == self.spec.get("evidence_command")
            and code == 0
            and self.spec.get("evidence_marker")
            and self.spec["evidence_marker"] in stdout
            and not self.evidence_seen
        ):
            self.evidence_seen = True
            self.old_plan = before
            self.last_plan = before
            emit("scenario_triggered", scenario_id="new-evidence", capability="replan")
        after = self._plan()
        if self.evidence_seen and after is not None and after != self.last_plan:
            emit("plan_revision_attempt", scenario_id="new-evidence")
            self.last_plan = after
        old, new = self.spec.get("before_strategy"), self.spec.get("after_strategy")
        if (
            self.evidence_seen
            and not self.replanned
            and self.old_plan
            and after
            and old
            and new
            and old in self.old_plan
            and new not in self.old_plan
            and new in after
            and old not in after
        ):
            emit(
                "plan_replanned",
                scenario_id="new-evidence",
                before_strategy=old,
                after_strategy=new,
                strategy_verified=True,
            )
            self.replanned = True
        return result


def scenario_audit(spec: dict) -> dict:
    return {
        "type": "scenario_audit",
        "recovery": bool(spec.get("recovery_command")),
        "replan": all(
            spec.get(k)
            for k in ("evidence_command", "evidence_marker", "plan_path", "before_strategy", "after_strategy")
        ),
    }
