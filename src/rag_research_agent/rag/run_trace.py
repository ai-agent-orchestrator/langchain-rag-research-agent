"""Opt-in, local research metrics. Never retain callback inputs or raw outputs.

Use TraceResearchRunner in place of ResearchRunner with trace=True, or pass a
TraceCollector to trace=. Existing ResearchRunner and its defaults are untouched.
Clocks return monotonic seconds. Model roles must be supplied explicitly; shadow
token records are not evidence of actual model calls or monetary cost.
"""
from __future__ import annotations

from collections import defaultdict
import json
from pathlib import Path
import re
from threading import RLock
from time import perf_counter
from uuid import uuid4

from langchain_core.callbacks import BaseCallbackHandler

from rag_research_agent.core.run_events import NodeEvent, RunEvent, cost_krw
from rag_research_agent.rag.research_graph import ResearchRunner

MATURITY = "incubating"


def event_from_result(result, domain, config):
    """Adapt a ResearchResult; config is explicit event metadata, not graph config.

    Missing timings, prices, grade and TTFT remain zero/estimated. No question,
    report, source, exception text, or unvalidated free-text log is copied.
    verify counts retries (the initial verification is not a loop).
    """
    path = tuple(result.path)
    nodes = config.get("nodes")
    if nodes is None:
        # Preserve repeated nodes and distribute the ordered legacy cost records
        # to invocations, rather than multiplying aggregate totals by path count.
        records = iter(result.cost)
        pending = next(records, None)
        nodes = []
        for name in path:
            usage = {"model_in": 0, "model_out": 0}
            seen = set()
            while pending is not None and pending[0] == name and pending[1] not in seen:
                seen.add(pending[1])
                usage[pending[1]] = usage.get(pending[1], 0) + pending[2]
                pending = next(records, None)
            nodes.append(NodeEvent(name, 0, usage["model_in"], usage["model_out"], None, True))
    nodes = tuple(nodes)
    cutoff = result.stopped in {"PER_NODE_TOKEN_CAP", "LOOP_LIMIT", "COST_LIMIT", "NODE_ERROR"}
    if result.verify_codes and result.shadow_tokens >= config.get("max_shadow_tokens", float("inf")):
        cutoff = True
    end_type = "cutoff" if cutoff else (
        "give_up" if result.stopped or result.verify_codes or result.interrupts else "END")
    calls = {"slm": 0, "flagship": 0}
    for node in nodes:
        role = config.get("model_roles", {}).get(node.model)
        if role is not None:
            if role not in calls:
                raise ValueError("model role must be slm or flagship")
            calls[role] += 1
    usage = defaultdict(lambda: {"in": 0, "out": 0})
    for node in nodes:
        if node.model is not None:
            usage[node.model]["in"] += node.tokens_in
            usage[node.model]["out"] += node.tokens_out
    amount = cost_krw(usage, config["pricing"]) if "pricing" in config else 0
    return RunEvent(
        run_id=config.get("run_id", str(uuid4())), domain=domain,
        track=config.get("track", "deep"), config=config.get("config", "graph_full"),
        dataset=config.get("dataset", ""), sha=config.get("sha", ""), path=path,
        end_type=end_type,
        loops={"rewrite": path.count("rewrite"), "gap": path.count("retrieve_gap"),
               "verify": max(0, path.count("verify") - 1)},
        calls=calls, tokens={"in": sum(n.tokens_in for n in nodes),
                             "out": sum(n.tokens_out for n in nodes)},
        cost_krw=amount, ttft_ms=config.get("ttft_ms", 0), total_ms=config.get("total_ms", 0),
        grade=config.get("grade", {"docs_in": 0, "docs_kept": 0, "relevance_drop_rate": 0}),
        guard=(), nodes=nodes, estimated=config.get("estimated", True))


class JsonlSink:
    """Append one validated run per line, confined to .runs/events/<domain>."""

    def __init__(self, root=Path(".runs/events")):
        self.root = Path(root)
        if not self.root.resolve().is_relative_to(Path(".runs").resolve()):
            raise ValueError("event sink must be inside .runs")
        self._lock = RLock()

    def __call__(self, event):
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", event.domain):
            raise ValueError("domain must be a safe directory name")
        payload = event.to_json(dumps=json.dumps) + "\n"
        target = self.root / event.domain / "events.jsonl"
        if not target.resolve().is_relative_to(Path(".runs").resolve()):
            raise ValueError("event sink must be inside .runs")
        with self._lock:
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("a", encoding="utf-8", newline="\n") as stream:
                stream.write(payload)


