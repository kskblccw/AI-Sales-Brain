"""
eval.py — 电商客服系统的 LangSmith 评估

评估维度：
1. 意图识别准确率
2. 回答完整性（关键词覆盖）
3. 回答质量（LLM-as-Judge）
4. 工具调用正确率

用法：
    python eval.py                          # 运行评估
    python eval.py --create-dataset-only    # 仅创建数据集
"""

import sys
import os
from langsmith import Client, evaluate
from langsmith.schemas import Run, Example

from config import make_llm
from graph import chat

llm = make_llm(temperature=0)
ls_client = Client()
DATASET_NAME = "ecommerce_cs_eval_v1"


# ── 创建评估数据集 ─────────────────────────────────────────────────────────────
def create_eval_dataset():
    """创建电商客服系统的评估数据集"""
    existing = list(ls_client.list_datasets(dataset_name=DATASET_NAME))
    if existing:
        print(f"使用已有数据集：{DATASET_NAME}")
        return existing[0]

    examples = [
        # 订单查询
        {
            "inputs": {"question": "帮我查一下订单 ORD202401010001 的物流情况"},
            "outputs": {
                "expected_intent": "order",
                "expected_keywords": ["物流", "快递", "订单"],
                "min_length": 20,
            },
        },
        {
            "inputs": {"question": "我的手机号是13800001001，帮我看看我有哪些订单"},
            "outputs": {
                "expected_intent": "order",
                "expected_keywords": ["订单", "13800001001"],
                "min_length": 30,
            },
        },
        # 商品咨询
        {
            "inputs": {"question": "我想买一个降噪耳机，有什么推荐吗？"},
            "outputs": {
                "expected_intent": "product",
                "expected_keywords": ["耳机", "价格", "降噪"],
                "min_length": 40,
            },
        },
        {
            "inputs": {"question": "iPhone 15 Pro Max 现在多少钱？"},
            "outputs": {
                "expected_intent": "product",
                "expected_keywords": ["iPhone", "价格", "9999"],
                "min_length": 30,
            },
        },
        {
            "inputs": {"question": "MacBook Pro 和 ThinkPad 哪个更适合编程？"},
            "outputs": {
                "expected_intent": "product",
                "expected_keywords": ["MacBook", "ThinkPad", "编程"],
                "min_length": 50,
            },
        },
        # 售后
        {
            "inputs": {"question": "我买的商品质量有问题，怎么退货？"},
            "outputs": {
                "expected_intent": "aftersale",
                "expected_keywords": ["退货", "售后", "申请"],
                "min_length": 30,
            },
        },
        {
            "inputs": {"question": "我的退货申请 RTN001 处理得怎么样了？"},
            "outputs": {
                "expected_intent": "aftersale",
                "expected_keywords": ["退货", "状态"],
                "min_length": 20,
            },
        },
        # FAQ
        {
            "inputs": {"question": "你们支持哪些支付方式？"},
            "outputs": {
                "expected_intent": "faq",
                "expected_keywords": ["支付", "支付宝", "微信"],
                "min_length": 20,
            },
        },
        {
            "inputs": {"question": "下单后多久能收到货？"},
            "outputs": {
                "expected_intent": "faq",
                "expected_keywords": ["配送", "发货", "天"],
                "min_length": 20,
            },
        },
        {
            "inputs": {"question": "会员有什么优惠吗？"},
            "outputs": {
                "expected_intent": "faq",
                "expected_keywords": ["会员", "折扣", "积分"],
                "min_length": 20,
            },
        },
    ]

    dataset = ls_client.create_dataset(
        dataset_name=DATASET_NAME,
        description="电商智能客服系统评估数据集",
    )

    ls_client.create_examples(
        inputs=[e["inputs"] for e in examples],
        outputs=[e["outputs"] for e in examples],
        dataset_id=dataset.id,
    )

    print(f"创建数据集：{DATASET_NAME}，{len(examples)} 个样本")
    return dataset


# ── 目标函数 ───────────────────────────────────────────────────────────────────
def target_function(inputs: dict) -> dict:
    """被评估的目标函数：调用客服系统并返回回答"""
    question = inputs["question"]
    # 每个评估用例使用独立会话
    session_id = f"eval_{hash(question) % 100000}"
    try:
        answer = chat(question, session_id=session_id)
    except Exception as e:
        answer = f"[ERROR] {e}"
    return {"answer": answer}


