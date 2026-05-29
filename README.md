# streaming-ava

`streaming-ava` 鏄竴涓潰鍚?*瀹炴椂璇煶瀵硅瘽**鐨勫妯℃€佸姪鎵嬪悗绔紝鏍稿績鑳藉姏鍖呮嫭锛?
- WebSocket 鍏ㄥ弻宸ヨ闊充細璇?- 娴佸紡 ASR锛堣闊宠瘑鍒級
- LLM 璺敱涓庡洖绛旂敓鎴?- 娴佸紡 TTS锛堣闊冲悎鎴愶級
- 鍥剧墖 / 闊抽 / 瑙嗛 / 鏂囦欢闄勪欢杈撳叆
- Prompt 鎻掍欢鍖栫粍缁?- 浼氳瘽鐘舵€併€佽蹇嗐€佽皟璇曡拷韪?- 鍙€夋帴鍏?OpenAI Agents SDK

瀹冨綋鍓嶆洿鍍忎竴濂椻€滃彲杩愯鐨勫疄鏃?Agent 鍚庣楠ㄦ灦 + 绛栫暐绯荤粺鈥濓紝鑰屼笉鏄崟涓€鑱婂ぉ鎺ュ彛銆?
---

## 1. 绯荤粺鐩爣

杩欎釜椤圭洰鐨勭洰鏍囨槸鎶婁竴娆″疄鏃跺璇濇媶鎴愮ǔ瀹氱殑鍑犱釜闃舵锛?
1. 鎺ユ敹鐢ㄦ埛杈撳叆锛堟枃鏈?/ 楹﹀厠椋?PCM / 闄勪欢锛?2. 璇嗗埆褰撳墠杞簲璇ヨ繘鍏ュ摢涓満鏅紙鏁欒偛銆侀棶绛斻€佹緞娓呫€侀棽鑱婄瓑锛?3. 鍩轰簬鍦烘櫙閫夋嫨 Prompt 绛栫暐
4. 娴佸紡鐢熸垚鍥炵瓟
5. 瀵瑰洖绛斿仛璇煶鍙嬪ソ鍖栧鐞嗭紙灏ゅ叾鏄暟瀛?/ LaTeX锛?6. 璋冪敤 TTS 骞舵帹閫佸墠绔挱鏀?7. 璁板綍鐘舵€併€佽蹇嗐€乼race 鍜岃瘎浼颁俊鎭?
---

## 2. 鏍稿績鏋舵瀯鎬昏

### 2.1 涓绘祦绋?
```text
Browser / Web Client
  鈹溾攢 鏂囨湰杈撳叆
  鈹溾攢 PCM 闊抽娴?  鈹斺攢 闄勪欢
          鈹?          鈻?FastAPI + WebSocket (`app.py`)
          鈹?          鈻?RealtimeConversationSession
  鈹溾攢 ASR partial / final
  鈹溾攢 turn lifecycle
  鈹溾攢 interrupt / barge-in
  鈹斺攢 event bus
          鈹?          鈻?ContextCompiler
  鈹溾攢 TurnInput 鏍囧噯鍖?  鈹溾攢 Snapshot 鏋勫缓
  鈹溾攢 Router messages 缂栬瘧
  鈹斺攢 Responder messages 缂栬瘧
          鈹?          鈻?Router LLM (`ava/routing/runner.py`)
  鈹斺攢 杈撳嚭 RouteDecision + router_plan
          鈹?          鈻?TurnPlan Builder (`ava/pipeline/generation/dispatcher.py`)
  鈹斺攢 灏?router_plan 鐗╁寲涓哄叿浣?Prompt 绛栫暐
          鈹?          鈻?Reply Service (`ava/pipeline/generation/reply_service.py`)
  鈹溾攢 鐩存帴 LLM 鐢熸垚
  鈹斺攢 鎴栧彲閫?Agents SDK 鎵ц
          鈹?          鈻?Speech Postprocess
  鈹溾攢 LaTeX span 妫€娴?  鈹溾攢 鏁板鍙ｈ鍖?  鈹斺攢 娴佸紡鏂囨湰缂撳啿
          鈹?          鈻?TTS Provider
          鈹?          鈻?Realtime Audio Bridge / Frontend Playback
```

### 2.2 璁捐鐗圭偣

