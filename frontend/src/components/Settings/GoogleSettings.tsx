import React, { useEffect, useState } from 'react';
import { apiGet, apiPost } from '../../lib/backend';
import { usePinAction } from '../Workspace/usePinAction';

type Status = { configured: boolean; connected: boolean; gmail: boolean; calendar: boolean };
type Mail = { id: string; subject: string; from: string; date: string; snippet: string };
type Event = { summary: string; start: string; end: string };
const base = '/api/workspace/google';

const GoogleSettings: React.FC = () => {
  const [status, setStatus] = useState<Status | null>(null);
  const [client, setClient] = useState<{ client_id: string; client_secret: string } | null>(null);
  const [url, setUrl] = useState('');
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const [mail, setMail] = useState<Mail[]>([]);
  const [events, setEvents] = useState<Event[]>([]);
  const { run, prompt } = usePinAction(setMessage);
  const refresh = async () => setStatus(await apiGet<Status>(`${base}/status`));
  useEffect(() => { refresh().catch(() => setMessage('Google connection status unavailable.')); }, []);

  const action = (fn: (pin?: string) => Promise<void>) => run(async pin => {
    setBusy(true);
    try { await fn(pin); } finally { setBusy(false); }
  });

  const importClient = async (file?: File) => {
    if (!file) return;
    try {
      if (file.size > 16000) throw new Error('Choose the small Desktop app OAuth credentials JSON file.');
      const data = JSON.parse(await file.text()).installed;
      if (!data || typeof data.client_id !== 'string') throw new Error('This must be a Desktop app OAuth credentials file.');
      setClient({ client_id: data.client_id, client_secret: typeof data.client_secret === 'string' ? data.client_secret : '' });
      setMessage('Credentials loaded locally. Save them to the encrypted vault to continue.');
    } catch (e) { setClient(null); setMessage(e instanceof Error ? e.message : 'Could not read credentials.'); }
  };

  return <div className="settings-section">
    <h3>Gmail and Google Calendar</h3>
    <p className="settings-desc">Read inbox previews and the next seven days from your primary calendar when you press Refresh. Drafts stay in Workspace. This connection cannot send mail or change events.</p>
    <p className="settings-desc">Setup: enable Gmail API and Google Calendar API in your Google Cloud project, configure consent, and create a Desktop app OAuth client. Import its JSON file here; never paste credentials into chat.</p>
    <p>{status ? (status.connected ? 'Connected' : status.configured ? 'Credentials saved; sign-in needed' : 'Not configured') : 'Checking connection…'}</p>
    <label>Desktop OAuth credentials <input type="file" accept=".json,application/json" disabled={busy} onChange={e => { void importClient(e.target.files?.[0]); e.target.value = ''; }} /></label>
    {client && <button type="button" disabled={busy} onClick={() => action(async pin => {
      await apiPost(`${base}/configure`, { ...client, pin }); setClient(null); setUrl(''); setMail([]); setEvents([]); await refresh(); setMessage('Saved in the encrypted vault.');
    })}>Save credentials</button>}
    <button type="button" disabled={busy || !status?.configured} onClick={() => action(async pin => {
      const result = await apiPost<{ authorization_url: string }>(`${base}/start`, { pin }); setUrl(result.authorization_url); setMessage('Copy the sign-in link into your normal browser. It expires in five minutes.');
    })}>Connect Google</button>
    {url && <div>
      <label>Google sign-in link <textarea readOnly rows={3} value={url} onFocus={e => e.target.select()} /></label>
      <button type="button" onClick={() => navigator.clipboard.writeText(url).then(() => setMessage('Link copied. Open it in your browser.')).catch(() => setMessage('Select and copy the link above.'))}>Copy link</button>
      <button type="button" disabled={busy} onClick={() => action(async pin => {
        setStatus(await apiPost<Status>(`${base}/finish`, { pin })); setUrl(''); setMessage('Connection saved. Refresh Gmail or Calendar below.');
      })}>Finish connection</button>
    </div>}
    <button type="button" disabled={busy || !status?.configured} onClick={() => action(async pin => {
      await apiPost(`${base}/disconnect`, { pin }); setUrl(''); setMail([]); setEvents([]); await refresh();
      setMessage('Local credentials removed. Revoke Sentinel in your Google Account to remove its Google-side grant.');
    })}>Disconnect and remove credentials</button>
    <div>
      <button type="button" disabled={busy || !status?.gmail} onClick={() => action(async () => {
        const r = await apiPost<{ messages: Mail[]; more_available: boolean }>(`${base}/messages`);
        setMail(r.messages); setMessage(r.more_available ? 'Showing the first 10 inbox messages.' : `${r.messages.length} inbox messages.`);
      })}>Refresh Gmail</button>
      <button type="button" disabled={busy || !status?.calendar} onClick={() => action(async () => {
        const r = await apiPost<{ events: Event[]; more_available: boolean }>(`${base}/events`);
        setEvents(r.events); setMessage(r.more_available ? 'Showing the first 25 events in the next seven days.' : `${r.events.length} events in the next seven days.`);
      })}>Refresh Calendar</button>
    </div>
    {mail.map(m => <div key={m.id}><strong>{m.subject || '(No subject)'}</strong><p>{m.from} · {m.date}</p><p>{m.snippet}</p></div>)}
    {events.map((e, i) => <p key={i}><strong>{e.summary}</strong> · {e.start} — {e.end}</p>)}
    {prompt}
    {message && <p role="status">{message}</p>}
  </div>;
};
export default GoogleSettings;
