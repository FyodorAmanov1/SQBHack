/**
 * Downmixes to mono, resamples to 16 kHz (linear), outputs Int16 to main thread.
 * State is carried across render quanta for continuous resampling.
 */
class CaptureProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this._carry = 0;
    this._last = 0;
  }

  process(inputs) {
    const input = inputs[0];
    if (!input || input.length === 0) {
      return true;
    }
    let ch0 = input[0];
    if (input.length > 1) {
      const n = ch0.length;
      const mix = new Float32Array(n);
      for (let c = 0; c < input.length; c++) {
        const ch = input[c];
        for (let i = 0; i < n; i++) mix[i] += ch[i];
      }
      const inv = 1 / input.length;
      for (let i = 0; i < n; i++) mix[i] *= inv;
      ch0 = mix;
    }

    const sr = sampleRate;
    const outRate = 16000;
    const step = sr / outRate;
    const M = ch0.length;

    const ext = new Float32Array(M + 1);
    ext[0] = this._last;
    ext.set(ch0, 1);

    const out = [];
    let pos = this._carry + 1;
    const limit = M + 1;
    while (pos < limit) {
      const i = Math.floor(pos);
      const f = pos - i;
      const s0 = ext[i];
      const s1 = ext[i + 1];
      const s = s0 * (1 - f) + s1 * f;
      const v = Math.max(-32768, Math.min(32767, Math.round(s * 32767)));
      out.push(v);
      pos += step;
    }

    this._last = ch0[M - 1];
    this._carry = pos - limit;

    if (out.length > 0) {
      const arr = new Int16Array(out);
      this.port.postMessage(arr.buffer, [arr.buffer]);
    }
    return true;
  }
}

registerProcessor("capture-processor", CaptureProcessor);
