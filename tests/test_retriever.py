
from __future__ import annotations

import sys
import time
from collections import defaultdict
from pathlib import Path
from threading import Lock
from uuid import uuid4

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

from fitness_multiagent_rag.agents.retriever.agent import (
    build_retriever_agent,
    _release_search_budget,
)


# --------------------------------------------------
# Performance profiler
# --------------------------------------------------

class AgentProfiler(BaseCallbackHandler):

    def __init__(self):
        super().__init__()

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

        print(
            f"[START] {kind}: {name}",
            flush=True,
        )

    def _end(self, run_id, error=None):
        with self.lock:
            record = self.start_times.pop(
                str(run_id),
                None,
            )

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
            f"[END] {kind}: {name}"
            f" | {duration:.3f}s"
            f"{' | FAILED' if error else ''}",
            flush=True,
        )

    # --------------------------------------------------
    # Tool callbacks
    # --------------------------------------------------

    def on_tool_start(
        self,
        serialized,
        input_str,
        *,
        run_id,
        **kwargs,
    ):
        name = (
            kwargs.get("name")
            or serialized.get("name", "unknown_tool")
        )

        self._start(
            "TOOL",
            name,
            run_id,
        )

    def on_tool_end(
        self,
        output,
        *,
        run_id,
        **kwargs,
    ):
        from fitness_multiagent_rag.utils.tool_errors import tool_result_error
        self._end(run_id, error=tool_result_error(output))

    def on_tool_error(
        self,
        error,
        *,
        run_id,
        **kwargs,
    ):
        self._end(
            run_id,
            error=error,
        )

    # --------------------------------------------------
    # LLM callbacks
    # --------------------------------------------------

    def on_chat_model_start(
        self,
        serialized,
        messages,
        *,
        run_id,
        **kwargs,
    ):
        name = serialized.get(
            "name",
            "ChatModel",
        )

        self._start(
            "LLM",
            name,
            run_id,
        )

    def on_llm_start(
        self,
        serialized,
        prompts,
        *,
        run_id,
        **kwargs,
    ):
        name = serialized.get(
            "name",
            "LLM",
        )

        self._start(
            "LLM",
            name,
            run_id,
        )

    def on_llm_end(
        self,
        response,
        *,
        run_id,
        **kwargs,
    ):
        self._end(run_id)

    def on_llm_error(
        self,
        error,
        *,
        run_id,
        **kwargs,
    ):
        self._end(
            run_id,
            error=error,
        )

    # --------------------------------------------------
    # Performance report
    # --------------------------------------------------

    def report(
        self,
        total_time,
        build_time,
        invocation_time,
    ):

        print("\n" + "=" * 78)
        print("RETRIEVER PERFORMANCE REPORT")
        print("=" * 78)

        print(
            f"{'TYPE':<10}"
            f" {'NAME':<35}"
            f" {'TIME (s)':>12}"
            f" {'STATUS':>10}"
        )

        print("-" * 78)

        with self.lock:
            records = list(self.records)

        for record in records:
            print(
                f"{record['kind']:<10}"
                f" {record['name'][:35]:<35}"
                f" {record['duration']:>12.3f}"
                f" {record['status']:>10}"
            )

        print("-" * 78)

        for kind in ("LLM", "TOOL"):
            durations = [
                r["duration"]
                for r in records
                if r["kind"] == kind
            ]

            failed = sum(
                1
                for r in records
                if r["kind"] == kind
                and r["status"] == "FAILED"
            )

            print(
                f"{kind} calls: {len(durations)}"
                f" | Failed: {failed}"
                f" | Total: {sum(durations):.3f}s"
            )

        # --------------------------------------------------
        # Qdrant search statistics
        # --------------------------------------------------

        search_records = [
            r
            for r in records
            if r["kind"] == "TOOL"
            and r["name"] in (
                "search_programs",
                "search_exercises",
            )
        ]

        print("\nSEARCH STATISTICS")
        print("-" * 78)

        print(
            f"Search tool calls: {len(search_records)}"
        )

        print(
            "Configured maximum admitted searches: 3"
        )

        print(
            "Note: blocked search tool calls may also "
            "appear in the callback count."
        )

        # --------------------------------------------------
        # Execution summary
        # --------------------------------------------------

        print("\nEXECUTION SUMMARY")
        print("-" * 78)

        print(
            f"Initialization: {build_time:.3f}s"
        )

        print(
            f"Agent request:  {invocation_time:.3f}s"
        )

        print(
            f"TOTAL TIME:     {total_time:.3f}s"
        )

        # --------------------------------------------------
        # Time by component
        # --------------------------------------------------

        grouped = defaultdict(list)

        for record in records:
            grouped[
                (
                    record["kind"],
                    record["name"],
                )
            ].append(record["duration"])

        print("\nTIME BY COMPONENT")
        print("-" * 78)

        for (kind, name), durations in grouped.items():

            total = sum(durations)
            average = total / len(durations)

            print(
                f"{kind}: {name}"
                f" | Calls: {len(durations)}"
                f" | Total: {total:.3f}s"
                f" | Average: {average:.3f}s"
            )

        print("=" * 78)

        print(
            "Nested calls can overlap; do not add their "
            "durations to calculate total time."
        )


