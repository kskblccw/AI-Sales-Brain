"""
auth_tools.py — 身份验证工具

核心设计原则：
  - 手机号从不在 LLM 上下文（System Prompt / 对话历史）中出现
  - LLM 通过 get_current_user_phone() 工具获取，但不"看到"推导过程
  - 工具只返回当前 Session 绑定的手机号，无法越权获取其他用户
"""

from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig


@tool
def get_current_user_phone(config: RunnableConfig) -> str:
    """
    获取当前登录用户的手机号。
    仅在需要验证身份、查询订单、创建售后申请时调用。
    如果用户未登录（返回空字符串），请告知用户在前端右上角输入手机号登录。

    注意：此工具不接受任何参数，只能获取当前会话绑定的用户手机号。
    """
    phone = (config or {}).get("configurable", {}).get("user_phone", "")
    if phone:
        return f"当前用户手机号：{phone}（已验证）"
    else:
        return "用户未登录。请告知用户：'请先在前端右上角输入您的手机号完成登录，我才能帮您查询订单或处理售后。'"


AUTH_TOOLS = [get_current_user_phone]
