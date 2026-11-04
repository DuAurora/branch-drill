"""Core engine. Pure Python, no third-party dependencies.

Tree format (dict / JSON):
{
  "id": str, "title": str, "entry": node_id,
  "nodes": {
    node_id: {"kind": "choice", "prompt": str,
              "options": [{"id", "text", "quality": correct|suboptimal|wrong,
                           "next": node_id, "feedback"?, "tips"?}],
              "key_points"?: {"prompt", "keywords": [...], "min_hits": int, "sample"?}},
    node_id: {"kind": "end", "verdict": "good"|"improve"|"fail", "summary": str}
  }
}
Fields `quality`, `next`, `feedback`, `tips`, `key_points.keywords`, `key_points.min_hits`
are *gold* fields: they must never be sent to the learner before answering.
"""
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping, Optional

QUALITIES = ("correct", "suboptimal", "wrong")
DEFAULT_WEIGHTS = {"quality": {"correct": 100.0, "suboptimal": 60.0, "wrong": 0.0},
                   "choice_weight": 0.65, "key_point_weight": 0.35,
                   "good_threshold": 80.0, "key_point_floor": 70.0}


class DrillError(ValueError):
    """Raised for malformed trees or invalid answers."""


def load_tree(path: str | Path) -> dict[str, Any]:
    tree = json.loads(Path(path).read_text(encoding="utf-8"))
    validate_tree(tree)
    return tree


def validate_tree(tree: Mapping[str, Any]) -> list[str]:
    """Validate structure. Raises DrillError on fatal problems; returns warnings (e.g. unreachable nodes)."""
    nodes = tree.get("nodes") or {}
    entry = tree.get("entry")
    if not tree.get("id"):
        raise DrillError("tree.id is required")
    if entry not in nodes:
        raise DrillError(f"entry node {entry!r} not found")
    for nid, node in nodes.items():
        kind = node.get("kind", "choice")
        if kind == "end":
            continue
        if kind != "choice":
            raise DrillError(f"node {nid}: unknown kind {kind!r}")
        opts = node.get("options") or []
        if not opts:
            raise DrillError(f"node {nid}: choice node has no options")
        seen = set()
        for o in opts:
            if o.get("id") in seen:
                raise DrillError(f"node {nid}: duplicate option id {o.get('id')!r}")
            seen.add(o.get("id"))
            if o.get("quality") not in QUALITIES:
                raise DrillError(f"node {nid}/{o.get('id')}: bad quality {o.get('quality')!r}")
            if o.get("next") not in nodes:
                raise DrillError(f"node {nid}/{o.get('id')}: dangling next {o.get('next')!r}")
    # reachability + cycle detection (DFS)
    warnings: list[str] = []
    state: dict[str, int] = {}

    def dfs(n: str) -> None:
        state[n] = 1
        for o in nodes[n].get("options") or []:
            m = o["next"]
            if state.get(m) == 1:
                raise DrillError(f"cycle detected via {n} -> {m}")
            if m not in state:
                dfs(m)
        state[n] = 2

    dfs(entry)
    for nid in nodes:
        if nid not in state:
            warnings.append(f"unreachable node: {nid}")
    return warnings


def public_view(tree: Mapping[str, Any]) -> dict[str, Any]:
    """Return a learner-safe copy with all gold fields removed."""
    out_nodes: dict[str, Any] = {}
    for nid, node in (tree.get("nodes") or {}).items():
        if node.get("kind") == "end":
            out_nodes[nid] = {"id": nid, "kind": "end"}
            continue
        item: dict[str, Any] = {"id": nid, "kind": "choice", "prompt": node.get("prompt", ""),
                                "options": [{"id": o["id"], "text": o.get("text", "")}
                                            for o in node.get("options") or []]}
        kp = node.get("key_points")
        if kp:
            item["key_points"] = {"prompt": kp.get("prompt", ""), "sample": kp.get("sample", "")}
        out_nodes[nid] = item
    return {k: deepcopy(tree.get(k, "")) for k in ("id", "title", "description", "entry")} | {
        "nodes": out_nodes}


