"""
eval.py -- 电商客服系统评估

用法：python eval.py [--create-dataset-only] [--experiment v5]
"""

import os, sys, json, hashlib
from langsmith import Client, evaluate
from langsmith.schemas import Run, Example
from config import make_llm

llm = make_llm(temperature=0)
ls_client = Client()
DATASET_NAME = "ecommerce_cs_eval_v5"

# 真实测试账号
PHONE_ZHANGWEI = "13800001001"  # 张伟，有订单
PHONE_LINA    = "13800001002"  # 李娜，有订单
PHONE_NEW     = "13800001011"  # 新用户，无订单（不在 seed 里，测试未登录场景）

EVAL_EXAMPLES = [
    # ---- order (张伟，有订单) ----
    {"inputs":{"question":"帮我查一下我的订单"},"outputs":{"expected_intent":"order","expected_keywords":["订单"],"min_length":30,"max_length":800},"phone":PHONE_ZHANGWEI},
    {"inputs":{"question":"我的快递到哪了？帮我查查物流"},"outputs":{"expected_intent":"order","expected_keywords":["物流"],"min_length":20,"max_length":500},"phone":PHONE_ZHANGWEI},
    {"inputs":{"question":"我要修改收货地址"},"outputs":{"expected_intent":"order","expected_keywords":["地址"],"min_length":20,"max_length":500},"phone":PHONE_ZHANGWEI},
    {"inputs":{"question":"上周买的东西怎么还没送到？"},"outputs":{"expected_intent":"order","expected_keywords":["订单"],"min_length":20,"max_length":600},"phone":PHONE_ZHANGWEI},

    # ---- product ----
    {"inputs":{"question":"推荐一款降噪耳机"},"outputs":{"expected_intent":"product","expected_keywords":["耳机","降噪"],"min_length":30,"max_length":500},"phone":PHONE_ZHANGWEI},
    {"inputs":{"question":"iPhone 15 Pro Max 和华为 Mate 60 Pro 哪个更好？"},"outputs":{"expected_intent":"product","expected_keywords":["iPhone","华为"],"min_length":30,"max_length":500},"phone":PHONE_LINA},
    {"inputs":{"question":"有没有适合跑步穿的鞋子？"},"outputs":{"expected_intent":"product","expected_keywords":["跑鞋"],"min_length":20,"max_length":500},"phone":PHONE_LINA},
    {"inputs":{"question":"MacBook Pro 适合编程用吗？"},"outputs":{"expected_intent":"product","expected_keywords":["MacBook"],"min_length":20,"max_length":400},"phone":PHONE_LINA},
    {"inputs":{"question":"想买个扫地机器人，有什么推荐？"},"outputs":{"expected_intent":"product","expected_keywords":["扫地"],"min_length":30,"max_length":500},"phone":PHONE_LINA},
    {"inputs":{"question":"有没有适合露营的帐篷？"},"outputs":{"expected_intent":"product","expected_keywords":["帐篷"],"min_length":20,"max_length":400},"phone":PHONE_LINA},
    {"inputs":{"question":"我想买猫粮，有什么推荐？"},"outputs":{"expected_intent":"product","expected_keywords":["猫粮"],"min_length":30,"max_length":500},"phone":PHONE_LINA},
    {"inputs":{"question":"帮我查一下有没有卖空气净化器"},"outputs":{"expected_intent":"product","expected_keywords":["净化","空气"],"min_length":20,"max_length":400},"phone":PHONE_LINA},
    {"inputs":{"question":"过年给家人买礼物，预算2000有什么推荐？"},"outputs":{"expected_intent":"product","expected_keywords":["推荐"],"min_length":15,"max_length":500},"phone":PHONE_LINA},
    {"inputs":{"question":"茅台多少钱一瓶？"},"outputs":{"expected_intent":"product","expected_keywords":["茅台"],"min_length":15,"max_length":400},"phone":PHONE_LINA},
    {"inputs":{"question":"推荐一款保湿精华"},"outputs":{"expected_intent":"product","expected_keywords":["精华"],"min_length":20,"max_length":400},"phone":PHONE_LINA},

    # ---- aftersale (张伟，有订单) ----
    {"inputs":{"question":"我买的商品质量有问题，怎么退货？"},"outputs":{"expected_intent":"aftersale","expected_keywords":["退货"],"min_length":30,"max_length":600},"phone":PHONE_ZHANGWEI},
    {"inputs":{"question":"我要退货退款"},"outputs":{"expected_intent":"aftersale","expected_keywords":["退货"],"min_length":20,"max_length":500},"phone":PHONE_ZHANGWEI},
    {"inputs":{"question":"退款什么时候到账？"},"outputs":{"expected_intent":"aftersale","expected_keywords":["退款"],"min_length":20,"max_length":500},"phone":PHONE_LINA},
    {"inputs":{"question":"衣服尺码买小了，可以换大一号吗？"},"outputs":{"expected_intent":"aftersale","expected_keywords":["换货"],"min_length":20,"max_length":500},"phone":PHONE_ZHANGWEI},
    {"inputs":{"question":"收到的商品和描述不符，我要投诉！"},"outputs":{"expected_intent":"aftersale","expected_keywords":["投诉"],"min_length":20,"max_length":500},"phone":PHONE_ZHANGWEI},

    # ---- faq ----
    {"inputs":{"question":"你们支持哪些支付方式？可以用花呗吗？"},"outputs":{"expected_intent":"faq","expected_keywords":["支付","花呗"],"min_length":20,"max_length":500},"phone":PHONE_LINA},
    {"inputs":{"question":"会员积分怎么获取？"},"outputs":{"expected_intent":"faq","expected_keywords":["积分"],"min_length":20,"max_length":500},"phone":PHONE_LINA},
    {"inputs":{"question":"下单后几天能收到货？"},"outputs":{"expected_intent":"faq","expected_keywords":["配送","天"],"min_length":20,"max_length":400},"phone":PHONE_LINA},
    {"inputs":{"question":"企业采购有优惠吗？"},"outputs":{"expected_intent":"faq","expected_keywords":["企业"],"min_length":15,"max_length":400},"phone":PHONE_LINA},
    {"inputs":{"question":"你们的营业时间是？"},"outputs":{"expected_intent":"faq","expected_keywords":["时间"],"min_length":15,"max_length":400},"phone":PHONE_LINA},
    {"inputs":{"question":"你好"},"outputs":{"expected_intent":"faq","expected_keywords":[],"min_length":3,"max_length":300},"phone":PHONE_LINA},
    {"inputs":{"question":"谢谢你的帮助"},"outputs":{"expected_intent":"faq","expected_keywords":[],"min_length":3,"max_length":200},"phone":PHONE_LINA},
    {"inputs":{"question":"在吗？"},"outputs":{"expected_intent":"faq","expected_keywords":[],"min_length":3,"max_length":200},"phone":PHONE_LINA},

    # ---- human ----
    {"inputs":{"question":"转人工"},"outputs":{"expected_intent":"human","expected_keywords":["人工"],"min_length":10,"max_length":300},"phone":PHONE_LINA},
    {"inputs":{"question":"我要找人工客服"},"outputs":{"expected_intent":"human","expected_keywords":["人工"],"min_length":10,"max_length":300},"phone":PHONE_LINA},
]


