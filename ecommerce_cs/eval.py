"""
eval.py -- 电商客服系统 LangSmith 自动化评估

评估维度（5个）：
  1. 意图识别准确率 -- 匹配预期意图
  2. 关键词覆盖率 -- 参考答案核心要点是否覆盖
  3. LLM-as-Judge 质量分 -- AI 评判语义准确性、完整性、有用性
  4. 结构完整性 -- 是否使用换行/分段等结构化格式
  5. 长度合理性 -- 是否在预期范围内

用法：
    python eval.py                          # 创建数据集 + 运行评估
    python eval.py --create-dataset-only    # 仅创建数据集
    python eval.py --experiment v3          # 指定实验名称
"""

import os
import sys
import json
from langsmith import Client, evaluate
from langsmith.schemas import Run, Example

from config import make_llm

llm = make_llm(temperature=0)
ls_client = Client()
DATASET_NAME = "ecommerce_cs_eval_v3"


# ============================================================
# 评估数据集 (30条，覆盖全品类 + 新功能)
# ============================================================
EVAL_EXAMPLES = [
    # ---- 订单查询 (order) ----
    {
        "inputs": {"question": "帮我查一下我的订单"},
        "outputs": {
            "expected_intent": "order",
            "expected_keywords": ["订单"],
            "min_length": 30, "max_length": 800,
        },
    },
    {
        "inputs": {"question": "我的快递到哪了？帮我查查物流"},
        "outputs": {
            "expected_intent": "order",
            "expected_keywords": ["物流", "快递"],
            "min_length": 30, "max_length": 600,
        },
    },
    {
        "inputs": {"question": "上周买的东西怎么还没送到？"},
        "outputs": {
            "expected_intent": "order",
            "expected_keywords": ["订单"],
            "min_length": 40, "max_length": 600,
        },
    },
    {
        "inputs": {"question": "我要修改收货地址"},
        "outputs": {
            "expected_intent": "order",
            "expected_keywords": ["地址"],
            "min_length": 20, "max_length": 500,
        },
    },

    # ---- 商品咨询 (product) ----
    {
        "inputs": {"question": "推荐一款降噪耳机"},
        "outputs": {
            "expected_intent": "product",
            "expected_keywords": ["耳机", "降噪"],
            "min_length": 40, "max_length": 600,
        },
    },
    {
        "inputs": {"question": "iPhone 15 Pro Max 和华为 Mate 60 Pro 哪个更好？"},
        "outputs": {
            "expected_intent": "product",
            "expected_keywords": ["iPhone", "华为"],
            "min_length": 40, "max_length": 600,
        },
    },
    {
        "inputs": {"question": "有没有适合跑步穿的鞋子？预算500左右"},
        "outputs": {
            "expected_intent": "product",
            "expected_keywords": ["跑鞋", "鞋"],
            "min_length": 40, "max_length": 600,
        },
    },
    {
        "inputs": {"question": "MacBook Pro 适合编程用吗？"},
        "outputs": {
            "expected_intent": "product",
            "expected_keywords": ["MacBook"],
            "min_length": 30, "max_length": 500,
        },
    },
    {
        "inputs": {"question": "想买个扫地机器人，有什么好的推荐？"},
        "outputs": {
            "expected_intent": "product",
            "expected_keywords": ["扫地"],
            "min_length": 40, "max_length": 600,
        },
    },
    {
        "inputs": {"question": "过年给家人买礼物，预算2000有什么推荐？"},
        "outputs": {
            "expected_intent": "product",
            "expected_keywords": ["推荐"],
            "min_length": 40, "max_length": 600,
        },
    },

    # ---- 售后处理 (aftersale) ----
    {
        "inputs": {"question": "我买的商品质量有问题，怎么退货？"},
        "outputs": {
            "expected_intent": "aftersale",
            "expected_keywords": ["退货", "售后"],
            "min_length": 40, "max_length": 600,
        },
    },
    {
        "inputs": {"question": "衣服尺码买小了，可以换大一号吗？"},
        "outputs": {
            "expected_intent": "aftersale",
            "expected_keywords": ["换货"],
            "min_length": 30, "max_length": 500,
        },
    },
    {
        "inputs": {"question": "退款什么时候到账？"},
        "outputs": {
            "expected_intent": "aftersale",
            "expected_keywords": ["退款"],
            "min_length": 20, "max_length": 500,
        },
    },
    {
        "inputs": {"question": "收到的商品和描述不符，我要投诉！"},
        "outputs": {
            "expected_intent": "aftersale",
            "expected_keywords": ["售后", "投诉"],
            "min_length": 30, "max_length": 500,
        },
    },
    {
        "inputs": {"question": "我要退货退款"},
        "outputs": {
            "expected_intent": "aftersale",
            "expected_keywords": ["退货", "退款"],
            "min_length": 30, "max_length": 600,
        },
    },

    # ---- FAQ 常见问题 (faq) ----
    {
        "inputs": {"question": "你们支持哪些支付方式？可以用花呗吗？"},
        "outputs": {
            "expected_intent": "faq",
            "expected_keywords": ["支付", "花呗"],
            "min_length": 30, "max_length": 500,
        },
    },
    {
        "inputs": {"question": "会员积分怎么获取？"},
        "outputs": {
            "expected_intent": "faq",
            "expected_keywords": ["积分", "会员"],
            "min_length": 30, "max_length": 500,
        },
    },
    {
        "inputs": {"question": "下单后几天能收到货？"},
        "outputs": {
            "expected_intent": "faq",
            "expected_keywords": ["配送", "发货"],
            "min_length": 30, "max_length": 500,
        },
    },
    {
        "inputs": {"question": "企业采购有优惠吗？"},
        "outputs": {
            "expected_intent": "faq",
            "expected_keywords": ["企业", "优惠"],
            "min_length": 20, "max_length": 400,
        },
    },
    {
        "inputs": {"question": "你们的营业时间是？"},
        "outputs": {
            "expected_intent": "faq",
            "expected_keywords": ["客服", "时间"],
            "min_length": 15, "max_length": 400,
        },
    },

    # ---- 转人工 (human) ----
    {
        "inputs": {"question": "转人工"},
        "outputs": {
            "expected_intent": "human",
            "expected_keywords": ["人工", "客服"],
            "min_length": 15, "max_length": 300,
        },
    },
    {
        "inputs": {"question": "我要找人工客服"},
        "outputs": {
            "expected_intent": "human",
            "expected_keywords": ["人工", "客服"],
            "min_length": 15, "max_length": 300,
        },
    },

    # ---- 新品类覆盖 ----
    {
        "inputs": {"question": "推荐一款保湿精华液"},
        "outputs": {
            "expected_intent": "product",
            "expected_keywords": ["精华"],
            "min_length": 30, "max_length": 500,
        },
    },
    {
        "inputs": {"question": "有没有适合露营的帐篷？"},
        "outputs": {
            "expected_intent": "product",
            "expected_keywords": ["帐篷"],
            "min_length": 30, "max_length": 500,
        },
    },
    {
        "inputs": {"question": "我想买猫粮，有什么推荐？"},
        "outputs": {
            "expected_intent": "product",
            "expected_keywords": ["猫粮"],
            "min_length": 30, "max_length": 500,
        },
    },
    {
        "inputs": {"question": "茅台多少钱一瓶？"},
        "outputs": {
            "expected_intent": "product",
            "expected_keywords": ["茅台"],
            "min_length": 20, "max_length": 400,
        },
    },

    # ---- 寒暄 / 边界 ----
    {
        "inputs": {"question": "你好"},
        "outputs": {
            "expected_intent": "faq",
            "expected_keywords": [],
            "min_length": 5, "max_length": 300,
        },
    },
    {
        "inputs": {"question": "在吗？"},
        "outputs": {
            "expected_intent": "faq",
            "expected_keywords": [],
            "min_length": 5, "max_length": 200,
        },
    },
    {
        "inputs": {"question": "谢谢你的帮助"},
        "outputs": {
            "expected_intent": "faq",
            "expected_keywords": [],
            "min_length": 5, "max_length": 200,
        },
    },
    {
        "inputs": {"question": "帮我查一下有没有卖空气净化器"},
        "outputs": {
            "expected_intent": "product",
            "expected_keywords": ["净化"],
            "min_length": 30, "max_length": 500,
        },
    },
]


