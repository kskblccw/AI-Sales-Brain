# 电商客服系统 -- MCP 功能设计方案

## 一、为什么加 MCP？

当前系统的局限性：

| 现状 | 痛点 | MCP 能做什么 |
|------|------|-------------|
| 物流信息用 `random.randint` 伪造 | 不可上线 | 对接真实快递公司 API |
| 售后工单只存数据库 | 人工处理环节缺失 | 工单推送到钉钉/飞书通知 |
| 商品库存是静态 seed 数据 | 与实际库存脱节 | 对接 ERP/WMS 系统实时查询 |
| 客服电话 400-888-8888 写死在代码里 | 无真正转接能力 | 对接在线客服平台（企业微信/微信客服） |
| 工具函数硬编码在 `tools/` 目录 | 新增工具需改代码重启 | MCP Server 热插拔，Agent 自动发现新工具 |

核心价值：**让 Agent 的能力边界不再受限于一个代码仓库**。物流、支付、库存、通知等能力由独立的 MCP Server 提供，Agent 通过标准协议调用。

---

## 二、架构设计

### 2.1 整体架构

```
┌─────────────────────────────────────────────────────────┐
│                     LangGraph 主图                        │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐ │
│  │ order    │  │ product  │  │ aftersale│  │   faq    │ │
│  │ agent    │  │ agent    │  │ agent    │  │  agent   │ │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘ │
│       │              │              │              │      │
│       └──────────────┴──────────────┴──────────────┘      │
│                          │                                │
│              工具层: LangChain Tool                         │
│       ┌──────────┬───────┴───────┬──────────┐            │
│       │ 本地工具  │  MCP 工具     │  RAG 工具 │            │
│       │ auth     │  (自动发现)    │ product   │            │
│       │ order DB │  logistics    │ faq       │            │
│       │ aftersale│  payment      │ knowledge │            │
│       └──────────┴───────┬───────┴──────────┘            │
└──────────────────────────┼────────────────────────────────┘
                           │ MCP Protocol (stdio / SSE)
           ┌───────────────┼───────────────┐
           │               │               │
    ┌──────┴──────┐ ┌──────┴──────┐ ┌──────┴──────┐
    │ 物流查询     │ │ 支付服务     │ │ 通知服务     │
    │ MCP Server  │ │ MCP Server  │ │ MCP Server  │
    │             │ │             │ │             │
    │ - track     │ │ - pay       │ │ - dingtalk  │
    │ - estimate  │ │ - refund    │ │ - email     │
    │ - carriers  │ │ - verify    │ │ - sms       │
    └──────┬──────┘ └──────┬──────┘ └──────┬──────┘
           │               │               │
    真实的快递API    支付宝/微信      钉钉/邮件/短信
```

### 2.2 工具分层

```
Agent 可用工具 = 本地工具 + MCP 工具 + RAG 工具
                      │
                      ├── 本地工具（不变）
                      │   auth_tools / order_tools (DB) / aftersale_tools (DB)
                      │   这些在代码仓内，随系统部署
                      │
                      ├── MCP 工具（新增）
                      │   由独立的 MCP Server 进程提供
                      │   Agent 启动时通过 MCP Client 自动发现并注册
                      │
                      └── RAG 工具（不变）
                          Chroma 知识库检索
```

---

## 三、MCP Server 设计

### 3.1 物流查询 MCP Server

**定位**：替代 `track_shipment` 中的 `random.randint` 假数据，对接真实快递 API。

```
MCP Server: logistics-mcp
─────────────────────────
Tools:
  track_shipment(order_no) → 快递100 / 菜鸟裹裹 API 查询实时物流
  estimate_delivery(address, carrier) → 预估送达时间
  list_carriers() → 可用快递公司列表
  modify_address(order_no, new_addr) → 对接快递公司修改地址接口

Resources:
  carrier://{code}/coverage → 快递公司覆盖范围（JSON）

外部依赖：
  快递100 API / 菜鸟物流云 API
```

**改造点**：`order_tools.py` 中的 `track_shipment` 和 `modify_shipping_address` 改为调用 MCP，本地工具只做归属验证，实际物流操作委托给 MCP Server。

### 3.2 支付服务 MCP Server

**定位**：处理退款、查询支付状态，对接支付宝/微信支付。

```
MCP Server: payment-mcp
───────────────────────
Tools:
  refund(order_no, amount) → 发起原路退款
  query_payment(order_no) → 查询支付状态/支付方式
  verify_payment(order_no) → 验证是否已支付完成

Resources:
  payment://{order_no}/receipt → 电子回单（PDF/图片）

外部依赖：
  支付宝开放平台 / 微信支付商户 API
```

