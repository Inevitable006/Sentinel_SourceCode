// Encode a bounded recording as mono 16 kHz, signed 16-bit PCM WAV.
export function encodeWav(chunks: Float32Array[], sampleRate: number): Blob {
  const count = chunks.reduce((n, chunk) => n + chunk.length, 0);
  const input = new Float32Array(count);
  let offset = 0;
  for (const chunk of chunks) { input.set(chunk, offset); offset += chunk.length; }
  const length = Math.min(30 * 16000, Math.floor(count * 16000 / sampleRate));
  const buffer = new ArrayBuffer(44 + length * 2);
  const view = new DataView(buffer);
  const label = (at: number, value: string) => [...value].forEach((c, i) => view.setUint8(at + i, c.charCodeAt(0)));
  label(0, 'RIFF'); view.setUint32(4, 36 + length * 2, true); label(8, 'WAVE');
  label(12, 'fmt '); view.setUint32(16, 16, true); view.setUint16(20, 1, true);
  view.setUint16(22, 1, true); view.setUint32(24, 16000, true);
  view.setUint32(28, 32000, true); view.setUint16(32, 2, true); view.setUint16(34, 16, true);
  label(36, 'data'); view.setUint32(40, length * 2, true);
  const ratio = sampleRate / 16000;
  for (let i = 0; i < length; i++) {
    const start = Math.floor(i * ratio);
    const end = Math.min(count, Math.max(start + 1, Math.floor((i + 1) * ratio)));
    let sum = 0;
    for (let j = start; j < end; j++) sum += input[j];
    const value = Math.max(-1, Math.min(1, sum / (end - start)));
    view.setInt16(44 + i * 2, Math.round(value * (value < 0 ? 32768 : 32767)), true);
  }
  return new Blob([buffer], { type: 'audio/wav' });
}
