"""
@Project ：streaming-ava 
@File    ：cosyvoice.py
@IDE     ：PyCharm 
@Author  ：潘尚国
@Date    ：2026/5/13 21:08 
"""
from typing import Any, Dict, List, Optional, Union

from pydantic import AliasChoices, BaseModel, ConfigDict, Field

class Cosyvoice(BaseModel):
    api_base: str = Field(
        "https://dashscope.aliyuncs.com/api/v1/services/audio/tts/SpeechSynthesizer",
        description="TTS 接口地址",
    )
    api_key: str = Field("", description="TTS 接口密钥")
    model: str = Field("cosyvoice-v3-flash", description="TTS 模型名称")
    voice: str = Field("longanyang", description="发音人")
    instruction: str = Field("", description="语音指令")


