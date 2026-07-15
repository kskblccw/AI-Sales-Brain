"""
eval.py — 电商客服系统 LangSmith 自动化评估

评估维度（5个）：
  1. 意图识别准确率 —— 匹配预期意图
  2. 关键词覆盖率 —— 参考答案核心要点是否覆盖
  3. LLM-as-Judge 质量分 —— AI 评判语义准确性、完整性、有用性
  4. 结构完整性 —— 是否使用标题/列表/分段等结构化格式
  5. 长度合理性 —— 是否在预期范围内

用法：
    python eval.py                          # 创建数据集 + 运行评估
    python eval.py --create-dataset-only    # 仅创建数据集
    python eval.py --experiment v2          # 指定实验名称
"""

import os
import sys
import json
from langsmith import Client, evaluate
from langsmith.schemas import Run, Example

from config import make_llm

llm = make_llm(temperature=0)
ls_client = Client()
DATASET_NAME = "ecommerce_cs_eval_v2"


# ═══════════════════════════════════════════════════════════════════════════════
# 评估数据集 (20条，5种意图各4条)
# ═══════════════════════════════════════════════════════════════════════════════
EVAL_EXAMPLES = [
    # ── 订单查询 (order) ──
    {
        "inputs": {"question": "帮我查一下订单 ORD202407140001 的物流情况"},
        "outputs": {
            "expected_intent": "order",
            "expected_keywords": ["物流", "订单"],
            "min_length": 30,
            "max_length": 400,
        },
    },
    {
        "inputs": {"question": "我的手机号 13800001001，帮我看看有哪些订单"},
        "outputs": {
            "expected_intent": "order",
            "expected_keywords": ["订单", "13800001001"],
            "min_length": 40,
            "max_length": 500,
        },
    },
    {
        "inputs": {"question": "我有一个快递单号，帮我查查到哪了"},
        "outputs": {
            "expected_intent": "order",
            "expected_keywords": ["快递", "物流", "订单"],
            "min_length": 30,
            "max_length": 400,
        },
    },
    {
        "inputs": {"question": "上周买的东西怎么还没送到？"},
        "outputs": {
            "expected_intent": "order",
            "expected_keywords": ["订单", "配送", "物流"],
            "min_length": 40,
            "max_length": 400,
        },
    },

    # ── 商品咨询 (product) ──
    {
        "inputs": {"question": "我想买一款降噪耳机，预算2000以内有什么推荐？"},
        "outputs": {
            "expected_intent": "product",
            "expected_keywords": ["耳机", "降噪", "价格", "元"],
            "min_length": 60,
            "max_length": 500,
        },
    },
    {
        "inputs": {"question": "iPhone 15 Pro Max 和华为 Mate 60 Pro 哪个更适合拍照？"},
        "outputs": {
            "expected_intent": "product",
            "expected_keywords": ["iPhone", "华为", "拍照", "摄像头"],
            "min_length": 80,
            "max_length": 600,
        },
    },
    {
        "inputs": {"question": "MacBook Pro 适合程序员用吗？有什么配置推荐？"},
        "outputs": {
            "expected_intent": "product",
            "expected_keywords": ["MacBook", "程序员", "配置", "内存"],
            "min_length": 60,
            "max_length": 500,
        },
    },
    {
        "inputs": {"question": "有没有适合跑步穿的鞋子？预算500以内"},
        "outputs": {
            "expected_intent": "product",
            "expected_keywords": ["跑鞋", "运动", "价格"],
            "min_length": 50,
            "max_length": 500,
        },
    },

    # ── 售后处理 (aftersale) ──
    {
        "inputs": {"question": "我买的商品质量有问题，怎么退货？"},
        "outputs": {
            "expected_intent": "aftersale",
            "expected_keywords": ["退货", "售后", "申请", "质量"],
            "min_length": 50,
            "max_length": 500,
        },
    },
    {
        "inputs": {"question": "衣服尺码买小了，可以换大一号吗？"},
        "outputs": {
            "expected_intent": "aftersale",
            "expected_keywords": ["换货", "尺码", "退货", "申请"],
            "min_length": 40,
            "max_length": 400,
        },
    },
    {
        "inputs": {"question": "我刚申请了退货，怎么退款还没到账？"},
        "outputs": {
            "expected_intent": "aftersale",
            "expected_keywords": ["退款", "退货", "到账"],
            "min_length": 30,
            "max_length": 400,
        },
    },
    {
        "inputs": {"question": "收到的商品和描述不符，我要投诉！"},
        "outputs": {
            "expected_intent": "aftersale",
            "expected_keywords": ["退货", "投诉", "退款", "售后"],
            "min_length": 40,
            "max_length": 500,
        },
    },

    # ── FAQ 常见问题 (faq) ──
    {
        "inputs": {"question": "你们支持哪些支付方式？可以用花呗吗？"},
        "outputs": {
            "expected_intent": "faq",
            "expected_keywords": ["支付宝", "微信", "花呗", "支付"],
            "min_length": 30,
            "max_length": 400,
        },
    },
    {
        "inputs": {"question": "会员积分怎么获取？有什么用处？"},
        "outputs": {
            "expected_intent": "faq",
            "expected_keywords": ["积分", "会员", "消费", "抵扣"],
            "min_length": 40,
            "max_length": 400,
        },
    },
    {
        "inputs": {"question": "下单后几天能收到货？我在北京"},
        "outputs": {
            "expected_intent": "faq",
            "expected_keywords": ["配送", "发货", "快递", "天"],
            "min_length": 30,
            "max_length": 400,
        },
    },
    {
        "inputs": {"question": "企业采购有优惠吗？我们公司想批量购买"},
        "outputs": {
            "expected_intent": "faq",
            "expected_keywords": ["企业", "团购", "优惠", "折扣"],
            "min_length": 40,
            "max_length": 400,
        },
    },

    # ── 混合/边界场景 ──
    {
        "inputs": {"question": "我上周下的单，商品有点小问题，不知道是退货好还是换货好"},
        "outputs": {
            "expected_intent": "aftersale",
            "expected_keywords": ["退货", "换货", "售后", "问题"],
            "min_length": 50,
            "max_length": 600,
        },
    },
    {
        "inputs": {"question": "马上过年了想给家人买点礼物，有什么推荐？预算2000"},
        "outputs": {
            "expected_intent": "product",
            "expected_keywords": ["推荐", "礼物", "价格"],
            "min_length": 60,
            "max_length": 500,
        },
    },
    {
        "inputs": {"question": "帮我看看最近有什么促销活动？"},
        "outputs": {
            "expected_intent": "faq",
            "expected_keywords": ["优惠", "促销", "活动", "折扣"],
            "min_length": 20,
            "max_length": 400,
        },
    },
    {
        "inputs": {"question": "你好"},
        "outputs": {
            "expected_intent": "faq",
            "expected_keywords": ["你好", "帮助", "客服"],
            "min_length": 10,
            "max_length": 300,
        },
    },
]


