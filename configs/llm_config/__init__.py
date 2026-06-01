"""
@Project ：streaming-ava 
@File    ：__init__.py.py
@IDE     ：PyCharm 
@Author  ：潘尚国
@Date    ：2026/5/14 02:33 
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class OpenAIConfig(BaseModel):
    api_base: str = Field("https://dashscope.aliyuncs.com/compatible-mode/v1", description="兼容 OpenAI 的基础 URL")
    api_key: str = Field("", description="LLM 接口密钥")
    model: str = Field("qwen-plus", description="LLM 模型名称")
    multimodal_model: str = Field("qwen3.5-omni-plus", description="多模态 LLM 模型名称")
    router_model: str = Field("qwen3.6-flash", description="意图理解模型名称")
    timeout: int = Field(60, description="LLM 超时时间（秒）")
    intent_timeout: int = Field(8, description="意图理解模型超时时间（秒）")


class BigModelConfig(BaseModel):
    api_base: str = Field("https://open.bigmodel.cn/api/paas/v4", description="智谱兼容接口地址")
    api_key: str = Field("", description="智谱 API Key")
    model: str = Field("glm-4.6v-flash", description="智谱模型名称")
    timeout: int = Field(15, description="智谱请求超时时间（秒）")
    enabled: bool = Field(False, description="是否启用智谱模型配置")
