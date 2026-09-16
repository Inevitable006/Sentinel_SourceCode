import React, { useState, useEffect } from 'react';
import './SettingsPanel.css';

const SettingsPanel: React.FC = () => {
  const [systemPrompt, setSystemPrompt] = useState('Loading...');
  const [saving, setSaving] = useState(false);
  const [status, setStatus] = useState('');

  useEffect(() => {
    const fetchSettings = async () => {
      let port = 8000;
      // @ts-ignore
      if (window.sentinel?.auth) {
        // @ts-ignore
        port = await window.sentinel.auth.getBackendPort();
      }
      
      fetch(`http://127.0.0.1:${port}/settings`)
        .then(res => res.json())
        .then(data => {
          setSystemPrompt(data.system_prompt);
        })
        .catch(err => {
          console.error(err);
          setSystemPrompt('Error loading settings.');
        });
    };
    
    fetchSettings();
  }, []);

  const handleSave = async () => {
    setSaving(true);
    setStatus('');
    
    let port = 8000;
    // @ts-ignore
    if (window.sentinel?.auth) {
      // @ts-ignore
      port = await window.sentinel.auth.getBackendPort();
    }
    
    fetch(`http://127.0.0.1:${port}/settings`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ system_prompt: systemPrompt })
    })
    .then(res => res.json())
    .then(() => {
      setStatus('Settings saved successfully!');
      setTimeout(() => setStatus(''), 3000);
    })
    .catch(err => {
      setStatus('Failed to save settings.');
      console.error(err);
    })
    .finally(() => {
      setSaving(false);
    });
  };

  return (
    <div className="settings-container glass-panel">
      <h2>Sentinel Configuration</h2>
      
      <div className="settings-section">
        <h3>Personality & Core Instructions (System Prompt)</h3>
        <p className="settings-desc">
          This prompt dictates how Sentinel behaves. It is injected into the AI's context window before every conversation.
        </p>
        
        <textarea 
          className="prompt-editor"
          value={systemPrompt}
          onChange={(e) => setSystemPrompt(e.target.value)}
          rows={12}
        />
        
        <div className="settings-actions">
          <span className="status-msg">{status}</span>
          <button 
            className="save-btn" 
            onClick={handleSave} 
            disabled={saving}
          >
            {saving ? 'Saving...' : 'Save Configuration'}
          </button>
        </div>
      </div>
    </div>
  );
};

export default SettingsPanel;