def create_eval_dataset():
    existing = list(ls_client.list_datasets(dataset_name=DATASET_NAME))
    if existing:
        ds = existing[0]
        n = len(list(ls_client.list_examples(dataset_id=ds.id)))
        print(f"已有数据集：{DATASET_NAME}（{n} 条）")
        return ds
    dataset = ls_client.create_dataset(
        dataset_name=DATASET_NAME,
        description="v5 -- 真实phone，30条用例，不做记忆隔离",
    )
    ls_client.create_examples(
        inputs=[{"question": e["inputs"]["question"]} for e in EVAL_EXAMPLES],
        outputs=[e["outputs"] for e in EVAL_EXAMPLES],
        dataset_id=dataset.id,
    )
    print(f"已创建：{DATASET_NAME}，{len(EVAL_EXAMPLES)} 条")
    return dataset


def target_function(inputs: dict) -> dict:
    question = inputs["question"]
    from config import get_checkpointer
    from graph import build_csr_graph
    from langchain_core.messages import HumanMessage

    graph = build_csr_graph(checkpointer=get_checkpointer())

    # 找对应 phone
    phone = PHONE_LINA  # 默认
    for e in EVAL_EXAMPLES:
        if e["inputs"]["question"] == question:
            phone = e.get("phone", PHONE_LINA)
            break

    tid = f"eval_{hashlib.md5(question.encode()).hexdigest()[:12]}"
    config = {"configurable": {"thread_id": tid, "user_phone": phone}}

    try:
        result = graph.invoke(
            {"messages":[HumanMessage(content=question)],"intent":"","iteration_count":0,
             "next_agent":"","user_phone":phone,"summary":"","user_profile_json":"",
             "approval_decision":"","approval_meta":""},
            config=config,
        )
        answer = result["messages"][-1].content
        intent = result.get("intent", "unknown")
    except Exception as e:
        answer = f"ERROR: {e}"
        intent = "error"

    return {"answer": answer, "intent": intent}