- **鍗曟璺敱锛屽崟娆¤鍒?*锛歊outer 涓€娆℃€ц繑鍥?`route + plan`锛屽悗缁笉鍐嶆湰鍦伴噸澶嶈鍒欒矾鐢?- **涓婁笅鏂囩粺涓€缂栬瘧**锛歚ava/context_engine` 鏄敮涓€涓婁笅鏂囩紪璇戞牳蹇?- **Prompt 璧勪骇涓庤繍琛屾€佸垎绂?*锛氶潤鎬?Prompt 鍦?`prompt-plugin/`锛屽姩鎬佺姸鎬侀€氳繃 runtime context 娉ㄥ叆
- **鐘舵€佷笌璁板繂鍒嗙**锛歚ConversationState` 绠?turn 鐢熷懡鍛ㄦ湡锛宍SessionMemory` 绠￠暱鏈熻蹇嗕笌鏁欒偛鎬?- **瀹炴椂浼樺厛**锛氭敮鎸?partial ASR銆佽竟鐢熸垚杈规挱銆佹墦鏂紙barge-in锛夈€佹挱鏀炬椂搴忔墦鐐?- **澶氬悗绔吋瀹?*锛歀LM / ASR / TTS 閮戒互 provider 閰嶇疆鍒囨崲

---

## 3. 浠ｇ爜缁撴瀯鍒嗘瀽

### 3.1 椤跺眰鐩綍

```text
streaming-ava/
鈹溾攢 app.py                      # FastAPI + WebSocket 涓诲叆鍙?鈹溾攢 realtime_server.py          # 鏈湴鍚姩鍏ュ彛
鈹溾攢 configs/                    # 涓婚厤缃笌鍒?provider 閰嶇疆
鈹溾攢 ava/                        # 绯荤粺涓讳唬鐮?鈹溾攢 prompt-plugin/              # Prompt 璧勪骇灞?鈹溾攢 static/                     # 璋冭瘯/婕旂ず鍓嶇
鈹溾攢 state/                      # 鏈湴鐘舵€併€乼race銆佽瘎浼版棩蹇?鈹溾攢 tests/                      # 鍗曞厓娴嬭瘯
鈹斺攢 scripts/                    # 杈呭姪鑴氭湰
```

### 3.2 `ava/` 妯″潡鑱岃矗

#### `ava/context_engine/`

涓婁笅鏂囩紪璇戞牳蹇冿紝璐熻矗鎶娾€滅敤鎴疯緭鍏?+ 鍘嗗彶 + 闄勪欢 + 璁板繂 + 璺敱淇℃伅鈥濈紪璇戞垚妯″瀷鍙秷璐圭殑 messages銆?
鍏抽敭鑱岃矗锛?
- 鏍囧噯鍖?`TurnInput`
- 鏋勫缓 `ContextSnapshot`
- 缂栬瘧 router / responder 鐨?runtime payload
- 缂栬瘧鏈€缁?messages
- 绠＄悊 continuity銆乵emory projection銆侀檮浠剁户鎵跨瓑

杩欐槸褰撳墠绯荤粺鏈€鍏抽敭鐨勨€滀腑鏋㈠眰鈥濄€?
#### `ava/domain/`

棰嗗煙妯″瀷灞傦紝璐熻矗瀹氫箟绯荤粺鈥滄槸浠€涔堚€濓紝涓嶈礋璐ｂ€滄€庝箞璋冪敤澶栭儴鑳藉姏鈥濄€?
涓昏瀛愭ā鍧楋細

- `conversation/`锛氫細璇濈姸鎬併€佺瓥鐣ャ€佹憳瑕?- `routing/`锛氳矾鐢卞喅绛栨ā鍨嬨€乻chema銆佺瓥鐣?- `memory/`锛氭暀鑲叉€併€佹€荤粨銆乤rtifact cache銆佹绱?- `multimodal/`锛氬妯℃€佽緭鍏?/ 濯掍綋瀵硅薄

#### `ava/capabilities/`

澶栭儴鑳藉姏閫傞厤灞傘€?
- `llm/`锛氳亰澶┿€佹帹鐞嗚姹傛瀯寤恒€乸rovider 鏄犲皠銆佹祦寮忎簨浠?- `asr/`锛氭祦寮忚瘑鍒鎴风涓?provider 宸ュ巶
- `tts/`锛氭祦寮?闈炴祦寮?TTS 閫傞厤
- `prompt/`锛歅romptCenter銆丳romptRuntime銆丳romptBuilder

#### `ava/pipeline/`

鎵ц缂栨帓灞傦紝璐熻矗鎶婁竴杞璇濈湡姝ｈ窇瀹屻€?
- `streaming/`锛氬疄鏃朵細璇濄€佷簨浠躲€佹墦鏂€佽闊虫祦
- `generation/`锛歵urn plan 鏋勫缓銆乺eply dispatcher銆乺eply service
- `speech/`锛氭暟瀛︽枃鏈彛璇寲銆丩aTeX 娴佸紡澶勭悊
- `agent/`锛欰gents SDK 鎵ц璺緞
- `output/`锛氳瘎浼版爣绛句笌鏃ュ織

#### `ava/core/`

鍩虹杩愯鑳藉姏銆?
- `session/`锛氱姸鎬佸姞杞姐€乼urn 鍓嶉澶勭悊
- `events/`锛氬疄鏃朵簨浠跺畾涔?- `tracing/`锛氱粨鏋勫寲 trace 杈撳嚭
- `runtime/`锛氳繍琛屾椂閿欒绛?
#### `ava/interfaces/`

涓庡閮ㄤ氦浜掔殑鎺ュ彛灞傘€?
- `websocket/`锛氶煶棰戞ˉ銆佹挱鏀惧櫒閰嶇疆銆侀煶棰?patch

---

## 4. 鍏ュ彛涓庤繍琛屾柟寮?
### 4.1 鍚庣鍏ュ彛

- `app.py`
  - 鍒涘缓 `FastAPI` 搴旂敤
  - 鏆撮湶 `/health`
  - 鏆撮湶 `/ws/audio`
  - 鎸傝浇 `static/` 鍓嶇

- `realtime_server.py`
  - 浠?`configs.settings` 璇诲彇 `host/port/reload`
  - 浣跨敤 `uvicorn.run(app, ...)` 鍚姩

### 4.2 鍓嶇婕旂ず椤?
璁块棶鏍硅矾寰?`/` 浼氱洿鎺ヨ繑鍥?`static/index.html`锛岃繖鏄竴涓交閲忚皟璇曞彴锛屾敮鎸侊細

- 杈撳叆 `session_id`
- 寤虹珛 WebSocket 杩炴帴
- 楹﹀厠椋庨噰闆?- 鍙戦€佹枃鏈?- 涓婁紶鎴栨殏瀛橀檮浠?- 鏌ョ湅褰撳墠璺敱銆佺瓥鐣ャ€丳rompt銆佹椂闂寸嚎鎸囨爣
- 瑙﹀彂鎵撴柇涓庨潤闊?
---

## 5. 瀵瑰鎺ュ彛

### 5.1 HTTP

#### `GET /`

杩斿洖鍓嶇璋冭瘯椤甸潰銆?
#### `GET /health`

鍋ュ悍妫€鏌ャ€?
杩斿洖绀轰緥锛?
```json
{"status": "ok"}
```

### 5.2 WebSocket

#### `WS /ws/audio?session_id=<id>`

杩欐槸绯荤粺鐨勬牳蹇冨疄鏃舵帴鍙ｃ€?
杩炴帴鎴愬姛鍚庢湇鍔＄浼氬厛鍙戦€?`hello` 娑堟伅锛屽寘鍚細

- 鍗忚鐗堟湰
- 闊抽鏍煎紡
- `player_url`
- 褰撳墠 `session_id`
- 鏈€杩戝巻鍙?- 褰撳墠鏆傚瓨闄勪欢

#### 瀹㈡埛绔彂閫佺殑鏁版嵁绫诲瀷

##### 1) 浜岃繘鍒跺抚

- 鍘熷 PCM 闊抽
- 鏈嶅姟绔細鎸夊浐瀹氬抚澶у皬鑱氬悎鍚庨€佸叆 ASR

##### 2) JSON 鏂囨湰鎺у埗娑堟伅

鏀寔鐨?`type`锛?
- `text`
  - 鎻愪氦鏂囨湰杈撳叆
  - 鍙悓鏃堕檮甯?`attachments`

- `interrupt`
  - 涓柇褰撳墠 assistant 杈撳嚭 / TTS 鎾斁

- `mic_stopped`
  - 鍛婄煡鏈嶅姟绔害鍏嬮鍋滄
  - 鏈嶅姟绔細 flush 鍓╀綑 PCM 骞?commit 褰撳墠 ASR 杈撳叆娈?
- `ping`
  - 淇濇椿

- `playback_started`
  - 鍓嶇涓婃姤鎾斁寮€濮嬫椂鏈猴紝鐢ㄤ簬 trace 鏃跺簭瀵归綈

- `stage_attachments`
  - 浠呮殏瀛橀檮浠讹紝涓嶈Е鍙戝洖绛?  - 鍚庣画 ASR final 鎴?`text` 鎻愪氦鏃朵竴璧锋秷璐?
- `clear_staged_attachments`
  - 娓呯┖鏆傚瓨闄勪欢

#### 鏈嶅姟绔洖鎺ㄤ簨浠?
浜嬩欢鐢?`RealtimeConversationSession` 鐢熸垚锛屽父瑙佷細鍖呮嫭锛?
- ASR partial / final
- 璺敱鍐崇瓥
- Prompt / strategy 璋冭瘯淇℃伅
- assistant token
- TTS chunk
- turn 瀹屾垚
- 閿欒涓庢帶鍒朵簨浠?
---

## 6. 涓€杞璇濇槸鎬庝箞璺戣捣鏉ョ殑

### 6.1 璇煶杈撳叆璺緞

```text
鍓嶇 PCM 闊抽
-> /ws/audio
-> StreamingASRClient
-> ASR partial / final
-> RealtimeConversationSession.on_asr_partial/final
-> ContextCompiler.build_snapshot(profile="router")
-> RouterService.route()
-> build_turn_plan()
-> stream_reply_with_callbacks()
-> speech postprocess
-> TTS
-> 鍓嶇鎾斁
```

### 6.2 鏂囨湰杈撳叆璺緞

```text
鍓嶇 JSON {type:"text", text, attachments}
-> build_turn_input()
-> submit_turn()
-> RouterService.route()
-> build_turn_plan()
-> generate / stream reply
```

### 6.3 璺敱闃舵

璺敱鍣ㄧ殑璐ｄ换闈炲父鍏嬪埗锛屽彧鍋氾細

- 鍒ゅ畾 `session_scene`
- 鍒ゅ畾 `turn_scene`
- 鍒ゅ畾鎰忓浘涓庣疆淇″害
- 鐢熸垚缁撴瀯鍖?`plan`

瀹?*涓嶇洿鎺ヨ緭鍑烘渶缁堢敤鎴风瓟妗?*銆?
### 6.4 Turn Plan 闃舵

`build_turn_plan()` 浼氭妸 router 杩斿洖鐨勬娊璞?`plan` 鏄犲皠涓猴細

- branch
- module
- subject
- style
- delivery mode
- ui mode
- responder messages

瀵逛簬鏁欒偛鍒嗘敮锛屼細杩涗竴姝ユ槧灏勬垚鏇寸粏鐨勬暀瀛︾瓥鐣ャ€?
### 6.5 鍥炵瓟鐢熸垚闃舵

`reply_service.py` 璐熻矗閫夋嫨鎵ц鍚庣锛?
- 榛樿锛氱洿鎺ヨ蛋 LLM 鑱婂ぉ鐢熸垚
- 鍙€夛細OpenAI Agents SDK

褰撳墠绛栫暐鏄細

- 濡傛灉鍚敤浜?Agents SDK锛屼笖鍒嗘敮/妯″潡鍦ㄥ厑璁稿悕鍗曞唴锛屽彲璧?agent
- 濡傛灉褰撳墠杞寘鍚妯℃€佷笂涓嬫枃锛屼紭鍏堝洖閫€鍒扮洿鎺?LLM 璺緞锛岄伩鍏?agent 璺緞澶勭悊澶嶆潅濯掍綋涓婁笅鏂囨椂涓嶇ǔ瀹?
### 6.6 璇煶鍚庡鐞嗛樁娈?
鍥炵瓟鏂囨湰鍦ㄨ繘鍏?TTS 鍓嶄細缁忚繃锛?
- LaTeX span 妫€娴?- 鏁板琛ㄨ揪寮忓彛璇寲
- 娴佸紡缂撳啿涓庡垎娈?
杩欒鏁板/鍏紡鍐呭鏇撮€傚悎鏈楄銆?
---

## 7. Prompt 绯荤粺璁捐

`prompt-plugin/` 鏄?Prompt 璧勪骇灞傦紝涓嶆壙鎷呰繍琛屾椂缂栨帓閫昏緫銆?
### 7.1 鐩綍缁撴瀯

```text
prompt-plugin/
鈹溾攢 core/
鈹? 鈹溾攢 base/         # persona銆佸妯℃€佸熀纭€瑙勫垯
鈹? 鈹溾攢 contracts/    # 杈撳嚭濂戠害
鈹? 鈹溾攢 renderer/     # 娓叉煋妯℃澘
鈹? 鈹斺攢 router/       # Router prompt
鈹斺攢 plugins/
   鈹溾攢 education/
   鈹溾攢 general_qa/
   鈹溾攢 casual_chat/
   鈹斺攢 clarify/
