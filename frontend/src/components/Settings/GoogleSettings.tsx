import React, { useEffect, useState, useRef } from 'react';
import { apiGet, apiPost } from '../../lib/backend';
import { usePinAction } from '../Workspace/usePinAction';

type Status = { configured: boolean; connected: boolean; gmail: boolean; calendar: boolean };
type Mail = { id: string; subject: string; from: string; date: string; snippet: string };
type Event = { summary: string; start: string; end: string };
const base = '/api/workspace/google';

const GoogleSettings: React.FC = () => {
  const [status, setStatus] = useState<Status | null>(null);
  const [statusError, setStatusError] = useState(false);
  const [client, setClient] = useState<{ client_id: string; client_secret: string } | null>(null);
  const [url, setUrl] = useState('');
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const [activeOp, setActiveOp] = useState<string | null>(null);
  const [mail, setMail] = useState<Mail[]>([]);
  const [events, setEvents] = useState<Event[]>([]);
  const isMountedRef = useRef(true);
  const refreshRequestIdRef = useRef(0);

  const { run, prompt } = usePinAction((msg) => {
    if (isMountedRef.current) setMessage(msg);
  });

  const refresh = async () => {
    const reqId = ++refreshRequestIdRef.current;
    try {
      const s = await apiGet<Status>(`${base}/status`);
      if (refreshRequestIdRef.current === reqId) {
        setStatus(s);
        setStatusError(false);
      }
    } catch {
      if (refreshRequestIdRef.current === reqId) {
        setStatus(null);
        setStatusError(true);
        setMessage('Google connection status unavailable.');
      }
    }
  };

  useEffect(() => {
    isMountedRef.current = true;
    void refresh();
    return () => {
      isMountedRef.current = false;
      refreshRequestIdRef.current += 1;
    };
  }, []);

  const action = (opName: string, fn: (pin?: string) => Promise<void>) => {
    if (busy) return;
    setActiveOp(opName);
    setBusy(true);
    void run(async (pin) => {
      try {
        await fn(pin);
      } finally {
        if (isMountedRef.current) {
          setBusy(false);
          setActiveOp(null);
        }
      }
    });
  };

  const importClient = async (file?: File) => {
    if (!file) return;
    try {
      if (file.size > 16000) throw new Error('Choose the small Desktop app OAuth credentials JSON file.');
      const data = JSON.parse(await file.text()).installed;
      if (!data || typeof data.client_id !== 'string') {
        throw new Error('This must be a Desktop app OAuth credentials file.');
      }
      if (isMountedRef.current) {
        setClient({
          client_id: data.client_id,
          client_secret: typeof data.client_secret === 'string' ? data.client_secret : '',
        });
        setMessage('Credentials loaded locally. Save them to the encrypted vault to continue.');
      }
    } catch (e) {
      if (isMountedRef.current) {
        setClient(null);
        setMessage(e instanceof Error ? e.message : 'Could not read credentials.');
      }
    }
  };

  const isPending = busy || Boolean(prompt);

  const statusText = statusError
    ? 'Status unavailable'
    : status
    ? status.connected
      ? 'Connected'
      : status.configured
      ? 'Credentials saved; sign-in needed'
      : 'Not configured'
    : 'Checking connection…';

  return (
    <div className="settings-section">
      <h3>Gmail and Google Calendar</h3>
      <p className="settings-desc">
        Read inbox previews and the next seven days from your primary calendar when you press Refresh. Drafts stay in Workspace. This connection cannot send mail or change events.
      </p>
      <p className="settings-desc">
        Setup: enable Gmail API and Google Calendar API in your Google Cloud project, configure consent, and create a Desktop app OAuth client. Import its JSON file here; never paste credentials into chat.
      </p>

      <p className="settings-desc" role="status">
        Connection status: <strong>{statusText}</strong>
      </p>

      <div style={{ margin: '0.75rem 0' }}>
        <label htmlFor="google-oauth-file" style={{ display: 'block', marginBottom: '0.25rem' }}>
          Desktop OAuth credentials
        </label>
        <input
          id="google-oauth-file"
          type="file"
          accept=".json,application/json"
          disabled={isPending}
          aria-label="Upload desktop OAuth credentials JSON file"
          onChange={e => {
            void importClient(e.target.files?.[0]);
            e.target.value = '';
          }}
        />
      </div>

      <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', margin: '0.5rem 0' }}>
        {client && (
          <button
            type="button"
            disabled={isPending}
            onClick={() =>
              action('save_creds', async (pin) => {
                await apiPost(`${base}/configure`, { ...client, pin });
                if (isMountedRef.current) {
                  setClient(null);
                  setUrl('');
                  setMail([]);
                  setEvents([]);
                }
                await refresh();
                if (isMountedRef.current) setMessage('Saved in the encrypted vault.');
              })
            }
          >
            {activeOp === 'save_creds' ? 'Saving credentials…' : 'Save credentials'}
          </button>
        )}

        <button
          type="button"
          disabled={isPending || !status?.configured}
          onClick={() =>
            action('connect', async (pin) => {
              const result = await apiPost<{ authorization_url: string }>(`${base}/start`, { pin });
              if (isMountedRef.current) {
                setUrl(result.authorization_url);
                setMessage('Copy the sign-in link into your normal browser. It expires in five minutes.');
              }
            })
          }
        >
          {activeOp === 'connect' ? 'Connecting…' : status?.connected ? 'Reconnect Google' : 'Connect Google'}
        </button>

        <button
          type="button"
          disabled={isPending || !status?.configured}
          onClick={() =>
            action('disconnect', async (pin) => {
              await apiPost(`${base}/disconnect`, { pin });
              if (isMountedRef.current) {
                setClient(null);
                setUrl('');
                setMail([]);
                setEvents([]);
              }
              await refresh();
              if (isMountedRef.current) {
                setMessage('Local credentials removed. Revoke Sentinel in your Google Account to remove its Google-side grant.');
              }
            })
          }
        >
          {activeOp === 'disconnect' ? 'Disconnecting…' : 'Disconnect and remove credentials'}
        </button>
      </div>

      {url && (
        <div style={{ margin: '0.75rem 0' }}>
          <label htmlFor="google-auth-link" style={{ display: 'block', marginBottom: '0.25rem' }}>
            Google sign-in link
          </label>
          <textarea
            id="google-auth-link"
            readOnly
            rows={3}
            value={url}
            aria-label="Google authorization link"
            onFocus={e => e.target.select()}
            style={{ width: '100%', boxSizing: 'border-box' }}
          />
          <div style={{ display: 'flex', gap: '0.5rem', marginTop: '0.5rem' }}>
            <button
              type="button"
              disabled={isPending}
              onClick={() =>
                navigator.clipboard
                  .writeText(url)
                  .then(() => setMessage('Link copied. Open it in your browser.'))
                  .catch(() => setMessage('Select and copy the link above.'))
              }
            >
              Copy link
            </button>
            <button
              type="button"
              disabled={isPending}
              onClick={() =>
                action('finish', async (pin) => {
                  const s = await apiPost<Status>(`${base}/finish`, { pin });
                  if (isMountedRef.current) {
                    setStatus(s);
                    setUrl('');
                    setMessage('Connection saved. Refresh Gmail or Calendar below.');
                  }
                })
              }
            >
              {activeOp === 'finish' ? 'Finishing…' : 'Finish connection'}
            </button>
          </div>
        </div>
      )}

      <div style={{ display: 'flex', gap: '0.5rem', margin: '0.75rem 0', flexWrap: 'wrap' }}>
        <button
          type="button"
          disabled={isPending || !status?.gmail}
          onClick={() =>
            action('mail', async () => {
              const r = await apiPost<{ messages: Mail[]; more_available: boolean }>(`${base}/messages`);
              if (isMountedRef.current) {
                setMail(r.messages);
                setMessage(r.more_available ? 'Showing the first 10 inbox messages.' : `${r.messages.length} inbox messages.`);
              }
            })
          }
        >
          {activeOp === 'mail' ? 'Refreshing Gmail…' : 'Refresh Gmail'}
        </button>
        <button
          type="button"
          disabled={isPending || !status?.calendar}
          onClick={() =>
            action('calendar', async () => {
              const r = await apiPost<{ events: Event[]; more_available: boolean }>(`${base}/events`);
              if (isMountedRef.current) {
                setEvents(r.events);
                setMessage(
                  r.more_available
                    ? 'Showing the first 25 events in the next seven days.'
                    : `${r.events.length} events in the next seven days.`
                );
              }
            })
          }
        >
          {activeOp === 'calendar' ? 'Refreshing Calendar…' : 'Refresh Calendar'}
        </button>
      </div>

      {mail.length > 0 && (
        <div aria-label="Inbox message previews" style={{ margin: '0.5rem 0' }}>
          <h4>Inbox previews</h4>
          {mail.map(m => (
            <div key={m.id} style={{ marginBottom: '0.5rem', paddingBottom: '0.5rem', borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
              <strong>{m.subject || '(No subject)'}</strong>
              <p className="settings-desc" style={{ margin: '0.15rem 0' }}>
                {m.from} · {m.date}
              </p>
              <p className="settings-desc" style={{ margin: '0.15rem 0' }}>
                {m.snippet}
              </p>
            </div>
          ))}
        </div>
      )}

      {events.length > 0 && (
        <div aria-label="Upcoming calendar events" style={{ margin: '0.5rem 0' }}>
          <h4>Calendar events</h4>
          <ul className="settings-desc" style={{ paddingLeft: '1.25rem' }}>
            {events.map((e, i) => (
              <li key={i} style={{ margin: '0.25rem 0' }}>
                <strong>{e.summary}</strong> · {e.start} — {e.end}
              </li>
            ))}
          </ul>
        </div>
      )}

      {prompt}
      {message && <p role="status" aria-live="polite" className="settings-desc">{message}</p>}
    </div>
  );
};

export default GoogleSettings;