# ============================================================
# 创建/获取数据集
# ============================================================
def create_eval_dataset():
    existing = list(ls_client.list_datasets(dataset_name=DATASET_NAME))
    if existing:
        ds = existing[0]
        examples = list(ls_client.list_examples(dataset_id=ds.id))
        print(f"使用已有数据集：{DATASET_NAME}（{len(examples)} 条）")
        return ds

    dataset = ls_client.create_dataset(
        dataset_name=DATASET_NAME,
        description="电商智能客服系统评估数据集 v3 -- 30条用例，覆盖全品类+转人工+寒暄",
    )
    ls_client.create_examples(
        inputs=[e["inputs"] for e in EVAL_EXAMPLES],
        outputs=[e["outputs"] for e in EVAL_EXAMPLES],
        dataset_id=dataset.id,
    )
    print(f"已创建数据集：{DATASET_NAME}，{len(EVAL_EXAMPLES)} 条用例")
    return dataset


# ============================================================
# 目标函数
# ============================================================
def target_function(inputs: dict) -> dict:
    question = inputs["question"]
    from config import get_checkpointer
    from graph import build_csr_graph
    from langchain_core.messages import HumanMessage

    graph = build_csr_graph(checkpointer=get_checkpointer())
    eval_phone = "13800001001"

    import hashlib
    tid = f"eval_{hashlib.md5(question.encode()).hexdigest()[:12]}"
    config = {"configurable": {"thread_id": tid, "user_phone": eval_phone}}

    try:
        result = graph.invoke(
            {
                "messages": [HumanMessage(content=question)],
                "intent": "", "iteration_count": 0, "next_agent": "",
                "user_phone": eval_phone, "summary": "", "user_profile_json": "",
                "approval_decision": "", "approval_meta": "",
            },
            config=config,
        )
        answer = result["messages"][-1].content
        intent = result.get("intent", "unknown")
    except Exception as e:
        answer = f"ERROR: {e}"
        intent = "error"

    return {"answer": answer, "intent": intent}


