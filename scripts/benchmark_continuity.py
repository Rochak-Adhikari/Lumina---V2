"""Deterministic, offline acceptance benchmark for the Continuity Engine.

Run ``python scripts/benchmark_continuity.py`` from any working directory. All
databases live in TemporaryDirectory instances. No user memory or model is used.

The permanent corpus contains 50 scenarios in each of the eight categories in
section 74 of the design. Expected answers come from the scenario inputs, never
from a second invocation of the operation being evaluated. Precision/recall are
micro averages over returned canonical records; false memories are unsupported
records, altered values, or missing/wrong provenance. Irrelevant but supported
records count against precision, not as invented memories. Temporal and
contradiction errors have their own denominators. Context tokens are a labelled
character-based estimate, not provider usage; actual model token cost is zero.
"""

from __future__ import annotations

import argparse
from collections import Counter
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import http.client
import json
from pathlib import Path
import socket
import statistics
import sys
import tempfile
import time
from typing import Any
from unittest.mock import patch
import urllib.request

# Support both direct execution and importing this module from pytest.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


CATEGORIES = (
    "explicit_facts", "temporal", "contradictions", "irrelevant",
    "multisession_continuation", "corrections", "decisions", "provenance",
)

# Ten different domains x five variations, rather than 50 copies of one string.
FACTS = (
    ("editor", "Vim", "Visual Studio Code"),
    ("database", "SQLite", "PostgreSQL"),
    ("deployment", "Windows desktop", "Linux server"),
    ("theme", "dark charcoal", "light ivory"),
    ("timezone", "Asia/Kathmandu", "Europe/London"),
    ("language", "नेपाली", "English"),
    ("release", "version 2.4", "version 3.1"),
    ("workspace", "C:/Projects/Orion", "D:/Work/Orion Next"),
    ("test_runner", "pytest", "unittest"),
    ("retention", "30 days", "90 days"),
)


