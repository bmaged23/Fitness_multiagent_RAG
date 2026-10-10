from __future__ import annotations

import sys
import time
import uuid
from collections import defaultdict
from pathlib import Path
from threading import Lock

from dotenv import load_dotenv
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import HumanMessage

# --------------------------------------------------
# Project configuration
# --------------------------------------------------

ROOT = Path(__file__).resolve().parents[1]

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

load_dotenv(ROOT / ".env")

# Adjust this import if your coach module or builder is named differently.
from fitness_multiagent_rag.agents.coach.agent import build_coach_agent
from config.settings import RECURSION_LIMIT

# --------------------------------------------------
# Test settings
# --------------------------------------------------

DEFAULT_REQUEST = (
    "I am trainee 1. Create a 3-day beginner full-body workout plan "
    "for muscle building using dumbbell-only equipment for 8 weeks. "
    "Use the trainee profile, retrieve grounded programs and exercises, "
    "and give me the final plan."
)



# --------------------------------------------------
# Performance profiler
# --------------------------------------------------

class AgentProfiler(BaseCallbackHandler):

    def __init__(self):
        self.start_times = {}
        self.records = []
        self.lock = Lock()

    def _start(self, kind, name, run_id):
        with self.lock:
            self.start_times[str(run_id)] = (
                time.perf_counter(),
                kind,
                name,
            )

        print(f"[START] {kind}: {name}", flush=True)

    def _end(self, run_id, error=None):
        with self.lock:
            record = self.start_times.pop(str(run_id), None)

            if record is None:
                return

            start, kind, name = record
            duration = time.perf_counter() - start

            self.records.append({
                "kind": kind,
                "name": name,
                "duration": duration,
                "status": "FAILED" if error else "OK",
            })

        print(
            f"[END] {kind}: {name} "
            f"| {duration:.3f}s"
            f"{' | FAILED' if error else ''}",
            flush=True,
        )

    # Tool callbacks
    def on_tool_start(
        self, serialized, input_str, *, run_id, **kwargs
    ):
        name = kwargs.get("name") or (serialized or {}).get(
            "name", "unknown_tool"
        )
        self._start("TOOL", name, run_id)

    def on_tool_end(self, output, *, run_id, **kwargs):
        from fitness_multiagent_rag.utils.tool_errors import tool_result_error
        self._end(run_id, error=tool_result_error(output))

    def on_tool_error(self, error, *, run_id, **kwargs):
        self._end(run_id, error=error)

    # LLM callbacks
    def on_chat_model_start(
        self, serialized, messages, *, run_id, **kwargs
    ):
        name = (serialized or {}).get("name", "ChatModel")
        self._start("LLM", name, run_id)

    def on_llm_start(
        self, serialized, prompts, *, run_id, **kwargs
    ):
        name = (serialized or {}).get("name", "LLM")
        self._start("LLM", name, run_id)

    def on_llm_end(self, response, *, run_id, **kwargs):
        self._end(run_id)

    def on_llm_error(self, error, *, run_id, **kwargs):
        self._end(run_id, error=error)

    # Final report
    def report(self, total_time):
        print("\n" + "=" * 75)
        print("COACH PERFORMANCE REPORT")
        print("=" * 75)

        print(
            f"{'TYPE':<10} {'NAME':<35} "
            f"{'TIME (s)':>12} {'STATUS':>10}"
        )
        print("-" * 75)

        for record in self.records:
            print(
                f"{record['kind']:<10} "
                f"{record['name'][:35]:<35} "
                f"{record['duration']:>12.3f} "
                f"{record['status']:>10}"
            )

        print("-" * 75)

        for kind in ("LLM", "TOOL"):
            durations = [
                r["duration"]
                for r in self.records
                if r["kind"] == kind
            ]

            print(
                f"{kind} calls: {len(durations)}"
                f" | Failed: "
                f"{sum(1 for r in self.records if r['kind'] == kind and r['status'] == 'FAILED')}"
                f" | Sum of durations: {sum(durations):.3f}s"
            )

        print(f"\nTOTAL REQUEST TIME: {total_time:.3f}s")

        # Group repeated calls by name
        grouped = defaultdict(list)

        for record in self.records:
            grouped[
                (record["kind"], record["name"])
            ].append(record["duration"])

        print("\nTIME BY COMPONENT")
        print("-" * 75)

        for (kind, name), durations in grouped.items():
            print(
                f"{kind}: {name}"
                f" | Calls: {len(durations)}"
                f" | Total: {sum(durations):.3f}s"
                f" | Average: {sum(durations)/len(durations):.3f}s"
            )

        print("=" * 75)
        print(
            "Note: Nested calls may overlap. "
            "Their durations should not be added "
            "to calculate total request time."
        )


# --------------------------------------------------
# Coach integration test
# --------------------------------------------------

def test_coach(request: str = DEFAULT_REQUEST):

    profiler = AgentProfiler()
    total_start = time.perf_counter()

    print("\n" + "=" * 75)
    print("COACH AGENT — PERFORMANCE TEST")
    print("=" * 75)

    print("\nBuilding Coach agent...", flush=True)
    build_start = time.perf_counter()

    agent = build_coach_agent()

    build_time = time.perf_counter() - build_start

    print(f"Agent initialization: {build_time:.3f}s")

    print(f"\nREQUEST:\n{request}\n")

    request_id = str(uuid.uuid4())
    invocation_start = time.perf_counter()

    try:
        result = agent.invoke(
            {
                "messages": [
                    HumanMessage(content=request)
                ]
            },
            config={
                "configurable": {"retriever_request_id": request_id},
                "callbacks": [profiler],
                "recursion_limit": RECURSION_LIMIT,
                "run_id": uuid.uuid4(),
            },
        )

        print("\n" + "=" * 75)
        print("FINAL COACH RESPONSE")
        print("=" * 75)

        for message in reversed(result.get("messages", [])):
            if (
                getattr(message, "type", "") == "ai"
                and message.content
            ):
                print(message.content)
                break

    except Exception as exc:
        print(
            f"\nERROR: {type(exc).__name__}: {exc}",
            flush=True,
        )
        raise

    finally:
        from fitness_multiagent_rag.agents.retriever.agent import _release_search_budget
        _release_search_budget(request_id)
        invocation_time = (
            time.perf_counter() - invocation_start
        )
        total_time = time.perf_counter() - total_start

        print(
            f"\nAgent invocation time: {invocation_time:.3f}s"
        )
        print(f"Agent initialization time: {build_time:.3f}s")

        profiler.report(total_time)


if __name__ == "__main__":
    # Optional: pass a custom request on the command line.
    #   python3 -u tests/test_coach.py "your request here"
    custom_request = " ".join(sys.argv[1:]).strip()
    test_coach(custom_request or DEFAULT_REQUEST)