# ═══════════════════════════════════════════════════════════════════════════════
# 创建/获取数据集
# ═══════════════════════════════════════════════════════════════════════════════
def create_eval_dataset():
    existing = list(ls_client.list_datasets(dataset_name=DATASET_NAME))
    if existing:
        print(f"使用已有数据集：{DATASET_NAME}（{len(list(ls_client.list_examples(dataset_id=existing[0].id)))} 条）")
        return existing[0]

    dataset = ls_client.create_dataset(
        dataset_name=DATASET_NAME,
        description="电商智能客服系统评估数据集 v2 — 5种意图 × 4用例 + 4边界场景",
    )
    ls_client.create_examples(
        inputs=[e["inputs"] for e in EVAL_EXAMPLES],
        outputs=[e["outputs"] for e in EVAL_EXAMPLES],
        dataset_id=dataset.id,
    )
    print(f"创建数据集：{DATASET_NAME}，{len(EVAL_EXAMPLES)} 条用例")
    return dataset


# ═══════════════════════════════════════════════════════════════════════════════
# 目标函数（被评估系统）
# ═══════════════════════════════════════════════════════════════════════════════
def target_function(inputs: dict) -> dict:
    """调用客服系统，返回回答"""
    question = inputs["question"]
    from config import get_checkpointer
    from graph import build_csr_graph
    from langchain_core.messages import HumanMessage

    graph = build_csr_graph(checkpointer=get_checkpointer())
    # 评估用固定测试账号（张伟，有15+笔订单）
    eval_phone = "13800001001"
    config = {"configurable": {"thread_id": f"eval_{hash(question) % 100000}", "user_phone": eval_phone}}

    try:
        result = graph.invoke(
            {
                "messages": [HumanMessage(content=question)],
                "intent": "", "iteration_count": 0, "next_agent": "",
                "user_phone": eval_phone,
            },
            config=config,
        )
        answer = result["messages"][-1].content
        # 顺便获取意图
        intent = result.get("intent", "unknown")
    except Exception as e:
        answer = f"ERROR: {e}"
        intent = "error"

    return {"answer": answer, "intent": intent}