# --------------------------------------------------
# Retriever integration test
# --------------------------------------------------

def test_retriever():

    profiler = AgentProfiler()

    total_start = time.perf_counter()

    print("\n" + "=" * 78)
    print("RETRIEVER AGENT — PERFORMANCE TEST")
    print("=" * 78)

    # --------------------------------------------------
    # Build Retriever
    # --------------------------------------------------

    print(
        "\nBuilding Retriever agent...",
        flush=True,
    )

    build_start = time.perf_counter()

    agent = build_retriever_agent()

    build_time = (
        time.perf_counter() - build_start
    )

    print(
        f"Retriever initialization: "
        f"{build_time:.3f}s",
        flush=True,
    )

    # --------------------------------------------------
    # Test request
    # --------------------------------------------------

    request = (
        "Retrieve relevant fitness programs and exercises "
        "for a beginner who wants to build muscle using "
        "dumbbells only. The training plan should have "
        "3 full-body workout days per week for 8 weeks. "
        "Search both fitness_programs and fitness_exercises, "
        "evaluate relevance and coverage, and return "
        "the best grounded results with their source details."
    )

    print(
        f"\nREQUEST:\n{request}\n",
        flush=True,
    )

    # --------------------------------------------------
    # Request configuration
    # --------------------------------------------------

    request_id = str(uuid4())

    config = {
        "configurable": {
            "retriever_request_id": request_id,
        },
        "recursion_limit": 20,
        "callbacks": [profiler],
    }

    invocation_start = time.perf_counter()

    # --------------------------------------------------
    # Invoke Retriever
    # --------------------------------------------------

    try:

        result = agent.invoke(
            {
                "messages": [
                    HumanMessage(content=request)
                ]
            },
            config=config,
        )

        # --------------------------------------------------
        # Final response
        # --------------------------------------------------

        print("\n" + "=" * 78)
        print("FINAL RETRIEVER RESPONSE")
        print("=" * 78)

        final_message = None

        for message in reversed(
            result.get("messages", [])
        ):
            if (
                getattr(message, "type", "") == "ai"
                and message.content
            ):
                final_message = message
                break

        if final_message is not None:
            print(
                final_message.content,
                flush=True,
            )
        else:
            print(
                "No final AI response was returned.",
                flush=True,
            )

    # --------------------------------------------------
    # Error handling
    # --------------------------------------------------

    except Exception as exc:

        print(
            f"\nERROR: "
            f"{type(exc).__name__}: {exc}",
            flush=True,
        )

        raise

    # --------------------------------------------------
    # Cleanup and report
    # --------------------------------------------------

    finally:

        _release_search_budget(request_id)

        invocation_time = (
            time.perf_counter() - invocation_start
        )

        total_time = (
            time.perf_counter() - total_start
        )

        profiler.report(
            total_time=total_time,
            build_time=build_time,
            invocation_time=invocation_time,
        )


# --------------------------------------------------
# Entry point
# --------------------------------------------------

if __name__ == "__main__":
    test_retriever()

