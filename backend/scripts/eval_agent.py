r"""Run the golden questions on live models: accuracy, tokens, cost and time per model.

Where it sits:
    evals/golden_questions.toml -> [eval_agent] -> the real orchestrator and tools
    -> a live provider (Claude by default) -> a report per model

BUSINESS: before a release, or before switching models, this answers "how often
  does the agent get the tape's numbers right, and what does that cost?" The
  answer is graded against each question's true value from the tape (golden.py).
TECH:
    From backend\ (PowerShell), with the key in the environment:
        $env:ANTHROPIC_API_KEY = "..."        # never commit it
        .venv\Scripts\python.exe scripts\eval_agent.py
        .venv\Scripts\python.exe scripts\eval_agent.py --models claude-haiku-5-5 claude-sonnet-5-5
        .venv\Scripts\python.exe scripts\eval_agent.py --only wac new_york_upb --out eval.json
        .venv\Scripts\python.exe scripts\eval_agent.py --fake      # free dry run, no network
    THIS SPENDS REAL MONEY: 21 questions cost about $0.006 on Claude Haiku 5.5 and
    $0.13 on Claude Sonnet 5.5 (measured 2026-11-25, docs/evals/2026-11-25.json).
    --max-usd caps the run: past it, built-in rules answer and those questions are
    marked as fallbacks. The tape is the seeded default in data\ (generated if
    missing). Every model gets the same questions and the same tape.
    Output uses PASS / FAIL, not symbols, so Windows PowerShell 5.1 prints it.
    Exit codes: 0 the run finished; 1 no API key is set; 2 every answer on a model
    came from the built-in rules (a rejected key, say), so the model was never
    measured and --out is NOT written: a failed run cannot overwrite a good report.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from dataclasses import asdict, replace
from decimal import Decimal
from pathlib import Path
from typing import Any

# TECH: run as a script from backend\, so put backend\ on the import path for `app`.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import loan_tape_gen as gen  # noqa: E402  (after the path line above)
from app import main  # noqa: E402
from app.agent.config import AgentConfig, load_agent_config  # noqa: E402
from app.agent.golden import GoldenResult, fake_script, load_golden, run_golden  # noqa: E402
from app.agent.providers.fake_provider import FakeProvider  # noqa: E402
from app.agent.service import AskService, build_ask_service, close_ask_service  # noqa: E402

EVAL_VISITOR = "eval"


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    """Command-line options (see the header for examples)."""
    p = argparse.ArgumentParser(description="Run Ask the Tape's golden questions on live models.")
    p.add_argument("--models", nargs="+", help="Model ids to test (default: the tape_query model)")
    p.add_argument("--only", nargs="+", help="Run only these question ids")
    p.add_argument("--max-usd", type=Decimal, default=Decimal("0.50"), help="Spending cap for the run")
    p.add_argument("--no-escalate", action="store_true", help="Never move up to the escalation model")
    p.add_argument("--fake", action="store_true", help="Use scripted answers (free, no network)")
    p.add_argument("--data-dir", type=Path, default=gen.DEFAULT_OUT_DIR, help="Folder with the tape")
    p.add_argument("--out", type=Path, help="Also write the results as JSON here")
    return p.parse_args(argv)


def eval_config(base: AgentConfig, model: str, args: argparse.Namespace) -> AgentConfig:
    """llm.toml with this model on tape_query, the run's cap, and no visitor limit.

    TECH: dataclasses.replace copies a frozen dataclass with some fields changed.
    """
    route = base.tasks["tape_query"]
    route = replace(route, model=model, escalation_model=model if args.no_escalate else route.escalation_model)
    budget = replace(base.budget, daily_cap_usd=args.max_usd, questions_per_visitor_per_day=10**6)
    return replace(base, tasks={**base.tasks, "tape_query": route}, budget=budget)


def summarize(model: str, results: list[GoldenResult]) -> dict[str, Any]:
    """Accuracy, tokens, cost and time for one model's run."""
    n = len(results) or 1
    tokens = {k: sum(r.usage[k] for r in results) for k in results[0].usage} if results else {}
    cost = sum((Decimal(r.cost_usd) for r in results), Decimal(0))
    return {"model": model, "questions": len(results), "passed": sum(r.passed for r in results),
            "accuracy_pct": round(100 * sum(r.passed for r in results) / n, 1),
            "fallbacks": sum(r.fallback_reason is not None for r in results), "tokens": tokens,
            "cost_usd": f"{cost:.6f}", "cost_per_question_usd": f"{cost / n:.6f}",
            "avg_ms": round(sum(r.elapsed_ms for r in results) / n)}


