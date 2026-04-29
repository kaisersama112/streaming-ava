"""Compatibility exports for the relocated realtime package."""

from ava.infrastructure.realtime import PlayerConfig, RealtimeAudioBridge, get_bridge, stop_bridge

__all__ = ["PlayerConfig", "RealtimeAudioBridge", "get_bridge", "stop_bridge"]
