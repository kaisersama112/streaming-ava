"""
@Project ：streaming-ava 
@File    ：step-fun.py
@IDE     ：PyCharm 
@Author  ：潘尚国
@Date    ：2026/5/13 21:08 
"""
from typing import Any, Dict, List, Optional, Union

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class StepFun(BaseModel):
    api_key: str = Field("", description="StepFun TTS API Key")
    ws_url: str = Field("wss://api.stepfun.com/v1/realtime/audio", description="StepFun TTS WebSocket 地址")
    model: str = Field("stepaudio-2.5-tts", description="StepFun TTS 模型名称")
    voice: str = Field("cixingnansheng", description="StepFun TTS 音色")
    instruction: str = Field("", description="StepFun TTS 语音指令")