```

### 7.2 璁捐鍘熷垯

- Prompt 璧勪骇鍙繚瀛?*绋冲畾绛栫暐**
- 杩愯鏃剁姸鎬侀€氳繃 `ContextCompiler` 娉ㄥ叆
- 涓婚摼璺笉鍐嶄緷璧栨湰鍦拌鍒欐爲鍋氫簩娆＄瓥鐣ユ帹鏂?- Router 璐熻矗涓€娆℃€х粰鍑烘渶灏忓繀瑕佽鍒?
---

## 8. 閰嶇疆绯荤粺

### 8.1 閰嶇疆鍏ュ彛

涓婚厤缃枃浠讹細

- `configs/config.yaml`

瀹冮€氳繃 `config_files` 缁х画鍔犺浇锛?
- `configs/asr_config/asr_config.yaml`
- `configs/llm_config/llm_config.yaml`
- `configs/tts_config/tts_config.yaml`

`configs/settings.py` 浼氬仛锛?
- YAML 璇诲彇
- include 閫掑綊鍚堝苟
- Pydantic 鏍￠獙
- 鐜鍙橀噺瑕嗙洊

### 8.2 閲嶈閰嶇疆椤?
#### `server`

- 鏈嶅姟鏍囬
- 鐩戝惉鍦板潃
- 绔彛
- reload

#### `runtime`

杩愯鏃朵富寮€鍏充笌璋冧紭鍙傛暟锛屽寘鎷細

- `state_file`
- `history_window`
- `max_context_messages`
- `router_model`
- `router_timeout`
- `agents_sdk_enabled`
- `agents_sdk_realtime_enabled`
- `realtime_audio_host`
- `realtime_audio_port`
- `barge_in_*`
- `echo_detection_*`
- trace / evaluation 鏂囦欢璺緞

#### `speech_postprocess`

- 鏄惁寮€鍚暟瀛﹀彛璇寲
- 鏄惁鍙浛鎹?LaTeX span
- 娴佸紡 flush 澶у皬

#### `openai_config`

LLM 涓婚厤缃紝鍖呭惈锛?
- `api_base`
- `api_key`
- `model`
- `multimodal_model`
- `timeout`

#### `asr_config`

褰撳墠鏀寔鐨?provider锛?
- `qwen3_asr`
- `dou_bao`

#### `voice_config`

褰撳墠鏀寔鐨?provider锛?
- `cosyvoice`
- `step_fun`
- `dou_bao`

### 8.3 鐜鍙橀噺瑕嗙洊

浠ｇ爜涓凡缁忔敮鎸佷竴閮ㄥ垎鍏抽敭鐜鍙橀噺瑕嗙洊锛屼緥濡傦細

- `STREAMING_AVA_OPENAI_API_KEY`
- `STREAMING_AVA_TTS_PROVIDER`
- `STREAMING_AVA_TTS_API_KEY`
- `STREAMING_AVA_STEPFUN_API_KEY`
- `STREAMING_AVA_DOUBAO_X_API_KEY`
- `STREAMING_AVA_ASR_PROVIDER`
- `STREAMING_AVA_ASR_API_KEY`
- `STREAMING_AVA_QWEN_ASR_API_KEY`
- `STREAMING_AVA_DOUBAO_ASR_X_API_KEY`

寤鸿鎶婄湡瀹炲瘑閽ユ斁鍦ㄧ幆澧冨彉閲忥紝鑰屼笉鏄洿鎺ュ啓鍏?YAML銆?
---

## 9. 鐘舵€併€佽蹇嗕笌杩借釜

### 9.1 `ConversationState`

璐熻矗锛?
- 褰撳墠 session 鐨?turn 鍘嗗彶
- 鏈€杩戣矾鐢变笂涓嬫枃
- 瀹炴椂 turn 鐢熷懡鍛ㄦ湡
- continuity 鎵€闇€鐨勪細璇濈姸鎬?
### 9.2 `SessionMemory`

璐熻矗锛?
- 鏁欒偛鎬佷俊鎭?- summary
- artifact 鍒嗘瀽缂撳瓨
- 鍙绱㈣蹇?
### 9.3 鏈湴鐘舵€佹枃浠?
榛樿浼氬啓鍏?`state/`锛屼緥濡傦細

- `state/memory.json`
- `state/evaluation.jsonl`
- 统一日志输出
- `state/agents_sessions.json`

### 9.4 Trace / Evaluation

绯荤粺骞挎硾浣跨敤 `append_trace_log(...)` 璁板綍锛?
- 璺敱杈撳叆杈撳嚭
- plan 閫夋嫨
- WS 鍛戒护
- 鍓嶇鎾斁鏃跺簭
- Agents SDK fallback
- 鐢熸垚閾捐矾鍏抽敭鑺傜偣

杩欏鎺掓煡瀹炴椂绯荤粺闂寰堟湁浠峰€笺€?
---

## 10. 涓柇涓庡疄鏃舵€ф満鍒?
绯荤粺宸茬粡鍥寸粫瀹炴椂瀵硅瘽鍋氫簡杈冨浼樺寲锛?
- **ASR partial 椹卞姩**
  - 鐢ㄦ埛杩樻病璇村畬鏃跺氨鑳芥洿鏂板眬閮ㄨ瘑鍒粨鏋?
- **barge-in**
  - 鐢ㄦ埛鎵撴柇鏃跺彲灏藉揩鍋滄褰撳墠 assistant 杈撳嚭

- **闊抽妗ヤ笌鎾斁鍣ㄥ垎绂?*
  - TTS 杈撳嚭璧扮嫭绔嬫挱鏀鹃€氳矾

- **鏃堕棿绾挎寚鏍?*
  - 鍓嶇鍙洖鎶ユ挱鏀惧紑濮嬫椂闂?  - 渚夸簬娴嬮噺棣?token銆侀闊抽銆侀鎾欢杩?
- **echo detection**
  - 鍑忓皯 TTS 鍥炲０琚啀娆¤瘑鍒垚鐢ㄦ埛杈撳叆

---

## 11. 渚濊禆涓庢妧鏈爤

### 11.1 Python

- Python `>=3.11`

### 11.2 鏍稿績渚濊禆

鏉ヨ嚜 `pyproject.toml` / `requirements.txt` 鐨勫叧閿緷璧栵細

- `fastapi`
- `uvicorn`
- `openai`
- `openai-agents`
- `pydantic`
- `pyyaml`
- `sympy`
- `lark`
- `dashscope`
- `fastrtc`

---

## 12. 鏈湴鍚姩

### 12.1 瀹夎渚濊禆

濡傛灉浣跨敤 `pip`锛?
```bash
pip install -r requirements.txt
```

濡傛灉甯屾湜鎸?`pyproject.toml` 瀹夎锛屼篃鍙互浣跨敤浣犵啛鎮夌殑宸ュ叿閾撅紙濡?`pip install -e .` 鎴?Poetry锛夈€?
### 12.2 閰嶇疆瀵嗛挜

鑷冲皯闇€瑕佸噯澶囷細

- LLM API Key
- ASR API Key
- TTS API Key

鎺ㄨ崘閫氳繃鐜鍙橀噺娉ㄥ叆锛岃€屼笉鏄洿鎺ユ敼浠撳簱鍐呴厤缃€?
### 12.3 鍚姩鏈嶅姟

```bash
python realtime_server.py
```

榛樿浼氳鍙?`configs/config.yaml` 涓殑 `server.port`銆?
### 12.4 璁块棶璋冭瘯椤?
娴忚鍣ㄦ墦寮€锛?
```text
http://127.0.0.1:7002/
```

濡傛灉浣犱慨鏀逛簡绔彛锛岃鎸夊疄闄呯鍙ｈ闂€?
---

## 13. 娴嬭瘯

褰撳墠浠撳簱涓凡鏈夌殑娴嬭瘯閲嶇偣闆嗕腑鍦細

- 閰嶇疆鍔犺浇涓?include 鍚堝苟
- ASR provider 宸ュ巶
- Doubao / 娴佸紡 ASR 鐩稿叧琛屼负

娴嬭瘯鐩綍锛?
- `tests/test_config_loading.py`
- `tests/test_asr_factory.py`
- `tests/test_doubao_streaming.py`
- `tests/test_doubao_asr_streaming.py`

---

## 14. 閫傚悎缁х画鎵╁睍鐨勭偣

### 14.1 鏂板鍒嗘敮 / 鍦烘櫙

鍙互浠庝袱灞傛墿灞曪細

- `prompt-plugin/plugins/` 澧炲姞 Prompt 璧勪骇
- `ava/pipeline/generation/model_plan_builder.py` 澧炲姞 plan 鍒扮瓥鐣ョ殑鏄犲皠

### 14.2 鏂板 LLM / ASR / TTS provider

鍒嗗埆鍦ㄤ互涓嬬洰褰曟墿灞曪細

- `ava/capabilities/llm/`
- `ava/capabilities/asr/`
- `ava/capabilities/tts/`

骞跺湪 `configs/` 涓ˉ鍏?provider 閰嶇疆銆?
### 14.3 鎺ュ叆鏇村己鐨勮蹇嗘绱?
褰撳墠鏋舵瀯宸茬粡缁?`memory projection / retrieved memories` 鐣欎簡浣嶇疆锛岄€傚悎鍚庣画鎺ワ細

- 鍚戦噺妫€绱?- 瀛︿範杩涘害杩借釜
- artifact 鐞嗚В缂撳瓨澶嶇敤

### 14.4 鍓嶇浜у搧鍖?
鐜板湪 `static/` 鏇村亸璋冭瘯鍙帮紱濡傛灉瑕佹寮忎骇鍝佸寲锛屽彲浠ユ妸锛?
- 杩炴帴鐘舵€?- 瀹炴椂瀛楀箷
- 绛栫暐璋冭瘯闈㈡澘
- 闄勪欢鏆傚瓨鏈哄埗

杩佺Щ鍒扮嫭绔嬪墠绔伐绋嬨€?
---

## 15. 褰撳墠绯荤粺鐨勭湡瀹炲畾浣?
缁煎悎浠ｇ爜缁撴瀯鏉ョ湅锛岃繖涓」鐩笉鏄畝鍗曠殑鈥滆闊宠亰澶?Demo鈥濓紝鑰屾槸涓€濂楀亸宸ョ▼鍖栫殑锛?
- **瀹炴椂澶氭ā鎬佸璇濆悗绔?*
- **鍦烘櫙璺敱 + Prompt 绛栫暐寮曟搸**
- **鏁欒偛 / 闂瓟绫诲姪鎵嬫墽琛屾鏋?*

瀹冨凡缁忓叿澶囨瘮杈冩竻鏅扮殑妯″潡杈圭晫锛?
- 杈撳叆涓庝笂涓嬫枃缂栬瘧
- 璺敱涓庣瓥鐣ラ€夋嫨
- 鍥炵瓟鎵ц
- 璇煶杈撳嚭
- 璁板繂涓庤拷韪?
濡傛灉鍚庣画缁х画杩唬锛屽缓璁噸鐐逛繚鎸佽繖鍑犱釜杈圭晫涓嶈閲嶆柊鑰﹀悎鍦ㄤ竴璧枫€?
---

## 16. 瀹夊叏寤鸿

浠庡綋鍓嶄粨搴撳唴瀹圭湅锛岄厤缃枃浠朵腑瀛樺湪绗笁鏂规湇鍔″瘑閽ュ瓧娈点€傛棤璁鸿繖浜涘瘑閽ユ槸鍚︿粛鐒舵湁鏁堬紝閮藉缓璁細

- 涓嶆妸鐪熷疄瀵嗛挜鎻愪氦鍒颁粨搴?- 鏀圭敤鐜鍙橀噺鎴栨湰鍦版湭鎻愪氦閰嶇疆
- 瀵瑰凡鏆撮湶鐨勫瘑閽ョ珛鍗宠疆鎹?
---

## 17. 鐩稿叧闃呰

- `ava/context_engine/README.md`
- `ava/context_engine/ARCHITECTURE.md`
- `ava/domain/README.md`
- `ava/domain/memory/ARCHITECTURE.md`
- `prompt-plugin/README.md`