@dataclass(frozen=True)
class Case:
    category: str
    index: int

    @property
    def id(self) -> str:
        return f"{self.category}-{self.index:02d}"

    @property
    def fact(self) -> tuple[str, str, str]:
        return FACTS[self.index // 5]

    @property
    def variant(self) -> int:
        return self.index % 5

    def at(self, day: int) -> str:
        # Fixed historical dates make reruns independent of the wall clock.
        stamp = datetime(2024, 1, 1, tzinfo=timezone.utc)
        return (stamp + timedelta(days=self.index * 5 + day)).isoformat()


CASES = tuple(Case(category, index) for category in CATEGORIES for index in range(50))


@dataclass
class Result:
    case_id: str
    category: str
    checks: int = 0
    failures: list[str] = field(default_factory=list)
    true_positives: int = 0
    false_positives: int = 0
    false_negatives: int = 0
    returned_records: int = 0
    false_memories: int = 0
    temporal_queries: int = 0
    stale_queries: int = 0
    contradiction_checks: int = 0
    contradiction_errors: int = 0
    continuity_slots: int = 0
    correct_continuity_slots: int = 0
    provenance_records: int = 0
    valid_provenance_records: int = 0
    latency_ms: list[float] = field(default_factory=list)
    context_chars: list[int] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.checks > 0 and not self.failures

    def check(self, condition: bool, message: str) -> None:
        self.checks += 1
        if not condition:
            self.failures.append(message)

    def slot(self, actual: Any, expected: Any, name: str) -> None:
        self.continuity_slots += 1
        self.correct_continuity_slots += int(actual == expected)
        self.check(actual == expected, f"{name}: expected {expected!r}, got {actual!r}")


@contextmanager
def offline_only():
    """Fail immediately on Python network access, including accidental providers."""
    attempts: list[str] = []

    def blocked(*args, **kwargs):
        attempts.append("network access")
        raise AssertionError("Continuity evaluation must run without network/model access")

    with (patch.object(socket.socket, "connect", blocked),
          patch.object(socket.socket, "connect_ex", blocked),
          patch.object(socket, "create_connection", blocked),
          patch.object(http.client.HTTPConnection, "connect", blocked),
          patch.object(http.client.HTTPSConnection, "connect", blocked),
          patch.object(urllib.request, "urlopen", blocked)):
        yield attempts


def summarize(results: list[Result]) -> dict[str, Any]:
    """Compute rates from measured counts, including non-perfect executions."""
    def total(name):
        return sum(getattr(result, name) for result in results)

    def rate(numerator, denominator):
        return numerator / denominator if denominator else None

    tp, fp, fn = (total(name) for name in
                  ("true_positives", "false_positives", "false_negatives"))
    latencies = sorted(value for r in results for value in r.latency_ms)
    contexts = [value for r in results for value in r.context_chars]
    return {
        "cases": len(results),
        "passed": sum(result.passed for result in results),
        "failed": sum(not result.passed for result in results),
        "checks": total("checks"),
        "precision": rate(tp, tp + fp),
        "recall": rate(tp, tp + fn),
        "true_positives": tp, "false_positives": fp, "false_negatives": fn,
        "false_memory_rate": rate(total("false_memories"), total("returned_records")),
        "staleness_error_rate": rate(total("stale_queries"), total("temporal_queries")),
        "contradiction_error_rate": rate(total("contradiction_errors"), total("contradiction_checks")),
        "continuity_accuracy": rate(total("correct_continuity_slots"), total("continuity_slots")),
        "provenance_coverage": rate(total("valid_provenance_records"), total("provenance_records")),
        "denominators": {
            "returned_records": total("returned_records"),
            "temporal_queries": total("temporal_queries"),
            "contradiction_checks": total("contradiction_checks"),
            "continuity_slots": total("continuity_slots"),
            "provenance_records": total("provenance_records"),
        },
        "latency_ms": {
            "samples": len(latencies),
            "mean": statistics.fmean(latencies) if latencies else None,
            "p50": statistics.median(latencies) if latencies else None,
            "p95": latencies[max(0, (95 * len(latencies) + 99) // 100 - 1)] if latencies else None,
            "max": max(latencies) if latencies else None,
        },
        "context_size_chars": {
            "samples": len(contexts),
            "mean": statistics.fmean(contexts) if contexts else None,
            "max": max(contexts) if contexts else None,
            "total": sum(contexts),
        },
        "context_token_estimate": sum((size + 3) // 4 for size in contexts),
        "context_token_estimate_method": "ceil(serialized context characters / 4) per response",
        "model_input_tokens": 0, "model_output_tokens": 0, "token_cost_usd": 0.0,
    }


class Scenario:
    """Arrange via public writes; evaluate public reads against authored values."""

    def __init__(self, case: Case, memory):
        self.case, self.memory = case, memory
        self.result = Result(case.id, case.category)
        self.known: dict[str, dict[str, Any]] = {}
        self.sources: dict[str, set[str]] = {}
        self.subject = memory.entity("person", f"Benchmark person {case.id}")["id"]
        self.project = memory.entity("project", f"Benchmark project {case.id}")["id"]

    def event(self, text: str, *, day=0, session="first", source="user", project=None):
        return self.memory.record_event(
            "conversation.message", {"role": "user" if source == "user" else "assistant", "text": text},
            source_type=source, source_id=f"{self.case.id}:{session}:{day}:{text}",
            session_id=f"{self.case.id}:{session}", project_id=project or self.project,
            timestamp=self.case.at(day),
        )

    def remember(self, predicate, value, *, day=0, subject=None, project=None,
                 supersedes=None, source="user", authorized=True, event=None):
        subject, project = subject or self.subject, project or self.project
        event = event or self.event(f"My {predicate} is {value}.", day=day, source=source, project=project)
        proposal = {"kind": "fact", "subject": subject, "predicate": predicate,
                    "object": value, "source_event_id": event["id"], "confidence": 0.8,
                    "stability": 0.7, "project_id": project, "data": {}}
        if supersedes:
            proposal["supersedes"] = supersedes
        outcome = self.memory.propose(proposal, authorized=authorized)
        record_id = outcome.get("record_id")
        if outcome.get("decision") in {"create", "duplicate", "reinforce", "supersede"} and record_id:
            self.known[record_id] = {"subject_entity_id": subject, "predicate": predicate,
                                     "object_value": value, "project_id": project}
            self.sources.setdefault(record_id, set()).add(event["id"])
        return outcome, event

    def created(self, outcome):
        if not outcome.get("ok") or not outcome.get("record_id"):
            raise AssertionError(f"Setup admission failed: {outcome}")
        return outcome["record_id"]

    def timed(self, operation, **kwargs):
        started = time.perf_counter_ns()
        answer = operation(**kwargs)
        self.result.latency_ms.append((time.perf_counter_ns() - started) / 1_000_000)
        self.result.context_chars.append(len(json.dumps(answer, ensure_ascii=False, sort_keys=True)))
        return answer

    def recall(self, expected, *, forbidden=(), temporal=False, **kwargs):
        answer = self.timed(self.memory.recall, **kwargs)
        items = answer["items"]
        actual = [item["id"] for item in items]
        observed, expected = set(actual), set(expected)
        r = self.result
        r.true_positives += len(observed & expected)
        r.false_positives += len(observed - expected)
        r.false_negatives += len(expected - observed)
        r.returned_records += len(items)
        r.check(observed == expected, f"recall expected {sorted(expected)}, got {sorted(observed)}")
        r.check(len(actual) == len(observed), "retrieval repeated a canonical record")
        if temporal:
            r.temporal_queries += 1
            r.stale_queries += bool(observed & set(forbidden))
        r.check(not (observed & set(forbidden)), "retrieval returned a stale/forbidden record")
        for item in items:
            record_id, record = item["id"], item["record"]
            gold = self.known.get(record_id)
            value_valid = gold is not None and all(record.get(k) == v for k, v in gold.items())
            event_ids = {entry.get("event_id") for entry in item["evidence"]}
            evidence_valid = bool(event_ids & self.sources.get(record_id, set()))
            r.provenance_records += 1
            r.valid_provenance_records += evidence_valid
            r.false_memories += not (value_valid and evidence_valid)
            r.check(value_valid, f"{record_id}: returned an unsupported or altered record")
            r.check(evidence_valid, f"{record_id}: no matching source event in provenance")
        return answer

    def explain(self, record_id):
        answer = self.timed(self.memory.explain, identity=record_id)
        gold = self.known[record_id]
        self.result.check(all(answer["record"].get(k) == v for k, v in gold.items()),
                          "explain changed the stored belief or decision")
        sources = {entry.get("event_id") for entry in answer["evidence"]}
        valid = self.sources[record_id] <= sources
        self.result.provenance_records += 1
        self.result.valid_provenance_records += valid
        self.result.check(valid, "explain omitted an independent supporting event")
        return answer


def run_case(case: Case) -> Result:
    from lumina.continuity.service import MemoryService
    with tempfile.TemporaryDirectory(prefix='lumina-memory-benchmark-') as folder, offline_only():
        path=Path(folder)/'memory.sqlite3'
        memory=MemoryService(path)
        scenario=Scenario(case,memory);r=scenario.result
        predicate,old,new=case.fact
        try:
            a,e=scenario.remember(predicate,old);old_id=scenario.created(a)
            scope={'query':predicate,'entity_id':scenario.subject,'project_id':scenario.project,'kind':'fact'}
            if case.category=='explicit_facts':
                scenario.recall({old_id},**scope)
                r.check(memory.explain(old_id)['record']['confirmed_by_user']==1,'Explicit fact lacks user authority')
            elif case.category=='temporal':
                b,_=scenario.remember(predicate,new,day=2,supersedes=old_id);new_id=scenario.created(b)
                scenario.recall({old_id},forbidden={new_id},temporal=True,as_of=case.at(1),**scope)
                scenario.recall({new_id},forbidden={old_id},temporal=True,**scope)
                scenario.recall(set(),temporal=True,as_of=case.at(-1),**scope)
            elif case.category=='contradictions':
                b,ev=scenario.remember(predicate,new,day=2,source='model');new_id=scenario.created(b)
                scenario.known[new_id]={'subject_entity_id':scenario.subject,'predicate':predicate,'object_value':new,'project_id':scenario.project}
                scenario.sources[new_id]={ev['id']}
                answer=scenario.recall({old_id,new_id},**scope)
                correct=b['decision']=='contradict' and bool(answer['uncertainties']) and answer['items'][0]['record']['object_value']==old
                r.contradiction_checks+=1;r.contradiction_errors+=not correct
                r.check(correct,'A weaker contradiction overwrote or hid confirmed evidence')
            elif case.category=='irrelevant':
                for i in range(6):scenario.remember('unrelated'+str(i),'Background detail '+str(i),day=1)
                scenario.recall({old_id},**scope)
                unknown=scenario.recall(set(),query='unsupported_knowledge_'+case.id,entity_id=scenario.subject)
                r.check(bool(unknown['uncertainties']),'Unknown answer must express uncertainty')
                bounded=memory.recall('',project_id=scenario.project,budget=512)
                r.check(len(json.dumps(bounded,ensure_ascii=False))<=512,'Context exceeds budget')
            elif case.category=='multisession_continuation':
                workspace=str(Path(folder)/('workspace '+str(case.variant)))
                memory.record_event('workspace.changed',{'workspace':workspace},session_id='first',project_id=scenario.project,timestamp=case.at(0))
                task='task-'+case.id
                memory.observe_task(task,'WAITING_FOR_USER','Complete '+predicate,workspace=workspace,session_id='first',project_id=scenario.project)
                memory.consolidate('first');memory.close()
                memory=MemoryService(path);scenario.memory=memory
                # An unrelated new project must not erase the explicitly requested scope.
                memory.set_workspace(str(Path(folder)/'other'),session_id='second')
                context=scenario.timed(memory.continuation,project_id=scenario.project)
                r.slot(context['project']['id'],scenario.project,'project')
                r.slot(context['workspace'],workspace,'workspace')
                r.slot(context['active_task']['task_id'],task,'task')
                r.slot(context['open_loops'][0]['task_id'],task,'open loop')
                r.check(bool(context['blockers']),'Missing blocker')
                r.check(bool(context['episode']),'Missing meaningful episode')
                memory.observe_task(task,'COMPLETED',project_id=scenario.project,session_id='second')
                r.check(not memory.continuation(scenario.project)['active_task'],'Completed task returned as unfinished')
            elif case.category=='corrections':
                ev=scenario.event('Correction: '+new,day=2)
                b=memory.correct(old_id,new,source_event_id=ev['id'],authorized=True);new_id=scenario.created(b)
                scenario.known[new_id]={**scenario.known[old_id],'object_value':new}
                scenario.sources[new_id]={ev['id']}
                scenario.recall({new_id},forbidden={old_id},temporal=True,**scope)
                scenario.recall({old_id},forbidden={new_id},temporal=True,as_of=case.at(1),**scope)
                r.check(memory.explain(new_id)['history'][0]['id']==old_id,'Correction discarded history')
            elif case.category=='decisions':
                ev=scenario.event('We chose '+old+' over '+new+' because local operation matters.',day=1)
                result=memory.propose({'kind':'decision','source_event_id':ev['id'],'project_id':scenario.project,
                    'data':{'subject':predicate,'chosen_option':old,'alternatives':[{'option':new,'reason':'Higher operating cost'}],
                    'reasoning':'Local operation matters','constraints':['No new service'],
                    'assumptions':[{'fact_id':old_id}],'expected_outcome':'Low operational overhead'}},authorized=True)
                decision_id=scenario.created(result)
                explanation=scenario.timed(memory.explain_decision,identity=decision_id)
                d=explanation['record']
                r.check(d['chosen_option']==old and d['alternatives_json'][0]['option']==new,'Decision alternatives lost')
                r.check(d['reasoning']=='Local operation matters' and d['constraints_json']==['No new service'],'Causal explanation lost')
                memory.correct(old_id,new,authorized=True)
                r.check(memory.explain_decision(decision_id)['record']['status']=='needs_review','Changed assumption did not trigger review')
            elif case.category=='provenance':
                duplicate,_=scenario.remember(predicate,old,event=e)
                r.check(duplicate['decision']=='duplicate','Same evidence was reinforced twice')
                b,e2=scenario.remember(predicate,old,day=2)
                r.check(b['decision']=='reinforce','Independent evidence was not attached')
                explanation=scenario.explain(old_id)
                r.check(len(explanation['evidence'])==2,'Duplicate evidence or independent evidence missing')
                scenario.recall({old_id},**scope)
        except Exception as error:
            r.check(False,type(error).__name__+': '+str(error))
        finally:
            memory.close()
        return r


def run_benchmark():
    results=[run_case(case) for case in CASES]
    report=summarize(results)
    report['categories']={name:summarize([r for r in results if r.category==name]) for name in CATEGORIES}
    report['failures']=[{'case':r.case_id,'failures':r.failures} for r in results if not r.passed]
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path)
    args=parser.parse_args();report=run_benchmark()
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k not in {'categories','failures'}},indent=2))
    if report['failures']:print(json.dumps(report['failures'][:6],indent=2,ensure_ascii=False))
    raise SystemExit(1 if report['failed'] else 0)