**改造点**：`aftersale_tools.py` 中退款成功后的通知可改为调用 MCP 实际退款。

### 3.3 通知服务 MCP Server

**定位**：转人工时不只是返回文字，而是真正发送通知。

```
MCP Server: notify-mcp
──────────────────────
Tools:
  send_dingtalk(user_id, message) → 发钉钉消息
  send_email(to, subject, body) → 发邮件
  send_sms(phone, message) → 发短信
  create_ticket(title, priority, assignee) → 创建工单（对接 Jira/飞书）

外部依赖：
  钉钉机器人 / 飞书 API / 阿里云短信
```

**改造点**：`human_handoff_node` 不只返回文字，同时调用 MCP 创建工单 + 发送通知。

### 3.4 库存管理 MCP Server

**定位**：对接 ERP/WMS 系统，提供实时库存。

```
MCP Server: inventory-mcp
─────────────────────────
Tools:
  check_stock(sku) → 实时库存查询（对接 ERP）
  reserve_stock(sku, qty) → 预留库存
  get_warehouse_info(product_id) → 仓库位置/发货时效

外部依赖：
  企业内部 ERP / WMS 系统 API
```

**改造点**：`product_tools.py` 中的 `check_stock` 改为调用 MCP 获取实时库存。

---

## 四、LangGraph 集成方式

### 4.1 使用 langchain-mcp-adapters

```python
# config.py 新增
import asyncio
from langchain_mcp_adapters.client import MultiServerMCPClient

async def create_mcp_client():
    """创建 MCP 客户端，连接所有 MCP Server"""
    client = MultiServerMCPClient({
        "logistics": {
            "command": "python",
            "args": ["-m", "mcp_servers.logistics"],
            "env": {"KUAIDI100_KEY": os.getenv("KUAIDI100_KEY")}
        },
        "payment": {
            "command": "python", 
            "args": ["-m", "mcp_servers.payment"],
            "env": {"ALIPAY_APP_ID": os.getenv("ALIPAY_APP_ID")}
        },
        "notify": {
            "command": "python",
            "args": ["-m", "mcp_servers.notify"],
            "env": {"DINGTALK_WEBHOOK": os.getenv("DINGTALK_WEBHOOK")}
        },
    })
    return client

_mcp_client = None

async def get_mcp_tools():
    """获取所有 MCP 提供的工具列表"""
    global _mcp_client
    if _mcp_client is None:
        _mcp_client = await create_mcp_client()
    return _mcp_client.get_tools()
```

### 4.2 Agent 绑定 MCP 工具

```python
# agents/order_agent.py 改造后
from config import get_mcp_tools

async def build_order_agent():
    llm = make_llm(temperature=0.3)
    
    # 本地工具 + MCP 工具 + 认证工具
    mcp_tools = await get_mcp_tools()
    logistics_tools = [t for t in mcp_tools if t.name in (
        "track_shipment", "estimate_delivery", "modify_address"
    )]
    
    all_tools = AUTH_TOOLS + ORDER_DB_TOOLS + logistics_tools
    llm_with_tools = llm.bind_tools(all_tools)
    # ... 其余不变
```

### 4.3 渐进式改造策略

**Phase 1：影子模式**（不改现有逻辑）

```
工具层同时调用本地工具 + MCP 工具
  ├── 主路径：本地工具（当前逻辑，保证稳定）
  └── 影子路径：MCP 工具（仅日志记录，不回传给用户）
```

**Phase 2：灰度切换**

```
按订单状态分流：
  待付款/待发货 → MCP 工具
  已发货/已完成 → 本地工具（保持稳定）
```

**Phase 3：全量切换**

```
MCP 工具成为主要路径
本地工具作为 fallback（MCP 超时/异常时降级）
```

---

## 五、项目结构变更

```
ecommerce_cs/
├── mcp_servers/                  # 【新增】MCP Server 目录
│   ├── __init__.py
│   ├── logistics/
│   │   ├── __init__.py
│   │   ├── server.py             # MCP Server 入口（stdio）
│   │   └── kuaidi100_client.py   # 快递 API 封装
│   ├── payment/
│   │   ├── __init__.py
│   │   ├── server.py
│   │   └── alipay_client.py
│   ├── notify/
│   │   ├── __init__.py
│   │   ├── server.py
│   │   └── dingtalk_client.py
│   └── inventory/
│       ├── __init__.py
│       ├── server.py
│       └── erp_client.py
│
├── mcp_config.py                 # 【新增】MCP 客户端配置 + 工具注册
├── tools/                        # 【改造】部分工具改为调用 MCP
│   ├── order_tools_mcp.py        # 新增：MCP 版本的物流工具
│   └── ...
├── agents/                       # 【改造】Agent 绑定 MCP 工具
├── server.py                     # 【改造】lifespan 中初始化 MCP client
└── ...
```

