"use strict";
// Both file uploads and extracted audio enter here as Blobs. Nothing is uploaded.
window.audioAnalysis = (() => {
  const SR = 22050, MAX_SECONDS = 1200, MAX_BYTES = 128 * 1024 * 1024;
  const workerURL = new URL('analysis-worker.js', document.currentScript.src);
  let worker, nextId = 0, cachedBlob, decoded;
  const pending = new Map();

  function stop(message = 'Analysis stopped. Please try again.') {
    worker?.terminate();
    worker = null;
    for (const job of pending.values()) { clearTimeout(job.timer); job.reject(new Error(message)); }
    pending.clear();
  }

  async function decode(blob) {
    if (!blob.size) throw new Error('The audio file is empty.');
    if (blob.size > MAX_BYTES) throw new Error('Audio files must be at most 128 MiB.');
    // Offline contexts do not request microphone access or start playback.
    const context = new OfflineAudioContext(1, 1, SR);
    let audio;
    try { audio = await context.decodeAudioData(await blob.arrayBuffer()); }
    catch { throw new Error('Cannot decode this audio. Try WAV, MP3, or a browser-supported audio file.'); }
    if (audio.duration > MAX_SECONDS) throw new Error('Audio must be at most 20 minutes long.');
    const mono = new Float32Array(audio.length);
    // Match FFmpeg's equal-power stereo-to-mono coefficients.
    const gain = audio.numberOfChannels === 2 ? Math.SQRT1_2 : 1 / audio.numberOfChannels;
    for (let channel = 0; channel < audio.numberOfChannels; channel++) {
      const samples = audio.getChannelData(channel);
      for (let i = 0; i < mono.length; i++) mono[i] += samples[i] * gain;
    }
    return mono;
  }

  async function analyzeAudio(blob, params, progress = () => {}) {
    if (cachedBlob !== blob || !decoded) {
      cachedBlob = blob;
      progress('Decoding audio…');
      decoded = decode(blob);
      const attempt = decoded;
      attempt.catch(() => { if (decoded === attempt) decoded = null; });
    }
    const pcm = await decoded;
    if (cachedBlob !== blob) throw new Error('Audio selection changed.');
    progress('Loading analyzer and detecting strokes…');
    if (!worker) {
      worker = new Worker(workerURL, { type: 'module' });
      const activeWorker = worker;
      worker.onerror = () => {
        if (worker === activeWorker) stop('The analyzer could not load. Check your connection and try again.');
      };
      worker.onmessageerror = () => {
        if (worker === activeWorker) stop('The analyzer returned an unreadable result. Please try again.');
      };
      worker.onmessage = ({data}) => {
        if (worker !== activeWorker) return;
        const job = pending.get(data.id);
        if (!job) return;
        pending.delete(data.id);
        clearTimeout(job.timer);
        if (data.error) {
          job.reject(new Error(data.error));
          // Failed module imports are cached by the worker. Retry in a fresh one.
          stop('The analyzer failed. Please try again.');
        }
        else job.resolve(data.result);
      };
    }
    // Keep the decoded PCM for sensitivity changes; transfer only a working copy.
    const samples = pcm.slice(), id = ++nextId;
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => stop('Analysis timed out. Try a shorter file.'), 300000);
      pending.set(id, {resolve, reject, timer});
      worker.postMessage({id, samples, params}, [samples.buffer]);
    });
  }

  function reset() {
    cachedBlob = decoded = null;
    if (pending.size) stop("Audio selection changed.");
  }
  function dispose() { reset(); stop(); }
  return {analyzeAudio, reset, dispose};
})();
