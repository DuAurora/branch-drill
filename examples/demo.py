"""Run: python examples/demo.py"""
import json
from pathlib import Path
from branch_drill import load_tree, public_view, evaluate_path

tree = load_tree(Path(__file__).with_name("platform_crowding.json"))
print(json.dumps(public_view(tree)["nodes"]["n0"], ensure_ascii=False, indent=2))
result = evaluate_path(tree, [
    {"node_id": "n0", "option_id": "a"},
    {"node_id": "n1", "option_id": "a", "text": "请大家排队，别挤，注意安全"},
])
print(json.dumps(result, ensure_ascii=False, indent=2))