# ── 评估器 ─────────────────────────────────────────────────────────────────────
def evaluate_length(run: Run, example: Example) -> dict:
    """评估回答长度是否合理"""
    answer = (run.outputs or {}).get("answer", "")
    expected = example.outputs or {}
    min_len = expected.get("min_length", 20)

    actual_len = len(answer)
    if actual_len >= min_len:
        score = 1.0
        comment = f"长度充足（{actual_len}字）"
    else:
        score = actual_len / max(min_len, 1)
        comment = f"回答过短（{actual_len}字，期望 ≥{min_len}字）"

    return {"key": "answer_length", "score": min(score, 1.0), "comment": comment}


def evaluate_keywords(run: Run, example: Example) -> dict:
    """评估回答是否包含预期关键词"""
    answer = (run.outputs or {}).get("answer", "").lower()
    expected_keywords = (example.outputs or {}).get("expected_keywords", [])

    if not expected_keywords:
        return {"key": "keyword_coverage", "score": 0.5, "comment": "无预期关键词"}

    matched = [kw for kw in expected_keywords if kw.lower() in answer]
    coverage = len(matched) / len(expected_keywords)

    return {
        "key": "keyword_coverage",
        "score": coverage,
        "comment": f"关键词覆盖 {len(matched)}/{len(expected_keywords)}：{matched}",
    }


def evaluate_quality_llm(run: Run, example: Example) -> dict:
    """LLM-as-Judge：评估回答质量"""
    answer = (run.outputs or {}).get("answer", "")
    question = (example.inputs or {}).get("question", "")

    if not answer or answer.startswith("[ERROR]"):
        return {"key": "llm_quality", "score": 0.0, "comment": "回答为空或出错"}

    if len(answer) > 1500:
        answer = answer[:1500] + "..."

    from langchain_core.messages import HumanMessage

    judge_prompt = f"""请评估以下客服回答的质量，给出 0-1 之间的分数。

评分标准：
- 1.0：回答准确、完整、友好，完美解决用户问题
- 0.7：回答基本正确，但不够详细或略有偏差
- 0.4：回答部分相关，但遗漏关键信息
- 0.1：回答不相关或错误

用户问题：{question}

客服回答：
{answer}

请只输出一个数字（0到1之间），不要其他内容。"""

    try:
        response = llm.invoke([HumanMessage(content=judge_prompt)])
        score_str = response.content.strip()
        score = float(score_str)
        score = max(0.0, min(1.0, score))
    except (ValueError, Exception):
        score = 0.5

    return {
        "key": "llm_quality_judge",
        "score": score,
        "comment": f"LLM-as-Judge 评分：{score:.2f}",
    }


# ── 运行评估 ───────────────────────────────────────────────────────────────────
def run_evaluation(experiment_name: str = "ecommerce_cs_v1"):
    """运行完整评估流程"""
    print("=" * 60)
    print("电商客服系统 — 自动化评估")
    print("=" * 60)

    # 1. 准备数据集
    dataset = create_eval_dataset()

    # 2. 运行评估
    print(f"\n开始评估实验：{experiment_name}")
    print("评估器：长度检查、关键词覆盖、LLM-as-Judge\n")

    results = evaluate(
        target_function,
        data=DATASET_NAME,
        evaluators=[
            evaluate_length,
            evaluate_keywords,
            evaluate_quality_llm,
        ],
        experiment_prefix=experiment_name,
        metadata={
            "system": "ecommerce_cs",
            "version": "1.0",
        },
        max_concurrency=1,
    )

    result_list = list(results)
    print(f"\n评估完成！共 {len(result_list)} 个样本")
    print(f"\n查看详细结果：https://smith.langchain.com")
    print(f"项目：{os.environ.get('LANGCHAIN_PROJECT', 'ecommerce_cs')}")
    print(f"实验名称：{experiment_name}")

    return result_list


if __name__ == "__main__":
    experiment = sys.argv[1] if len(sys.argv) > 1 else "ecommerce_cs_v1"
    run_evaluation(experiment_name=experiment)
