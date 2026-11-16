export const state = {
  ws: null,
  connectPromise: null,

  audioCtx: null,
  mediaStream: null,
  workletNode: null,
  analyserNode: null,
  levelDataArray: null,
  levelAnimationId: null,

  playbackCtx: null,
  playbackGainNode: null,
  playbackScheduledAt: 0,
  playbackSources: new Set(),
  playbackReportedTurns: new Set(),

  isMicActive: false,
  isMuted: false,
  isMicTransitioning: false,
  callStartedAt: null,
  callAccumulatedMs: 0,
  timerIntervalId: null,

  currentSessionState: "idle",
  lastLocalInterruptAt: 0,
  localSpeechInterruptArmed: true,

  activeAssistantTurnId: null,
  partialDraftId: null,
  assistantNodes: new Map(),
  userMessageKeys: new Set(),
  messageMetaStore: new Map(),
  localMessageSeq: 0,
  interruptedAssistantTurns: new Set(),

  pendingAttachments: [],

  lastTimeline: {},
  lastProfile: {},
  lastRoute: {},
  lastPipelineDebug: {},
};