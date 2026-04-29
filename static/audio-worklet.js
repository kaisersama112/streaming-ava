class PCMDownsamplerProcessor extends AudioWorkletProcessor {
  constructor(options) {
    super();
    const opts = options?.processorOptions || {};
    this.targetSampleRate = opts.targetSampleRate || 16000;
    this.sourceSampleRate = sampleRate; // global in AudioWorklet
    this.ratio = this.sourceSampleRate / this.targetSampleRate;
    this._carry = 0.0;
  }

  // Convert Float32 [-1,1] to Int16
  _floatToInt16(sample) {
    const s = Math.max(-1, Math.min(1, sample));
    return s < 0 ? s * 0x8000 : s * 0x7fff;
  }

  process(inputs) {
    const input = inputs[0];
    if (!input || input.length === 0) return true;
    const ch0 = input[0];
    if (!ch0 || ch0.length === 0) return true;

    // Naive downsample by picking samples at fixed ratio.
    // For ASR this is acceptable as an MVP; you can swap to better resampler later.
    const outLen = Math.floor((ch0.length - this._carry) / this.ratio);
    if (outLen <= 0) return true;

    const out = new Int16Array(outLen);
    let inPos = this._carry;
    for (let i = 0; i < outLen; i++) {
      const idx = Math.floor(inPos);
      out[i] = this._floatToInt16(ch0[idx]);
      inPos += this.ratio;
    }
    this._carry = inPos - ch0.length;
    if (this._carry < 0) this._carry = 0;

    this.port.postMessage(out.buffer, [out.buffer]);
    return true;
  }
}

registerProcessor("pcm-downsampler", PCMDownsamplerProcessor);

class PCMPlayerProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.queue = [];
    this.current = null;
    this.offset = 0;

    this.port.onmessage = (event) => {
      const data = event?.data || {};
      if (data.type === "clear") {
        this.queue = [];
        this.current = null;
        this.offset = 0;
        return;
      }
      if (data.type === "push" && data.buffer) {
        const chunk = new Int16Array(data.buffer);
        if (chunk.length) {
          this.queue.push(chunk);
        }
      }
    };
  }

  _ensureCurrent() {
    while ((!this.current || this.offset >= this.current.length) && this.queue.length) {
      this.current = this.queue.shift();
      this.offset = 0;
    }
    return !!this.current && this.offset < this.current.length;
  }

  process(inputs, outputs) {
    const output = outputs[0];
    if (!output || output.length === 0) {
      return true;
    }

    const channel = output[0];
    for (let i = 0; i < channel.length; i += 1) {
      if (!this._ensureCurrent()) {
        channel[i] = 0;
        continue;
      }
      channel[i] = this.current[this.offset] / 32768;
      this.offset += 1;
    }

    for (let c = 1; c < output.length; c += 1) {
      output[c].set(channel);
    }

    if (this.current && this.offset >= this.current.length) {
      this.current = null;
      this.offset = 0;
    }
    return true;
  }
}

registerProcessor("pcm-player", PCMPlayerProcessor);
