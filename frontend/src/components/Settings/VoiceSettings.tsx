import React, { useEffect, useState } from 'react';
import { apiGet, apiPost } from '../../lib/backend';

type Voice = { id: string; name: string; gender: string };
type VoiceInfo = { voices: Voice[]; voice_id: string | null; rate: number; min_rate: number; max_rate: number };

const label = (v: Voice) => `${v.name.replace('Microsoft ', '')} (${v.gender === 'male' ? 'Male' : v.gender === 'female' ? 'Female' : 'Voice'})`;

// Choose the voice Sentinel speaks with (male or female) and how fast it talks.
const VoiceSettings: React.FC = () => {
  const [info, setInfo] = useState<VoiceInfo | null>(null);
  const [message, setMessage] = useState('');

  useEffect(() => {
    apiGet<VoiceInfo>('/api/voice/voices').then(setInfo).catch(e => setMessage(e.message));
  }, []);

  const save = async (change: { voice_id?: string; rate?: number }) => {
    try {
      setInfo(await apiPost<VoiceInfo>('/api/voice/voices', change));
      setMessage('Saved.');
    } catch (e) { setMessage(e instanceof Error ? e.message : 'Not saved.'); }
  };

  return (
    <div className="settings-section">
      <h3>Voice</h3>
      <p className="settings-desc">The voice Sentinel uses for spoken replies (turn Voice On in Chat). Voices come from Windows.</p>
      {info && info.voices.length === 0 && <p className="settings-desc">No Windows voices were found.</p>}
      {info && info.voices.length > 0 && (
        <>
          <select className="settings-dropdown" value={info.voice_id ?? ''} onChange={e => save({ voice_id: e.target.value })}>
            {info.voices.map(v => <option key={v.id} value={v.id}>{label(v)}</option>)}
          </select>
          <label className="settings-desc" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginTop: '0.5rem' }}>
            Speed
            <input type="range" min={info.min_rate} max={info.max_rate} step={10} value={info.rate}
                   onChange={e => setInfo({ ...info, rate: Number(e.target.value) })}
                   onMouseUp={() => save({ rate: info.rate })} onKeyUp={() => save({ rate: info.rate })} />
            {info.rate}
          </label>
          <button type="button" onClick={() => apiPost('/api/voice/voices/preview').catch(e => setMessage(e.message))}>Preview voice</button>
        </>
      )}
      <p className="settings-desc">{message}</p>
      <p className="settings-desc">More voices: Windows Settings → Time &amp; language → Speech → Add voices. Some newer voices may not be usable by Sentinel yet.</p>
    </div>
  );
};

export default VoiceSettings;
