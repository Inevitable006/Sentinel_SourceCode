import React, { useEffect, useState, useRef } from 'react';
import { apiGet, apiPost } from '../../lib/backend';

type Voice = { id: string; name: string; gender: string };
type VoiceInfo = { voices: Voice[]; voice_id: string | null; rate: number; min_rate: number; max_rate: number };

const label = (v: Voice) => `${v.name.replace('Microsoft ', '')} (${v.gender === 'male' ? 'Male' : v.gender === 'female' ? 'Female' : 'Voice'})`;

// Choose the voice Sentinel speaks with (male or female) and how fast it talks.
const VoiceSettings: React.FC = () => {
  const [info, setInfo] = useState<VoiceInfo | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [previewing, setPreviewing] = useState(false);
  const [message, setMessage] = useState('');
  const isMountedRef = useRef(true);
  const loadRequestIdRef = useRef(0);
  const saveRequestIdRef = useRef(0);

  useEffect(() => {
    isMountedRef.current = true;
    const reqId = ++loadRequestIdRef.current;
    setLoading(true);
    setLoadError(null);
    apiGet<VoiceInfo>('/api/voice/voices')
      .then(r => {
        if (loadRequestIdRef.current === reqId) {
          setInfo(r);
          setLoadError(null);
          setLoading(false);
        }
      })
      .catch(e => {
        if (loadRequestIdRef.current === reqId) {
          setInfo(null); // Clear stale voice info on load failure
          const errText = e instanceof Error ? e.message : 'Could not load voices.';
          setLoadError(errText);
          setMessage(errText);
          setLoading(false);
        }
      });
    return () => {
      isMountedRef.current = false;
      loadRequestIdRef.current += 1;
      saveRequestIdRef.current += 1;
    };
  }, []);

  const save = async (change: { voice_id?: string; rate?: number }) => {
    if (saving) return;
    const reqId = ++saveRequestIdRef.current;
    setSaving(true);
    try {
      const updated = await apiPost<VoiceInfo>('/api/voice/voices', change);
      if (saveRequestIdRef.current === reqId) {
        setInfo(updated);
        setMessage('Saved.');
      }
    } catch (e) {
      if (saveRequestIdRef.current === reqId) {
        setMessage(e instanceof Error ? e.message : 'Not saved.');
      }
    } finally {
      if (saveRequestIdRef.current === reqId) {
        setSaving(false);
      }
    }
  };

  const preview = async () => {
    if (previewing || saving) return;
    setPreviewing(true);
    try {
      await apiPost('/api/voice/voices/preview');
    } catch (e) {
      if (isMountedRef.current) {
        setMessage(e instanceof Error ? e.message : 'Could not preview voice.');
      }
    } finally {
      if (isMountedRef.current) {
        setPreviewing(false);
      }
    }
  };

  return (
    <div className="settings-section">
      <h3>Voice</h3>
      <p className="settings-desc">The voice Sentinel uses for spoken replies (turn Voice On in Chat). Voices come from Windows.</p>
      {loading && <p className="settings-desc" role="status">Loading Windows voices…</p>}
      {!loading && loadError && (
        <p className="settings-desc" role="alert">
          Failed to load voices: {loadError}
        </p>
      )}
      {!loading && !loadError && info && info.voices.length === 0 && <p className="settings-desc">No Windows voices were found.</p>}
      {!loading && !loadError && info && info.voices.length > 0 && (
        <>
          <label htmlFor="voice-select" className="settings-desc" style={{ display: 'block', marginBottom: '0.25rem' }}>
            Voice
          </label>
          <select
            id="voice-select"
            className="settings-dropdown"
            value={info.voice_id ?? ''}
            disabled={saving}
            onChange={e => save({ voice_id: e.target.value })}
            aria-label="Voice selection"
          >
            {info.voices.map(v => <option key={v.id} value={v.id}>{label(v)}</option>)}
          </select>
          <label className="settings-desc" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginTop: '0.5rem' }}>
            Speed
            <input
              type="range"
              min={info.min_rate}
              max={info.max_rate}
              step={10}
              value={info.rate}
              disabled={saving}
              aria-label="Speech speed"
              onChange={e => setInfo({ ...info, rate: Number(e.target.value) })}
              onMouseUp={() => save({ rate: info.rate })}
              onKeyUp={e => { if (['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'Home', 'End', 'PageUp', 'PageDown'].includes(e.key)) save({ rate: info.rate }); }}
            />
            {info.rate}
          </label>
          <button
            type="button"
            disabled={previewing || saving}
            onClick={() => void preview()}
            aria-label="Preview currently selected voice"
          >
            {previewing ? 'Playing preview…' : 'Preview voice'}
          </button>
        </>
      )}
      {message && <p className="settings-desc" role="status" aria-live="polite">{message}</p>}
      <p className="settings-desc">More voices: Windows Settings → Time &amp; language → Speech → Add voices. Some newer voices may not be usable by Sentinel yet.</p>
    </div>
  );
};

export default VoiceSettings;