def print_report(summary: dict[str, Any], results: list[GoldenResult]) -> None:
    """One line per question, then the model's totals."""
    print(f"\n=== {summary['model']} ===")
    for r in results:
        flag = "PASS" if r.passed else "FAIL"
        note = f" [fallback: {r.fallback_reason}]" if r.fallback_reason else ""
        print(f"{flag}  {r.id:<28} expected {r.expected!s:<22} ${r.cost_usd}  {r.elapsed_ms} ms{note}")
        if not r.passed:
            print(f"      answer: {r.answer[:200]}")
    t = summary["tokens"]
    print(f"Accuracy {summary['passed']}/{summary['questions']} ({summary['accuracy_pct']}%), "
          f"fallbacks {summary['fallbacks']}")
    print(f"Tokens: input {t.get('input_tokens', 0):,}, output {t.get('output_tokens', 0):,}, "
          f"cache read {t.get('cache_read_tokens', 0):,}, cache write {t.get('cache_write_tokens', 0):,}")
    print(f"Cost ${summary['cost_usd']} total, ${summary['cost_per_question_usd']} per question; "
          f"average {summary['avg_ms']} ms")


def all_fallback_error(model: str, results: list[GoldenResult]) -> str | None:
    """The error to print when no answer on this model came from the model, else None.

    BUSINESS: on 2026-11-25 a run with the placeholder key "passed" 11 of 21
      questions with $0 spent: every answer came from the built-in rules after a
      401. That measures the rules, not the model, so it must not count as an eval.
      Some fallbacks (the --max-usd cap running out partway) are still a valid run.
    TECH: results is one model's list; an empty list is not an all-fallback run.
      collections.Counter counts each fallback reason, e.g. {"http_401": 21}.
    """
    if not results or any(r.fallback_reason is None for r in results):
        return None
    reasons = ", ".join(f"{k} x{n}" for k, n in Counter(r.fallback_reason for r in results).items())
    return (f"ERROR: all {len(results)} answers on {model} came from built-in rules, not the model "
            f"({reasons}). The model was never used: check ANTHROPIC_API_KEY and the --max-usd cap. "
            f"No report was written.")


def run_model(service: AskService, args: argparse.Namespace, questions: list, store: Any) -> list[GoldenResult]:
    """All questions on one model. TECH: --fake swaps in a fresh FakeProvider per question."""
    route = service.cfg.tasks["tape_query"]

    def ask(q: Any) -> Any:
        if args.fake:
            service.orchestrator.providers[route.provider] = FakeProvider(fake_script(q))
        return service.orchestrator.ask(q.question, EVAL_VISITOR)
    return run_golden(ask, questions, store.con)


def main_cli(argv: list[str] | None = None) -> int:
    """Run the evaluation.

    BUSINESS: a report is written only when every model was really measured.
    TECH: exit code 0 when done, 1 if the live provider has no key, 2 if every
      answer on a model fell back (see all_fallback_error); 1 and 2 write no --out.
    """
    args = parse_args(argv)
    base = load_agent_config()
    questions = [q for q in load_golden() if not args.only or q.id in args.only]
    store = main.open_store(args.data_dir)
    report: list[dict[str, Any]] = []
    try:
        for model in args.models or [base.tasks["tape_query"].model]:
            cfg = eval_config(base, model, args)
            service = build_ask_service(args.data_dir / main.TAPE_FILE, store.columns, main.all_labels(),
                                        {k: q.where for k, q in store.questions.items()},
                                        lambda: main.tape_summary(store), cfg)
            try:
                route = cfg.tasks["tape_query"]
                if not args.fake and not service.orchestrator.providers[route.provider].available():
                    print(f"No API key for {route.provider}: set {cfg.provider_keys.get(route.provider)}.")
                    return 1
                results = run_model(service, args, questions, store)
            finally:
                close_ask_service(service)
            summary = summarize(model, results)
            print_report(summary, results)
            # BUSINESS: stop at once. A rejected key fails every model the same way,
            #   and returning before --out keeps the last good report on disk.
            error = all_fallback_error(model, results)
            if error:
                print(error)
                return 2
            report.append({**summary, "results": [asdict(r) for r in results]})
    finally:
        store.con.close()
    if args.out:
        args.out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main_cli())