# ============================================================
# 评估器 1: 意图识别准确率
# ============================================================
def evaluate_intent(run: Run, example: Example) -> dict:
    expected = (example.outputs or {}).get("expected_intent", "")
    predicted = (run.outputs or {}).get("intent", "")

    if not expected:
        return {"key": "intent_accuracy", "score": 0.5, "comment": "无预期意图"}

    score = 1.0 if predicted == expected else 0.0
    comment = f"预期={expected} 实际={predicted}" + (" 匹配" if score else " 不匹配")
    return {"key": "intent_accuracy", "score": score, "comment": comment}


# ============================================================
# 评估器 2: 关键词覆盖率
# ============================================================
def evaluate_keywords(run: Run, example: Example) -> dict:
    answer = ((run.outputs or {}).get("answer", "")).lower()
    expected_keywords = (example.outputs or {}).get("expected_keywords", [])

    if not expected_keywords:
        return {"key": "keyword_coverage", "score": 1.0, "comment": "无预期关键词（跳过）"}

    matched = [kw for kw in expected_keywords if kw.lower() in answer]
    coverage = len(matched) / len(expected_keywords)

    return {
        "key": "keyword_coverage",
        "score": round(coverage, 2),
        "comment": f"覆盖 {len(matched)}/{len(expected_keywords)}",
    }


# ============================================================
# 评估器 3: LLM-as-Judge 综合质量评分
# ============================================================
def evaluate_quality_llm(run: Run, example: Example) -> dict:
    answer = (run.outputs or {}).get("answer", "")
    question = (example.inputs or {}).get("question", "")

    if not answer or answer.startswith("ERROR"):
        return {"key": "llm_quality", "score": 0.0, "comment": "回答为空或系统错误"}

    truncated = answer if len(answer) <= 1000 else answer[:1000] + "..."

    prompt = f"""你是电商客服质量评审专家。请评估以下客服回答的质量。
从准确性、完整性、有用性三个维度评估，综合给分（0-1）。

用户问题：{question}

客服回答：
{truncated}

只输出一个 JSON：{{"score": 0.0到1.0之间, "reason": "简短理由"}}"""

    try:
        from langchain_core.messages import HumanMessage
        response = llm.invoke([HumanMessage(content=prompt)])
        content = response.content.strip()

        if "```" in content:
            content = content.split("```")[1].split("```")[0]
            if content.startswith("json"):
                content = content[4:]

        result = json.loads(content)
        score = float(result.get("score", 0.7))
        score = max(0.0, min(1.0, score))
        reason = result.get("reason", "")

        return {
            "key": "llm_quality",
            "score": round(score, 2),
            "comment": reason or f"综合分={score:.2f}",
        }
    except Exception as e:
        return {"key": "llm_quality", "score": 0.6, "comment": f"评分解析异常: {e}"}


