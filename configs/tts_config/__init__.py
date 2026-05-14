"""
@Project ：streaming-ava 
@File    ：__init__.py
@IDE     ：PyCharm 
@Author  ：潘尚国
@Date    ：2026/5/13 21:07 
"""
from typing import Any, Dict, List, Optional, Union

from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from .cosyvoice import Cosyvoice
from .doubao import DouBao
from .step_fun import StepFun


class VoiceConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    provider: str = Field("cosyvoice", description="TTS provider: cosyvoice / stepfun / doubao")
    cosyvoice: Cosyvoice = Field(default_factory=Cosyvoice, description="TTS cosyvoice")
    step_fun: StepFun = Field(default_factory=StepFun, description="TTS stepfun")
    dou_bao: DouBao = Field(
        default_factory=DouBao,
        validation_alias=AliasChoices("dou_bao", "doubao"),
        description="TTS DouBao",
    )
    volume: int = Field(50, description="音量调节")
    speech_rate: float = Field(1.0, description="语速调节")
    pitch_rate: float = Field(1.0, description="语调调节")
    format: str = Field("wav", description="音频格式")
    sample_rate: int = Field(24000, description="音频采样率")
    timeout: int = Field(120, description="TTS 超时时间（秒）")