---

## 六、MCP Server 示例：物流查询

### 6.1 MCP Server 实现

```python
# mcp_servers/logistics/server.py
import os
from mcp.server import Server
from mcp.server.stdio import stdio_server

server = Server("logistics-mcp")

@server.tool()
async def track_shipment(tracking_no: str, carrier: str = "auto") -> dict:
    """查询快递实时轨迹"""
    client = Kuaidi100Client(os.getenv("KUAIDI100_KEY"))
    result = await client.query(tracking_no, carrier)
    return {
        "status": result.status,
        "checkpoints": [
            {"time": c.time, "location": c.location, "desc": c.desc}
            for c in result.checkpoints
        ],
        "estimated_delivery": result.estimated_delivery,
    }

@server.tool()
async def estimate_delivery(from_city: str, to_city: str, carrier: str) -> dict:
    """预估配送时效"""
    # ...

@server.resource("carrier://{code}/coverage")
async def carrier_coverage(code: str) -> str:
    """获取快递公司覆盖范围"""
    # ...

async def main():
    async with stdio_server() as streams:
        await server.run(streams[0], streams[1], server.create_initialization_options())
```

### 6.2 Agent 工具列表的最终形态

以 order_agent 为例，工具来源分布：

```
order_agent 可用工具 (8个)
├── 本地认证 (1)
│   └── get_current_user_phone        [auth_tools.py]
├── 本地数据库 (1)
│   └── list_my_orders               [order_tools.py]
├── MCP: 物流 (4)
│   ├── track_shipment               [logistics MCP]
│   ├── estimate_delivery            [logistics MCP]
│   ├── list_carriers                [logistics MCP]
│   └── modify_address               [logistics MCP]
└── MCP: 库存 (2)
    ├── check_stock                  [inventory MCP]
    └── get_warehouse_info           [inventory MCP]
```

---

## 七、MCP 带来的架构收益

| 维度 | 之前 | 之后 |
|------|------|------|
| 物流数据 | `random.randint` 伪造 | 快递 API 实时查询 |
| 新增工具 | 写代码 → 重启服务 | 启动 MCP Server → Agent 自动发现 |
| 工具复用 | 每个项目拷贝 `tools/` 目录 | MCP Server 独立部署，多个 Agent 共享 |
| 故障隔离 | 一个工具挂了整个 Agent 崩溃 | MCP Server 独立进程，超时降级到本地兜底 |
| 外部集成 | 硬编码 API 调用 | 通过 MCP 标准接口，换供应商只改 Server |
| 安全边界 | 工具代码和业务代码混在一起 | MCP Server 独立进程，最小权限原则 |
| 多语言支持 | 只能用 Python 写工具 | MCP 支持任何语言实现 Server（Go/Node/Rust） |

---

## 八、实施路线图

```
Week 1-2: 搭建 logistics-mcp 原型
  - 实现 track_shipment 工具（对接快递100）
  - 在 order_agent 中接入 MCP 工具（影子模式）
  - 验证稳定后切换为主路径

Week 3-4: 搭建 notify-mcp
  - 实现 send_dingtalk + create_ticket
  - human_handoff_node 对接通知

Week 5-6: 搭建 payment-mcp + inventory-mcp
  - 退款流程对接真实支付 API
  - 库存查询对接 ERP

Week 7-8: 完善
  - 所有 MCP Server 加降级 + 重试 + 监控
  - 编写 MCP Server 的 Dockerfile
  - docker-compose 一键启动全部服务
```

---

## 九、部署架构（最终态）

```
docker-compose.yml
─────────────────
services:
  chat-server:     # FastAPI 客服后端 (8000)
  kb-server:       # 知识库管理 (8001)
  postgres:        # 业务数据 + checkpoint
  chroma:          # 向量数据库

  # MCP Servers
  logistics-mcp:   # 物流查询（stdio 模式，chat-server 子进程）
  payment-mcp:     # 支付服务
  notify-mcp:      # 通知服务
  inventory-mcp:   # 库存管理
```

MCP Server 通过 stdio 协议与 chat-server 通信（`MultiServerMCPClient` 自动管理子进程生命周期），无需额外端口。