class TraceCollector(BaseCallbackHandler):
    """LangGraph node callbacks, keyed by invocation ID for parallel nodes.

    Legacy node costs are shadow estimates. LLM callbacks supply measured
    usage and model names when the injected model reports them.
    One collector belongs to one active invocation, including each resume.
    """

    def __init__(self, *, domain="research", config=None, clock=perf_counter, sink=None):
        self.domain, self.config, self.clock = domain, dict(config or {}), clock
        self.sink = sink if sink is not None else JsonlSink()
        self._lock = RLock()
        self.last_event = None
        self._active = {}
        self._nodes = []
        self._parents = {}
        self._llms = {}
        self._measured = defaultdict(list)

    def begin(self):
        with self._lock:
            self._active.clear()
            self._nodes.clear()
            self._parents.clear()
            self._llms.clear()
            self._measured.clear()
            self.last_event = None
            self._started = self.clock()
            self._ttft_ms = None

    def on_chain_start(self, serialized, inputs, *, run_id, metadata=None, tags=None, **kwargs):
        name = (metadata or {}).get("langgraph_node")
        with self._lock:
            self._parents[run_id] = kwargs.get("parent_run_id")
            if name and kwargs.get("name") == name and any(t.startswith("graph:step:") for t in tags or ()):
                self._active[run_id] = (name, self.clock())

    def on_llm_start(self, serialized, prompts, *, run_id, parent_run_id=None, **kwargs):
        with self._lock:
            owner = parent_run_id
            while owner is not None and owner not in self._active:
                owner = self._parents.get(owner)
            model = (kwargs.get("invocation_params") or {}).get("model_name")
            model = model or (kwargs.get("invocation_params") or {}).get("model")
            if owner is not None:
                self._llms[run_id] = (owner, model)

    def on_chat_model_start(self, serialized, messages, **kwargs):
        self.on_llm_start(serialized, (), **kwargs)

    def on_llm_end(self, response, *, run_id, **kwargs):
        with self._lock:
            record = self._llms.pop(run_id, None)
            if record is None:
                return
            owner, model = record
            model = model or (response.llm_output or {}).get("model_name")
            usage = (response.llm_output or {}).get("token_usage")
            if usage is None:
                usage = (response.llm_output or {}).get("usage")
            if usage is None:
                usage = {}
                for generations in response.generations:
                    for generation in generations:
                        metadata = getattr(getattr(generation, "message", None), "usage_metadata", None) or {}
                        if metadata:
                            for key in ("input_tokens", "output_tokens"):
                                usage[key] = usage.get(key, 0) + metadata.get(key, 0)
            self._measured[owner].append((model, usage))

    def on_llm_new_token(self, token, **kwargs):
        with self._lock:
            if self._ttft_ms is None:
                self._ttft_ms = (self.clock() - self._started) * 1000

    def on_chain_end(self, outputs, *, run_id, **kwargs):
        with self._lock:
            active = self._active.pop(run_id, None)
            if active is None:
                return
            name, started = active
            elapsed = (self.clock() - started) * 1000
            usage = {"model_in": 0, "model_out": 0}
            for _, kind, count in (outputs or {}).get("cost", ()):
                usage[kind] = usage.get(kind, 0) + count
            measured = self._measured.pop(run_id, [])
            if measured:
                # One entry per actual model call, with node time on the first.
                for index, (model, tokens) in enumerate(measured):
                    self._nodes.append(NodeEvent(name, elapsed if index == 0 else 0,
                        tokens.get("prompt_tokens", tokens.get("input_tokens", 0)),
                        tokens.get("completion_tokens", tokens.get("output_tokens", 0)), model, not bool(tokens)))
            else:
                self._nodes.append(NodeEvent(name, elapsed, usage["model_in"], usage["model_out"], None, True))

    def on_chain_error(self, error, *, run_id, **kwargs):
        # Never retain error messages or input text.
        self.on_chain_end({}, run_id=run_id)

    def finish(self, result, *, max_shadow_tokens):
        with self._lock:
            # nodes may contain multiple measured model calls for one path node.
            nodes = tuple(self._nodes)
            config = {**self.config, "nodes": nodes,
                      "total_ms": (self.clock() - self._started) * 1000,
                      "max_shadow_tokens": max_shadow_tokens}
            if self._ttft_ms is not None:
                config["ttft_ms"] = self._ttft_ms
            event = event_from_result(result, self.domain, config)
            self.sink(event)
            self.last_event = event
            return event


class TraceResearchRunner(ResearchRunner):
    """Drop-in opt-in runner; trace=False creates no collector or output files."""

    def __init__(self, *args, trace=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.trace = TraceCollector() if trace is True else trace

    def _config(self, thread_id):
        config = super()._config(thread_id)
        if self.trace:
            config = {**config, "callbacks": [self.trace]}
        return config

    def _execute(self, graph_input, config):
        if not self.trace:
            return super()._execute(graph_input, config)
        self.trace.begin()
        result = super()._execute(graph_input, config)
        self.trace.finish(result, max_shadow_tokens=self.cfg.max_shadow_tokens)
        return result