# ═══════════════════════════════════════════════════════════════════════════════
# 评估器 1: 意图识别准确率
# ═══════════════════════════════════════════════════════════════════════════════
def evaluate_intent(run: Run, example: Example) -> dict:
    """判断系统识别的意图是否与预期一致"""
    expected = (example.outputs or {}).get("expected_intent", "")
    predicted = (run.outputs or {}).get("intent", "")

    if not expected:
        return {"key": "intent_accuracy", "score": 0.5, "comment": "无预期意图标注"}

    score = 1.0 if predicted == expected else 0.0
    comment = f"预期={expected} 实际={predicted}" + (" 匹配" if score else " 不匹配")
    return {"key": "intent_accuracy", "score": score, "comment": comment}


# ═══════════════════════════════════════════════════════════════════════════════
# 评估器 2: 关键词覆盖率
# ═══════════════════════════════════════════════════════════════════════════════
def evaluate_keywords(run: Run, example: Example) -> dict:
    """检查回答是否包含了参考答案中的关键信息"""
    answer = ((run.outputs or {}).get("answer", "")).lower()
    expected_keywords = (example.outputs or {}).get("expected_keywords", [])

    if not expected_keywords:
        return {"key": "keyword_coverage", "score": 0.5, "comment": "无预期关键词"}

    matched = [kw for kw in expected_keywords if kw.lower() in answer]
    coverage = len(matched) / len(expected_keywords)

    return {
        "key": "keyword_coverage",
        "score": round(coverage, 2),
        "comment": f"覆盖 {len(matched)}/{len(expected_keywords)}：{', '.join(matched) if matched else '无'}",
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 评估器 3: LLM-as-Judge 综合质量评分（最核心）
# ═══════════════════════════════════════════════════════════════════════════════
def evaluate_quality_llm(run: Run, example: Example) -> dict:
    """用 LLM 评判回答的综合质量（准确性、完整性、有用性、友好度）"""
    answer = (run.outputs or {}).get("answer", "")
    question = (example.inputs or {}).get("question", "")

    if not answer or answer.startswith("ERROR"):
        return {"key": "llm_quality", "score": 0.0, "comment": "回答为空或系统错误"}

    # 截断长回答避免超出 token 限制
    truncated = answer if len(answer) <= 1200 else answer[:1200] + "..."

    prompt = f"""你是电商客服质量评审专家。请从以下5个维度评估客服回答的质量，
每个维度打分（0或1），最后给出综合分数（0-1之间，可以是小数）：

维度1 - 准确性(0/1)：回答的事实是否正确、是否与问题相关
维度2 - 完整性(0/1)：是否覆盖了用户问题的核心要点
维度3 - 有用性(0/1)：是否提供了可操作的具体建议或信息
维度4 - 友好度(0/1)：语气是否礼貌、热情、专业
维度5 - 简洁性(0/1)：是否简明扼要、不啰嗦

用户问题：{question}

客服回答：
{truncated}

请按以下格式输出（只输出最终的JSON）：
{{"accuracy": 0或1, "completeness": 0或1, "helpfulness": 0或1, "politeness": 0或1, "conciseness": 0或1, "total": 综合分0到1}}"""

    try:
        from langchain_core.messages import HumanMessage
        response = llm.invoke([HumanMessage(content=prompt)])
        content = response.content.strip()

        # 提取 JSON（容错处理）
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]

        result = json.loads(content)
        total = float(result.get("total", 0.5))
        total = max(0.0, min(1.0, total))

        # 格式化评论：显示各维度得分
        dims = ["accuracy", "completeness", "helpfulness", "politeness", "conciseness"]
        dim_str = " ".join(f"{d}={result.get(d, '?')}" for d in dims)

        return {
            "key": "llm_quality",
            "score": round(total, 2),
            "comment": f"综合={total:.2f} | {dim_str}",
        }
    except Exception as e:
        return {"key": "llm_quality", "score": 0.5, "comment": f"评分解析失败: {e}"}


