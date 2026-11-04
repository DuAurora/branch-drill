# branch-drill

[中文](#中文) | [English](#english)

## 中文

**一个零依赖的分支决策树实训引擎：服务端保存"金标"，客户端只拿到去答案的题面，按路径判分并给出逐步复盘。**

### 问题背景
职业技能实训（客运服务、安全应急、医护、客服等）中，很多处置题不是单选题，而是"一步选择决定下一步局面"的情景链。常见问题：
- 答案（哪个选项正确、跳转到哪、反馈）若下发到前端，学员打开开发者工具就能看到；
- 客户端可伪造路径，只提交"好看"的节点；
- 题目由教师手写 JSON，容易出现悬空跳转、死循环、孤立节点；
- 除了选择，还想检查学员能否用自己的话说出关键要点。

### 算法思路
1. **结构校验**：检查入口、选项 id 唯一、`quality` 合法、`next` 不悬空；DFS 检测环路，报告不可达节点。
2. **金标剥离**：`public_view()` 生成仅含题面与选项文字的副本，去掉 `quality / next / feedback / tips / keywords / min_hits` 及结局判定。
3. **单步判分**：选项质量映射为分数（correct 100 / suboptimal 60 / wrong 0）；若节点设置了 `key_points`，对自由文本做大小写无关的要点命中（支持同义词组），按 0.65·选择 + 0.35·要点 加权，达标时要点分有下限保护。
4. **路径判分**：严格模式下每一步必须是上一步选项的 `next`，防止跳题；汇总平均分、正确/次优/错误计数，结合结局节点给出 `good / improve / fail / incomplete`。
所有权重都可通过 `weights` 参数覆盖。

### 用法
```bash
pip install -e ".[test]"
python examples/demo.py
pytest
```
```python
from branch_drill import load_tree, public_view, evaluate_path
tree = load_tree("examples/platform_crowding.json")
send_to_client(public_view(tree))           # 无答案
result = evaluate_path(tree, steps)         # 服务端判分
```

### 示例
`examples/platform_crowding.json` 为自编的 2 步小样例（站台拥挤疏导），仅用于演示格式。

### 限制
- 要点检查是子串匹配，不做语义理解、分词或语音识别，可能被堆砌关键词"刷分"；
- 只支持有向无环树/图，不支持循环重试类剧情；
- 示例内容为虚构教学样例，不构成任何真实作业规范或应急指引。

## English

**A zero-dependency engine for branching decision-tree drills: gold answers stay on the server, learners get a stripped view, and full answer paths are validated and scored with step-by-step review.**

### Background
Many vocational-training tasks are chains of decisions where each choice changes the next situation. Shipping answers to the client leaks them; clients can forge paths; hand-written trees often contain dangling links or cycles; and instructors want to check whether a learner can state key points in their own words.

### Approach
1. **Validation** – entry, unique option ids, legal `quality`, no dangling `next`; DFS cycle detection; unreachable-node warnings.
2. **Gold stripping** – `public_view()` removes `quality / next / feedback / tips / keywords / min_hits` and end verdicts.
3. **Step scoring** – quality → score (100/60/0); optional free-text key-point check (case-insensitive substring, synonym groups), blended 0.65/0.35 with a floor once the minimum hits are met.
4. **Path scoring** – strict mode requires every step to follow the previous option's `next`; returns average score, counts, verdict (`good/improve/fail/incomplete`) and review. All weights are overridable.

### Usage
See the commands above; `examples/demo.py` shows a full round trip.

### Limitations
Substring key-point matching only (no semantics, tokenization or speech); acyclic graphs only; sample content is fictional and not operational guidance.

## License
Apache-2.0
