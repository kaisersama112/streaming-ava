export const TARGET_SAMPLE_RATE = 16000;
export const PLAYBACK_SAMPLE_RATE = 24000;
export const SESSION_STORAGE_KEY = "ava.realtime.session_id";
export const STATIC_ASSET_VERSION = "20261117-router-test";
export const MAX_LOG_ENTRIES = 200;
export const LOCAL_BARGE_IN_RMS_THRESHOLD = 0.02;
export const LOCAL_BARGE_IN_RELEASE_THRESHOLD = 0.012;
export const LOCAL_BARGE_IN_COOLDOWN_MS = 450;

export const TIMELINE_LABELS = [
  ["t0_submit", "t0 用户提交"],
  ["t1_prepare_state_done", "t1 状态准备"],
  ["t2_router_done", "t2 路由完成"],
  ["t3_turn_plan_done", "t3 轮次计划"],
  ["t4_first_token", "t4 首个 token"],
  ["t5_first_tts_submit", "t5 提交 TTS"],
  ["t6_first_tts_chunk", "t6 TTS 首块"],
  ["t7_first_push_pcm", "t7 推送 PCM"],
  ["t8_frontend_playback", "t8 前端播放"],
];