# ---- 评估器 ----
def evaluate_intent(run: Run, example: Example) -> dict:
    e = (example.outputs or {}).get("expected_intent","")
    p = (run.outputs or {}).get("intent","")
    if not e: return {"key":"intent_accuracy","score":0.5,"comment":"无预期"}
    s = 1.0 if p==e else 0.0
    return {"key":"intent_accuracy","score":s,"comment":f"预期={e} 实际={p}"}

def evaluate_keywords(run: Run, example: Example) -> dict:
    a = ((run.outputs or {}).get("answer","")).lower()
    eks = (example.outputs or {}).get("expected_keywords",[])
    if not eks: return {"key":"keyword_coverage","score":1.0,"comment":"跳过"}
    m = [k for k in eks if k.lower() in a]
    return {"key":"keyword_coverage","score":round(len(m)/len(eks),2),"comment":f"{len(m)}/{len(eks)}"}

def evaluate_quality_llm(run: Run, example: Example) -> dict:
    a = (run.outputs or {}).get("answer","")
    q = (example.inputs or {}).get("question","")
    if not a or a.startswith("ERROR"): return {"key":"llm_quality","score":0.0,"comment":"空/错误"}
    p = f"评估客服回答质量(0-1)。问题:{q}\n回答:{a[:800]}\n只输出JSON:{{\"score\":0.0-1.0,\"reason\":\"理由\"}}"
    try:
        from langchain_core.messages import HumanMessage
        r = llm.invoke([HumanMessage(content=p)])
        c = r.content.strip()
        if "```" in c: c = c.split("```")[1].split("```")[0]
        if c.startswith("json"): c = c[4:]
        j = json.loads(c)
        return {"key":"llm_quality","score":round(max(0,min(1,float(j.get("score",0.7)))),2),"comment":j.get("reason","")}
    except: return {"key":"llm_quality","score":0.6,"comment":"解析异常"}

def evaluate_structure(run: Run, example: Example) -> dict:
    a = (run.outputs or {}).get("answer","")
    f = {"换行":a.count("\n")>=2,"序号":any(m in a for m in["1.","2.","一、"]),"加粗":"**"in a}
    m = sum(f.values())
    return {"key":"structure","score":0.8 if m>=2 else 0.5 if m>=1 else 0.2,"comment":f"{m}/3"}

def evaluate_length(run: Run, example: Example) -> dict:
    a = (run.outputs or {}).get("answer","")
    e = example.outputs or {}; mn,mx = e.get("min_length",10), e.get("max_length",600)
    al = len(a)
    if mn<=al<=mx: return {"key":"length","score":1.0,"comment":f"{al}字"}
    if al<mn: return {"key":"length","score":max(0.3,al/max(mn,1)),"comment":f"过短({al}字)"}
    return {"key":"length","score":max(0.5,mx/max(al,1)),"comment":f"偏长({al}字)"}


def run_evaluation(experiment_name: str = "ecommerce_cs_v5"):
    print("="*50+"\n电商客服评估 v5\n"+"="*50)
    ds = create_eval_dataset()
    evals = [evaluate_intent,evaluate_keywords,evaluate_quality_llm,evaluate_structure,evaluate_length]
    print(f"\n{experiment_name} | {len(EVAL_EXAMPLES)}条 | 评估中...\n")
    results = evaluate(target_function, data=DATASET_NAME, evaluators=evals,
                       experiment_prefix=experiment_name,
                       metadata={"system":"ecommerce_cs","version":"5.0","model":os.getenv("LLM_MODEL","qwen-plus")},
                       max_concurrency=1)
    rl = list(results)
    sbk = {}
    for r in rl:
        for fb in (r.get("feedback") or []): sbk.setdefault(fb.key,[]).append(fb.score or 0)
    print(f"\n{'='*50}\n{len(rl)}条完成\n{'='*50}")
    for k in sorted(sbk): print(f"  {k}: {sum(sbk[k])/len(sbk[k]):.2f} ({len(sbk[k])}条)")
    print(f"\n  综合: {sum(sum(s) for s in sbk.values())/sum(len(s) for s in sbk.values()):.2f}")
    return rl


if __name__ == "__main__":
    run_evaluation(experiment_name=sys.argv[1] if len(sys.argv)>1 else "ecommerce_cs_v5")
