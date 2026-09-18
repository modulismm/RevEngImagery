/* Microphone recording.
 *
 * MediaRecorder produces WebM/Opus in Chrome and Firefox, and MP4/AAC in newer
 * Safari; the server sniffs magic bytes and accepts both. The stream's tracks
 * are stopped explicitly on finish, otherwise the browser leaves the microphone
 * indicator on, which is alarming for someone who did not expect it.
 */

export function isSupported() {
  return !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia
            && typeof MediaRecorder !== 'undefined');
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
    if (!isSupported()) {
      throw new Error('This browser cannot record sound. Try uploading a file instead.');
    }
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
