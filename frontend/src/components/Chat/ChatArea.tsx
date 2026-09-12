import React, { useState, useEffect, useRef } from 'react';
import { Send, Paperclip, Bot, User, Volume2, VolumeX } from 'lucide-react';
import './Chat.css';

interface Message {
  id: string;
  sender: 'user' | 'sentinel';
  text: string;
  timestamp: Date;
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
  const wsRef = useRef<WebSocket | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Initialize WebSocket connection
  useEffect(() => {
    const ws = new WebSocket('ws://127.0.0.1:8000/ws/chat');

    ws.onopen = () => setIsConnected(true);

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      if (data.type === 'reply') {
        setMessages(prev => [...prev, {
          id: Date.now().toString(),
          sender: 'sentinel',
          text: data.message,
          timestamp: new Date()
        }]);
      }
    };

    ws.onclose = () => setIsConnected(false);
    wsRef.current = ws;

    return () => ws.close();
  }, []);

  // Auto-scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSend = (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim()) return;

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
      wsRef.current.send(JSON.stringify({
        text: input,
        voice_enabled: voiceEnabled
      }));
    } else {
      setMessages(prev => [...prev, {
        id: (Date.now() + 1).toString(),
        sender: 'sentinel',
        text: 'Error: Connection to backend lost.',
        timestamp: new Date()
      }]);
    }

    setInput('');
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
        <form onSubmit={handleSend} className="input-form">
          <button type="button" className="action-btn" title="Attach file">
            <Paperclip size={20} />
          </button>
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Message Sentinel..."
            className="text-input"
          />
          <button type="submit" className="submit-btn" disabled={!input.trim()}>
            <Send size={18} />
          </button>
        </form>
      </div>
    </div>
  );
};

export default ChatArea;
