import { useCallback, useEffect, useRef, useState } from 'react';
import { Mic, Square, X } from 'lucide-react';
import { apiGet, backendInfo, LOCK_EVENT, notifyLockStateChanged } from '../../lib/backend';
import { encodeWav } from '../../lib/audio';

type Mode = 'idle' | 'starting' | 'recording' | 'transcribing';
type Props = { disabled: boolean; onTranscript: (text: string) => void; onActive: (active: boolean) => void };

export default function Dictation(props: Props) {
  const [mode, setMode] = useState<Mode>('idle');
  const [message, setMessage] = useState('Dictate locally. Review the text before sending.');
  const [seconds, setSeconds] = useState(0);
  const callbacks = useRef(props); callbacks.current = props;
  const run = useRef(0);
  const currentMode = useRef<Mode>('idle');
  const capture = useRef<{ stream?: MediaStream; context?: AudioContext; source?: MediaStreamAudioSourceNode;
    processor?: ScriptProcessorNode; mute?: GainNode; timer?: number; chunks: Float32Array[]; count: number }>({ chunks: [], count: 0 });
  const request = useRef<AbortController | null>(null);

  const release = useCallback(() => {
    const c = capture.current;
    window.clearInterval(c.timer);
    if (c.processor) c.processor.onaudioprocess = null;
    c.source?.disconnect(); c.processor?.disconnect(); c.mute?.disconnect();
    c.stream?.getTracks().forEach(track => track.stop());
    if (c.context && c.context.state !== 'closed') void c.context.close().catch(() => {});
    capture.current = { chunks: [], count: 0 };
  }, []);

  const changeMode = (next: Mode) => {
    currentMode.current = next; setMode(next); callbacks.current.onActive(next !== 'idle');
  };
  const cancel = useCallback(() => {
    run.current++; request.current?.abort(); request.current = null; release();
    currentMode.current = 'idle'; setMode('idle'); callbacks.current.onActive(false);
    setMessage('Dictation cancelled. Recording discarded.');
  }, [release]);

  useEffect(() => {
    const hide = () => { if (document.hidden && currentMode.current !== 'idle') cancel(); };
    window.addEventListener(LOCK_EVENT, cancel);
    document.addEventListener('visibilitychange', hide);
    return () => {
      run.current++; request.current?.abort(); release();
      window.removeEventListener(LOCK_EVENT, cancel);
      document.removeEventListener('visibilitychange', hide);
    };
  }, [cancel, release]);
  useEffect(() => { if (props.disabled && currentMode.current !== 'idle') cancel(); }, [props.disabled, cancel]);

  const finish = async () => {
    if (currentMode.current !== 'recording') return;
    const id = run.current;
    const c = capture.current;
    const wav = encodeWav(c.chunks, c.context!.sampleRate);
    release(); changeMode('transcribing'); setMessage('Transcribing on this computer…');
    const controller = new AbortController(); request.current = controller;
    try {
      const { port, token } = await backendInfo();
      if (run.current !== id) return;
      const response = await fetch(`http://127.0.0.1:${port}/api/voice/transcribe`, {
        method: 'POST', headers: { 'X-Sentinel-Session': token, 'Content-Type': 'audio/wav' },
        body: wav, signal: controller.signal,
      });
      const result = await response.json();
      if (run.current !== id) return;
      if (response.status === 423) notifyLockStateChanged();
      if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : 'Dictation failed. Try again.');
      if (typeof result.text !== 'string') throw new Error('No transcript was returned.');
      if (result.text.trim()) {
        callbacks.current.onTranscript(result.text.trim());
        setMessage('Transcript added. Review and edit it, then press Send.');
      } else setMessage('No speech detected. Try speaking closer to the microphone.');
    } catch (error) {
      if (run.current === id) setMessage(error instanceof Error ? error.message : 'Dictation failed.');
    } finally {
      if (run.current === id) { request.current = null; changeMode('idle'); }
    }
  };

  const start = async () => {
    if (props.disabled || currentMode.current !== 'idle') return;
    const id = ++run.current;
    changeMode('starting'); setMessage('Checking local dictation…');
    try {
      const status = await apiGet<{ available: boolean; reason: string | null }>('/api/voice/status');
      if (run.current !== id) return;
      if (!status.available) throw new Error(status.reason || 'Local dictation is unavailable.');
      if (!navigator.mediaDevices?.getUserMedia) throw new Error('Microphone recording is unavailable in this window.');
      setMessage('Allow microphone access to begin recording.');
      const stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true }, video: false });
      if (run.current !== id) { stream.getTracks().forEach(t => t.stop()); return; }
      const c = capture.current; c.stream = stream;
      const context = new AudioContext(); c.context = context;
      await context.resume();
      if (run.current !== id) return;
      c.source = context.createMediaStreamSource(stream);
      c.processor = context.createScriptProcessor(4096, 1, 1);
      c.mute = context.createGain(); c.mute.gain.value = 0;
      c.source.connect(c.processor); c.processor.connect(c.mute); c.mute.connect(context.destination);
      c.processor.onaudioprocess = event => {
        if (currentMode.current !== 'recording') return;
        const remaining = Math.floor(context.sampleRate * 30) - c.count;
        const samples = event.inputBuffer.getChannelData(0).slice(0, remaining);
        c.chunks.push(samples); c.count += samples.length;
        if (c.count >= context.sampleRate * 30) void finish();
      };
      stream.getAudioTracks().forEach(track => { track.onended = cancel; });
      setSeconds(0); changeMode('recording'); setMessage('Recording locally — stop when finished (30 seconds maximum).');
      const began = Date.now();
      c.timer = window.setInterval(() => {
        setSeconds(Math.min(30, Math.floor((Date.now() - began) / 1000)));
        if (Date.now() - began >= 30000) void finish();
      }, 250);
    } catch (error) {
      if (run.current !== id) return;
      release(); changeMode('idle');
      setMessage(error instanceof DOMException && error.name === 'NotAllowedError'
        ? 'Microphone access was denied. Enable it in Windows privacy settings and try again.'
        : error instanceof Error ? error.message : 'Could not start the microphone.');
    }
  };

  return <div className="dictation-controls">
    <button type="button" className="action-btn" onClick={() => mode === 'recording' ? void finish() : void start()}
      disabled={props.disabled || mode === 'starting' || mode === 'transcribing'}
      aria-label={mode === 'recording' ? 'Stop recording and transcribe' : 'Dictate a message'}>
      {mode === 'recording' ? <Square size={17} /> : <Mic size={17} />}
      <span>{mode === 'recording' ? `Stop · ${seconds}s` : mode === 'transcribing' ? 'Transcribing…' : 'Dictate'}</span>
    </button>
    {mode !== 'idle' && <button type="button" className="action-btn" onClick={cancel} aria-label="Cancel dictation"><X size={17} />Cancel</button>}
    <span role="status" aria-live="polite" className="dictation-status">{message}</span>
  </div>;
}
