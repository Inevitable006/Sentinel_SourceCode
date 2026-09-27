import React, { useState, useEffect, useRef } from 'react';
import { Send, Paperclip, Bot, User, Volume2, VolumeX } from 'lucide-react';
import './Chat.css';
import { notifyLockStateChanged } from '../../lib/backend';

interface Message {
  id: string;
  sender: 'user' | 'sentinel';
  text: string;
  timestamp: Date;
}

interface Confirmation {
  token: string;
  session_id: string;
  action_preview: { tool: string; purpose: string; risk: string; args: Record<string, unknown> };
}

const ChatArea: React.FC = () => {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: '1',
      sender: 'sentinel',
      text: 'Systems online. How can I assist you today?',
      timestamp: new Date()
    }
  ]);
  const [input, setInput] = useState('');
  const [isConnected, setIsConnected] = useState(false);
  const [voiceEnabled, setVoiceEnabled] = useState(true);
  const [modelLoadState, setModelLoadState] = useState<'unloaded'|'loading'|'loaded'|'failed'>('unloaded');
  const [loadErrorMsg, setLoadErrorMsg] = useState('');
  const [selectedImage, setSelectedImage] = useState<File | null>(null);
  const [status, setStatus] = useState('Connecting…');
  const [busy, setBusy] = useState(false);
  const [confirmation, setConfirmation] = useState<Confirmation | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [pinNeeded, setPinNeeded] = useState(false);
  const [approvalPin, setApprovalPin] = useState('');
  const streamIdRef = useRef<string | null>(null);
  const authRef = useRef({ port: 8000, token: '' });
  const wsRef = useRef<WebSocket | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const handleLoadModel = async () => {
    setModelLoadState('loading');
    setLoadErrorMsg('');
    try {
      let port = 8000;
      let token = "dev_fallback_token";

      // @ts-ignore
      if (window.sentinel?.auth) {
        // @ts-ignore
        port = await window.sentinel.auth.getBackendPort();
        // @ts-ignore
        token = await window.sentinel.auth.getSessionToken();
      }

      const response = await fetch(`http://127.0.0.1:${port}/api/models/load`, {
        method: 'POST',
        headers: {
          'X-Sentinel-Session': token
        }
      });

      if (response.ok) {
        setModelLoadState('loaded');
      } else {
        const errData = await response.json();
        setLoadErrorMsg(errData.detail || 'Failed to load model');
        setModelLoadState('failed');
      }
    } catch (e: any) {
      setLoadErrorMsg(e.message || 'Connection error');
      setModelLoadState('failed');
    }
  };

  // Initialize WebSocket connection
  useEffect(() => {
    let ws: WebSocket | undefined;
    let disposed = false;
    let retryTimer: ReturnType<typeof setTimeout> | undefined;
    let attempt = 0;

    // The Python backend starts a few seconds after the window opens, and may
    // restart after a crash. Keep retrying (1s, 2s, 4s, 8s, then every 10s)
    // instead of giving up after the first failed attempt.
    const scheduleReconnect = () => {
      if (disposed) return;
      const delay = Math.min(1000 * 2 ** attempt, 10000);
      attempt += 1;
      setStatus(`Waiting for Sentinel backend... retrying in ${Math.round(delay / 1000)}s`);
      retryTimer = setTimeout(() => {
        initWebSocket().catch(scheduleReconnect);
      }, delay);
    };

    const initWebSocket = async () => {
      let port = 8000;
      let token = "dev_fallback_token";

      // @ts-ignore
      if (window.sentinel?.auth) {
        // @ts-ignore
        port = await window.sentinel.auth.getBackendPort();
        // @ts-ignore
        token = await window.sentinel.auth.getSessionToken();
      }

      if (disposed) return;
      authRef.current = { port, token };
      // The session token goes in the subprotocol header, never in the URL (URLs end up in logs).
      ws = new WebSocket(`ws://127.0.0.1:${port}/ws/chat`, ['sentinel.v1', token]);

      ws.onopen = () => {
        attempt = 0;
        setIsConnected(true);
      };

      ws.onmessage = (event) => {
        if (disposed) return;
        try {
          const data = JSON.parse(event.data);
          if (data.type === 'reply_start') {
            streamIdRef.current = crypto.randomUUID();
            setBusy(true);
          } else if (data.type === 'reply_chunk' && typeof data.token === 'string') {
            const id = streamIdRef.current ?? crypto.randomUUID();
            streamIdRef.current = id;
            setMessages(prev => prev.some(msg => msg.id === id)
              ? prev.map(msg => msg.id === id ? { ...msg, text: msg.text + data.token } : msg)
              : [...prev, { id, sender: 'sentinel', text: data.token, timestamp: new Date() }]);
          } else if (data.type === 'reply_end') {
            streamIdRef.current = null;
          } else if (data.type === 'reply' || data.type === 'error') {
            setMessages(prev => [...prev, { id: crypto.randomUUID(), sender: 'sentinel', text: String(data.message), timestamp: new Date() }]);
            setBusy(false);
          } else if (data.type === 'status') {
            setStatus(String(data.message));
          } else if (data.type === 'state') {
            setStatus(String(data.state));
            setBusy(!['COMPLETED', 'CANCELLED', 'WAITING_FOR_PERMISSION'].includes(data.state));
          } else if (data.type === 'tool_confirmation_required') {
            setConfirmation(data.data);
            setPinNeeded(false);
            setApprovalPin('');
            setBusy(false);
          } else if (data.type === 'locked') {
            setStatus('Sentinel locked.');
            notifyLockStateChanged();
          }
        } catch {
          setStatus('Received an invalid response from the backend.');
        }
      };

      ws.onclose = () => {
        if (disposed) return;
        setIsConnected(false);
        setBusy(false);
        setConfirmation(null);
        streamIdRef.current = null;
        scheduleReconnect();
      };
      // onerror is always followed by onclose, which schedules the retry.
      ws.onerror = () => { if (!disposed) setStatus('Backend connection failed.'); };
      wsRef.current = ws;
    };

    initWebSocket().catch(scheduleReconnect);

    return () => {
      disposed = true;
      if (retryTimer) clearTimeout(retryTimer);
      ws?.close();
    };
  }, []);

  // Auto-scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSend = (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || busy || confirmation || confirming || !isConnected) return;

    // Add user message to UI
    const newUserMsg: Message = {
      id: Date.now().toString(),
      sender: 'user',
      text: input,
      timestamp: new Date()
    };
    setMessages(prev => [...prev, newUserMsg]);

    // Send to backend
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      const payload: any = {
        text: input,
        voice_enabled: voiceEnabled
      };

      if (selectedImage) {
        // We rely on Electron IPC to send absolute paths.
        // In this architecture, File.path gives the absolute path.
        // @ts-ignore
        payload.image_path = selectedImage.path || "";
      }

      wsRef.current.send(JSON.stringify(payload));
      setBusy(true);
      setStatus('Processing…');
    } else {
      setMessages(prev => [...prev, {
        id: (Date.now() + 1).toString(),
        sender: 'sentinel',
        text: 'Error: Connection to backend lost.',
        timestamp: new Date()
      }]);
    }

    setInput('');
    setSelectedImage(null);
  };

  const handleConfirm = async () => {
    if (!confirmation || confirming) return;
    const pending = confirmation;
    setConfirming(true);
    setConfirmation(null); // A single-use token must never be automatically retried.
    try {
      const { port, token } = authRef.current;
      const response = await fetch(`http://127.0.0.1:${port}/api/tools/confirm`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Sentinel-Session': token },
        body: JSON.stringify({ token: pending.token, session_id: pending.session_id,
          tool_name: pending.action_preview.tool, args: pending.action_preview.args,
          pin: approvalPin || undefined })
      });
      const result = await response.json();
      // PIN problems are answered before the action runs, so the approval can be offered again.
      if ([401, 403, 429].includes(response.status)) {
        const detail = (result && result.detail) || {};
        setConfirmation(pending);
        setPinNeeded(true);
        setApprovalPin('');
        setStatus(String(detail.message || 'Enter your PIN to approve this action.'));
        return;
      }
      if (!response.ok) {
        const detail = result && result.detail;
        throw new Error(typeof detail === 'string' ? detail : String((detail && detail.message) || 'Confirmation failed'));
      }
      setPinNeeded(false);
      setApprovalPin('');
      setMessages(prev => [...prev, { id: crypto.randomUUID(), sender: 'sentinel',
        text: result.status === 'success' ? String(result.data) : String(result.message || 'Action did not complete.'), timestamp: new Date() }]);
      setStatus(result.status === 'success' ? 'Action completed.' : 'Action did not complete.');
    } catch {
      setStatus('Unable to verify the action outcome. Check before requesting it again.');
    } finally {
      setConfirming(false);
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      setSelectedImage(e.target.files[0]);
    }
  };

  return (
    <div className="chat-container glass-panel">
      <div className="chat-header">
        <div className="model-info">
          <Bot size={18} className="model-icon" />
          <span>Core AI Processor</span>
          {isConnected ? (
            <span className="badge badge-green">Connected</span>
          ) : (
            <span className="badge badge-red">Disconnected</span>
          )}
          {modelLoadState === 'unloaded' && (
            <button className="badge badge-blue" onClick={handleLoadModel} style={{cursor: 'pointer', border: '1px solid currentColor', background: 'transparent', marginLeft: '0.5rem'}}>Load Local Model</button>
          )}
          {modelLoadState === 'loading' && (
            <span className="badge badge-blue" style={{marginLeft: '0.5rem'}}>Loading...</span>
          )}
          {modelLoadState === 'loaded' && (
            <span className="badge badge-green" style={{marginLeft: '0.5rem'}}>Model Ready</span>
          )}
          {modelLoadState === 'failed' && (
            <span className="badge badge-red" title={loadErrorMsg} style={{marginLeft: '0.5rem'}}>Load Failed</span>
          )}
        </div>
        <div className="voice-toggle" onClick={() => setVoiceEnabled(!voiceEnabled)} style={{ cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '0.5rem', color: voiceEnabled ? 'var(--accent-primary)' : 'var(--text-secondary)' }}>
          {voiceEnabled ? <Volume2 size={20} /> : <VolumeX size={20} />}
          <span style={{ fontSize: '0.85rem' }}>{voiceEnabled ? 'Voice On' : 'Voice Off'}</span>
        </div>
      </div>

      <div className="messages-area">
        {messages.map((msg) => (
          <div key={msg.id} className={`message-wrapper ${msg.sender}`}>
            <div className="message-avatar">
              {msg.sender === 'sentinel' ? <Bot size={20} /> : <User size={20} />}
            </div>
            <div className="message-content">
              <div className="message-bubble">{msg.text}</div>
              <div className="message-time">
                {msg.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
              </div>
            </div>
          </div>
        ))}
        <div ref={messagesEndRef} />
      </div>

      <div className="input-area">
        <div role="status" aria-live="polite">{status}</div>
        {confirmation && (
          <div role="group" aria-label="Action approval">
            <p>{confirmation.action_preview.purpose}</p>
            <p>Risk: {confirmation.action_preview.risk}</p>
            <pre style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{JSON.stringify(confirmation.action_preview.args, null, 2)}</pre>
            {pinNeeded && (
              <label htmlFor="approval-pin" style={{ display: 'flex', flexDirection: 'column', gap: '4px', margin: '6px 0' }}>
                <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>High-risk action: enter your PIN to approve</span>
                <input id="approval-pin" type="password" autoComplete="current-password" value={approvalPin}
                       onChange={(e) => setApprovalPin(e.target.value)} />
              </label>
            )}
            <button type="button" onClick={handleConfirm} disabled={confirming || !isConnected || (pinNeeded && !approvalPin)}>Approve action</button>
            <button type="button" onClick={() => { setConfirmation(null); setPinNeeded(false); setApprovalPin(''); setStatus('Action declined.'); }}>Decline</button>
          </div>
        )}
        {selectedImage && (
          <div className="image-preview" style={{ padding: '8px', display: 'flex', alignItems: 'center', gap: '8px', background: 'rgba(255,255,255,0.05)', borderRadius: '4px', marginBottom: '8px' }}>
            <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>Selected Image: {selectedImage.name}</span>
            <button type="button" onClick={() => setSelectedImage(null)} style={{ background: 'none', border: 'none', color: 'var(--accent-primary)', cursor: 'pointer', fontSize: '0.8rem' }}>Remove</button>
          </div>
        )}
        <form onSubmit={handleSend} className="input-form">
          <input
            type="file"
            accept="image/*"
            style={{ display: 'none' }}
            ref={fileInputRef}
            onChange={handleFileChange}
          />
          <button type="button" className="action-btn" title="Attach Image" onClick={() => fileInputRef.current?.click()}>
            <Paperclip size={20} />
          </button>
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Message Sentinel..."
            className="text-input"
          />
          <button type="submit" className="submit-btn" disabled={!input.trim() || busy || !!confirmation || confirming || !isConnected}>
            <Send size={18} />
          </button>
        </form>
      </div>
    </div>
  );
};

export default ChatArea;
