/* Microphone recording.
 *
 * MediaRecorder produces WebM/Opus in Chrome and Firefox, and MP4/AAC in newer
 * Safari; the server sniffs magic bytes and accepts both. The stream's tracks
 * are stopped explicitly on finish, otherwise the browser leaves the microphone
 * indicator on, which is alarming for someone who did not expect it.
 */

/**
 * Why recording is unavailable, or null if it is fine.
 *
 * Worth distinguishing, because the causes need different answers from whoever
 * is standing next to the person: an insecure connection is the facilitator's
 * problem to fix, an old iPad is not fixable at all.
 */
export function unavailableReason() {
  // getUserMedia requires a secure context. Over plain http the API is simply
  // absent, which otherwise surfaces as a baffling permissions error.
  if (typeof window !== 'undefined' && window.isSecureContext === false) return 'insecure';
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) return 'insecure';
  if (typeof MediaRecorder === 'undefined') return 'old-browser';
  return null;
}

export function isSupported() {
  return unavailableReason() === null;
}

/** True for an iPad or iPhone too old for MediaRecorder (before iOS 14.3). */
export function isOldIos() {
  const ua = (typeof navigator !== 'undefined' && navigator.userAgent) || '';
  if (!/iPad|iPhone|iPod/.test(ua)) return false;
  const match = ua.match(/OS (\d+)[_.](\d+)/);
  if (!match) return false;
  const major = Number(match[1]);
  const minor = Number(match[2]);
  return major < 14 || (major === 14 && minor < 3);
}

function pickMimeType() {
  const candidates = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4', 'audio/ogg'];
  for (const type of candidates) {
    if (MediaRecorder.isTypeSupported && MediaRecorder.isTypeSupported(type)) return type;
  }
  return '';   // let the browser choose
}

export class Recorder {
  constructor() {
    this.stream = null;
    this.recorder = null;
    this.chunks = [];
    this.startedAt = 0;
  }

  get recording() {
    return !!this.recorder && this.recorder.state === 'recording';
  }

  /** Throws a plain-language Error if the microphone is unavailable or refused. */
  async start() {
    const reason = unavailableReason();
    if (reason) throw new Error(reason);
    try {
      this.stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true },
      });
    } catch (err) {
      if (err && (err.name === 'NotAllowedError' || err.name === 'SecurityError')) {
        throw new Error('The browser blocked the microphone. Allow it for this site, then try again.');
      }
      if (err && err.name === 'NotFoundError') {
        throw new Error('No microphone was found.');
      }
      throw new Error('The microphone could not be started.');
    }
    const mimeType = pickMimeType();
    this.recorder = new MediaRecorder(this.stream, mimeType ? { mimeType } : undefined);
    this.chunks = [];
    this.recorder.ondataavailable = (e) => { if (e.data && e.data.size) this.chunks.push(e.data); };
    this.recorder.start();
    this.startedAt = Date.now();
  }

  /** Resolves to a Blob, or null if nothing was captured. */
  stop() {
    return new Promise((resolve) => {
      if (!this.recorder || this.recorder.state === 'inactive') { this._release(); resolve(null); return; }
      this.recorder.onstop = () => {
        const type = this.recorder.mimeType || 'audio/webm';
        const blob = this.chunks.length ? new Blob(this.chunks, { type }) : null;
        this._release();
        resolve(blob);
      };
      this.recorder.stop();
    });
  }

  cancel() {
    try { if (this.recording) this.recorder.stop(); } catch (_) {}
    this.chunks = [];
    this._release();
  }

  elapsed() {
    return this.recording ? (Date.now() - this.startedAt) / 1000 : 0;
  }

  _release() {
    if (this.stream) {
      // Turns the microphone indicator off.
      this.stream.getTracks().forEach((track) => track.stop());
      this.stream = null;
    }
    this.recorder = null;
  }
}

/** Extension the server will accept, derived from what the browser produced. */
export function filenameFor(blob) {
  const type = (blob && blob.type) || '';
  if (type.includes('mp4')) return 'recording.m4a';
  if (type.includes('ogg')) return 'recording.ogg';
  return 'recording.webm';
}