# ============================================================
# 评估器 4: 结构完整性
# ============================================================
def evaluate_structure(run: Run, example: Example) -> dict:
    answer = (run.outputs or {}).get("answer", "")

    features = {
        "换行分段": answer.count("\n") >= 2,
        "数字列表": any(f"\n{i}" in answer or f"\n{i}." in answer for i in range(1, 6)),
        "中文序号": any(m in answer for m in ["一、", "二、", "1.", "2."]),
        "要点符号": "- " in answer or "  - " in answer,
        "加粗标记": "**" in answer,
    }

    matched = sum(1 for v in features.values() if v)

    if matched >= 3:
        score = 1.0
    elif matched >= 2:
        score = 0.8
    elif matched >= 1:
        score = 0.5
    else:
        score = 0.2

    return {
        "key": "structure",
        "score": score,
        "comment": f"{matched}/{len(features)} 结构化特征",
    }


# ============================================================
# 评估器 5: 长度合理性
# ============================================================
def evaluate_length(run: Run, example: Example) -> dict:
    answer = (run.outputs or {}).get("answer", "")
    expected = example.outputs or {}
    min_len = expected.get("min_length", 10)
    max_len = expected.get("max_length", 600)
    actual_len = len(answer)

    if min_len <= actual_len <= max_len:
        score = 1.0
        comment = f"适中（{actual_len}字）"
    elif actual_len < min_len:
        score = max(0.3, actual_len / max(min_len, 1))
        comment = f"过短（{actual_len}字，预期>={min_len}）"
    else:
        ratio = max_len / max(actual_len, 1)
        score = max(0.5, ratio)
        comment = f"偏长（{actual_len}字，预期<={max_len}）"

    return {"key": "length", "score": round(score, 2), "comment": comment}


# ============================================================
# 运行评估
# ============================================================
def run_evaluation(experiment_name: str = "ecommerce_cs_v3"):
    print("=" * 60)
    print("电商智能客服系统 -- 自动化评估")
    print("=" * 60)

    dataset = create_eval_dataset()

    evaluators = [
        evaluate_intent,
        evaluate_keywords,
        evaluate_quality_llm,
        evaluate_structure,
        evaluate_length,
    ]

    print(f"\n实验：{experiment_name}")
    print(f"用例：{len(EVAL_EXAMPLES)} 条")
    print(f"评估器：意图准确率 | 关键词覆盖 | LLM质量 | 结构完整 | 长度合理\n")

    results = evaluate(
        target_function,
        data=DATASET_NAME,
        evaluators=evaluators,
        experiment_prefix=experiment_name,
        metadata={
            "system": "ecommerce_cs",
            "version": "3.0",
            "model": os.getenv("LLM_MODEL", "qwen-plus"),
            "products": 200,
            "categories": 18,
        },
        max_concurrency=1,
    )

    result_list = list(results)

    print(f"\n{'='*60}")
    print(f"评估完成：{len(result_list)} 条用例")
    print(f"{'='*60}")

    scores_by_key = {}
    for r in result_list:
        for fb in (r.get("feedback") or []):
            scores_by_key.setdefault(fb.key, []).append(fb.score or 0)

    print("\n评估器均分：")
    for key, scores in sorted(scores_by_key.items()):
        avg = sum(scores) / len(scores)
        print(f"  {key}: {avg:.2f} ({len(scores)}条)")

    overall = sum(sum(s) for s in scores_by_key.values()) / sum(len(s) for s in scores_by_key.values())
    print(f"\n  综合均分: {overall:.2f}")

    print(f"\n详细结果：https://smith.langchain.com")
    return result_list


if __name__ == "__main__":
    experiment = sys.argv[1] if len(sys.argv) > 1 else "ecommerce_cs_v3"
    run_evaluation(experiment_name=experiment)