def score_key_points(text: str, keywords: list[str], min_hits: int = 1,
                     floor: float = DEFAULT_WEIGHTS["key_point_floor"]) -> dict[str, Any]:
    """Case-insensitive substring hit check of free-text answer against expected key points.
    Each keyword may be a str or a list of synonyms (any synonym counts)."""
    raw = (text or "").strip().lower()
    need = max(1, int(min_hits or 1))
    if not raw:
        return {"score": 0.0, "hits": [], "hit_count": 0, "passed": False}
    hits = []
    for kw in keywords or []:
        group = kw if isinstance(kw, (list, tuple)) else [kw]
        if any(str(s).strip().lower() and str(s).strip().lower() in raw for s in group):
            hits.append(group[0])
    ratio = len(hits) / max(len(keywords or []), 1)
    passed = len(hits) >= need
    score = min(100.0, ratio * 100.0 + (10.0 if passed else 0.0))
    if passed:
        score = max(score, floor)
    return {"score": round(score, 1), "hits": hits, "hit_count": len(hits), "passed": passed}


def _option(node: Mapping[str, Any], option_id: str) -> Mapping[str, Any]:
    for o in node.get("options") or []:
        if o.get("id") == option_id:
            return o
    raise DrillError(f"option {option_id!r} not found")


def evaluate_step(tree: Mapping[str, Any], node_id: str, option_id: str, text: str = "",
                  weights: Optional[Mapping[str, Any]] = None) -> dict[str, Any]:
    w = {**DEFAULT_WEIGHTS, **(weights or {})}
    nodes = tree.get("nodes") or {}
    node = nodes.get(node_id)
    if node is None:
        raise DrillError(f"node {node_id!r} not found")
    if node.get("kind") == "end":
        raise DrillError("cannot answer an end node")
    opt = _option(node, option_id)
    q = opt.get("quality", "wrong")
    choice_score = float(w["quality"].get(q, 0.0))
    kp_result = None
    step_score = choice_score
    kp = node.get("key_points")
    if kp:
        kp_result = score_key_points(text, list(kp.get("keywords") or []), int(kp.get("min_hits") or 1),
                                     float(w["key_point_floor"]))
        step_score = round(choice_score * w["choice_weight"] + kp_result["score"] * w["key_point_weight"], 1)
    nxt = opt.get("next")
    nxt_node = nodes.get(nxt)
    return {"node_id": node_id, "option_id": option_id, "quality": q, "choice_score": choice_score,
            "key_points": kp_result, "step_score": step_score,
            "feedback": opt.get("feedback", ""), "tips": opt.get("tips", ""),
            "next_node_id": nxt, "next_node": public_view(tree)["nodes"].get(nxt),
            "is_end": bool(nxt_node and nxt_node.get("kind") == "end")}


def evaluate_path(tree: Mapping[str, Any], steps: list[Mapping[str, Any]],
                  weights: Optional[Mapping[str, Any]] = None, strict: bool = True) -> dict[str, Any]:
    """Score a full answer path. With strict=True, each step must follow the previous option's `next`
    (prevents clients from cherry-picking nodes)."""
    w = {**DEFAULT_WEIGHTS, **(weights or {})}
    if not steps:
        raise DrillError("empty path")
    expected = tree.get("entry")
    results = []
    for s in steps:
        nid = str(s.get("node_id", ""))
        if strict and nid != expected:
            raise DrillError(f"path broken: expected node {expected!r}, got {nid!r}")
        r = evaluate_step(tree, nid, str(s.get("option_id", "")), str(s.get("text", "")), w)
        results.append(r)
        expected = r["next_node_id"]
    stats = {q: sum(1 for r in results if r["quality"] == q) for q in QUALITIES}
    avg = round(sum(r["step_score"] for r in results) / len(results), 1)
    end = (tree.get("nodes") or {}).get(results[-1]["next_node_id"]) or {}
    completed = end.get("kind") == "end"
    verdict = end.get("verdict", "improve") if completed else "incomplete"
    if completed and avg >= w["good_threshold"] and stats["wrong"] == 0:
        verdict = "good"
    return {"tree_id": tree.get("id"), "overall_score": avg, "verdict": verdict, "completed": completed,
            "summary": end.get("summary", ""), "stats": {"steps": len(results), **stats},
            "review": [{k: r[k] for k in ("node_id", "option_id", "quality", "step_score",
                                          "feedback", "tips", "key_points")} for r in results]}
