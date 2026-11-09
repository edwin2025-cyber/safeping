// Short alert tone made with the Web Audio API. No audio files.
// Browsers keep audio locked until the user clicks once, so unlockAudio()
// must run inside a click (the sound toggle or the Test sound button).

let ctx = null;

export function unlockAudio() {
  try {
    if (!ctx) {
      const AudioCtx = window.AudioContext || window.webkitAudioContext;
      if (!AudioCtx) return false;
      ctx = new AudioCtx();
    }
    if (ctx.state === "suspended") ctx.resume();
    return true;
  } catch {
    return false;
  }
}

function beep(start, frequency, length) {
  const osc = ctx.createOscillator();
  const gain = ctx.createGain();
  osc.type = "sine";
  osc.frequency.value = frequency;
  gain.gain.setValueAtTime(0.0001, start);
  gain.gain.exponentialRampToValueAtTime(0.25, start + 0.02);
  gain.gain.exponentialRampToValueAtTime(0.0001, start + length);
  osc.connect(gain).connect(ctx.destination);
  osc.start(start);
  osc.stop(start + length + 0.02);
}

export function playAlertTone() {
  if (!unlockAudio() || ctx.state !== "running") return false;
  const now = ctx.currentTime;
  beep(now, 880, 0.18);
  beep(now + 0.24, 660, 0.18);
  beep(now + 0.48, 880, 0.26);
  return true;
}