# ═══════════════════════════════════════════════════════════════════════════════
# 评估器 4: 结构完整性
# ═══════════════════════════════════════════════════════════════════════════════
def evaluate_structure(run: Run, example: Example) -> dict:
    """检查回答是否有清晰的结构（标题、列表、分段等）"""
    answer = (run.outputs or {}).get("answer", "")

    # 结构化特征检测
    features = {
        "标题(#)": "#" in answer,
        "数字列表(1.)": any(f"{i}." in answer for i in range(1, 10)),
        "中文序号": any(marker in answer for marker in ["一、", "二、", "三、"]),
        "项目符号(-)": "\n-" in answer or "\n-" in answer,
        "分段空行": "\n\n" in answer,
        "加粗(**)": "**" in answer,
    }

    matched = sum(1 for v in features.values() if v)
    total_features = len(features)

    # 有2个及以上结构化特征则是良好结构
    if matched >= 4:
        score = 1.0
    elif matched >= 2:
        score = 0.7
    elif matched >= 1:
        score = 0.4
    else:
        score = 0.1

    matched_names = [k for k, v in features.items() if v]
    return {
        "key": "structure",
        "score": score,
        "comment": f"{matched}/{total_features} 结构化特征：{', '.join(matched_names) if matched_names else '无'}",
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 评估器 5: 长度合理性
# ═══════════════════════════════════════════════════════════════════════════════
def evaluate_length(run: Run, example: Example) -> dict:
    """检查回答长度是否在预期范围内"""
    answer = (run.outputs or {}).get("answer", "")
    expected = example.outputs or {}
    min_len = expected.get("min_length", 20)
    max_len = expected.get("max_length", 600)
    actual_len = len(answer)

    if min_len <= actual_len <= max_len:
        score = 1.0
        comment = f"长度适中（{actual_len}字，预期 {min_len}-{max_len}）"
    elif actual_len < min_len:
        score = max(0.1, actual_len / max(min_len, 1))
        comment = f"回答过短（{actual_len}字，预期 ≥{min_len}）"
    else:
        # 偏长但可能有价值，宽松扣分
        score = 0.7
        comment = f"回答偏长（{actual_len}字，预期 ≤{max_len}）"

    return {"key": "length", "score": round(score, 2), "comment": comment}


# ═══════════════════════════════════════════════════════════════════════════════
# 运行评估
# ═══════════════════════════════════════════════════════════════════════════════
def run_evaluation(experiment_name: str = "ecommerce_cs_v2"):
    print("=" * 60)
    print("电商智能客服系统 — 自动化评估")
    print("=" * 60)

    dataset = create_eval_dataset()

    evaluators = [
        evaluate_intent,
        evaluate_keywords,
        evaluate_quality_llm,
        evaluate_structure,
        evaluate_length,
    ]

    print(f"\n实验名称：{experiment_name}")
    print(f"评估器：意图准确率 | 关键词覆盖 | LLM综合质量 | 结构完整性 | 长度合理性")
    print(f"用例数：{len(EVAL_EXAMPLES)} 条\n")

    results = evaluate(
        target_function,
        data=DATASET_NAME,
        evaluators=evaluators,
        experiment_prefix=experiment_name,
        metadata={
            "system": "ecommerce_cs",
            "version": "2.0",
            "model": os.getenv("LLM_MODEL", "qwen-plus"),
        },
        max_concurrency=1,
    )

    result_list = list(results)

    # ── 本地汇总 ──
    print(f"\n{'='*60}")
    print(f"评估完成！共 {len(result_list)} 条用例")
    print(f"{'='*60}")

    # 按评估器统计均分
    scores_by_key = {}
    for r in result_list:
        for fb in (r.get("feedback") or []):
            scores_by_key.setdefault(fb.key, []).append(fb.score or 0)

    print("\n评估器均分：")
    for key, scores in sorted(scores_by_key.items()):
        avg = sum(scores) / len(scores)
        print(f"  {key}: {avg:.2f} ({len(scores)}条)")

    print(f"\n查看详细结果：https://smith.langchain.com")
    print(f"项目：{os.getenv('LANGCHAIN_PROJECT', 'ecommerce_cs')}")
    return result_list


if __name__ == "__main__":
    experiment = sys.argv[1] if len(sys.argv) > 1 else "ecommerce_cs_v2"
    run_evaluation(experiment_name=experiment)
