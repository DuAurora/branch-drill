import json
from pathlib import Path
import pytest
from branch_drill import (DrillError, validate_tree, public_view, evaluate_step, evaluate_path,
                          score_key_points, load_tree)

EX = Path(__file__).parents[1] / "examples" / "platform_crowding.json"
GOLD = {"quality", "next", "feedback", "tips", "keywords", "min_hits"}


@pytest.fixture
def tree():
    return load_tree(EX)


def _keys(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from _keys(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _keys(v)


def test_public_view_has_no_gold(tree):
    assert GOLD.isdisjoint(set(_keys(public_view(tree))))
    assert "verdict" not in json.dumps(public_view(tree))


def test_perfect_path_is_good(tree):
    r = evaluate_path(tree, [{"node_id": "n0", "option_id": "a"},
                             {"node_id": "n1", "option_id": "a", "text": "请排队，别挤，注意安全"}])
    assert r["verdict"] == "good" and r["completed"] and r["overall_score"] >= 80


def test_wrong_branch_fails(tree):
    r = evaluate_path(tree, [{"node_id": "n0", "option_id": "c"}])
    assert r["verdict"] == "fail" and r["stats"]["wrong"] == 1 and r["overall_score"] == 0


def test_incomplete_path(tree):
    r = evaluate_path(tree, [{"node_id": "n0", "option_id": "b"}])
    assert r["verdict"] == "incomplete" and not r["completed"]


def test_strict_path_rejects_jump(tree):
    with pytest.raises(DrillError):
        evaluate_path(tree, [{"node_id": "n1", "option_id": "a"}])
    evaluate_path(tree, [{"node_id": "n1", "option_id": "a"}], strict=False)


def test_key_points_synonyms_and_floor():
    r = score_key_points("请排队，别挤", ["排队", ["不要拥挤", "别挤"], "注意安全", "其他车门"], 2)
    assert r["hits"] == ["排队", "不要拥挤"] and r["passed"] and r["score"] >= 70
    assert score_key_points("", ["a"])["score"] == 0


def test_step_blends_scores(tree):
    r = evaluate_step(tree, "n1", "a", "")
    assert r["step_score"] == 65.0 and r["is_end"]


@pytest.mark.parametrize("mutate,msg", [
    (lambda t: t.update(entry="zz"), "entry"),
    (lambda t: t["nodes"]["n0"]["options"][0].update(next="zz"), "dangling"),
    (lambda t: t["nodes"]["n0"]["options"][0].update(quality="ok"), "quality"),
    (lambda t: t["nodes"]["n1"]["options"][0].update(next="n0"), "cycle"),
])
def test_validation_errors(tree, mutate, msg):
    mutate(tree)
    with pytest.raises(DrillError, match=msg):
        validate_tree(tree)


def test_unreachable_warning(tree):
    tree["nodes"]["orphan"] = {"kind": "end", "verdict": "good", "summary": ""}
    assert validate_tree(tree) == ["unreachable node: orphan"]
