import React, { useState, useEffect } from 'react';
import './SettingsPanel.css';

interface ModelProfile {
  id: string;
  name: string;
  description: string;
}

const SettingsPanel: React.FC = () => {
  const [systemPrompt, setSystemPrompt] = useState('Loading...');
  const [models, setModels] = useState<ModelProfile[]>([]);
  const [activeModel, setActiveModel] = useState<string>('');
  const [localOnly, setLocalOnly] = useState(false);
  const [saving, setSaving] = useState(false);
  const [status, setStatus] = useState('');

  const getAuthInfo = async () => {
    let port = 8000;
    let token = "dev_fallback_token";
    // @ts-ignore
    if (window.sentinel?.auth) {
      // @ts-ignore
      port = await window.sentinel.auth.getBackendPort();
      // @ts-ignore
      token = await window.sentinel.auth.getSessionToken();
    }
    return { port, token };
  };

  useEffect(() => {
    const fetchSettings = async () => {
      try {
        const { port, token } = await getAuthInfo();
        const headers = { 'X-Sentinel-Session': token };
        
        // Fetch Settings (Prompt)
        const settingsRes = await fetch(`http://127.0.0.1:${port}/settings`, { headers });
        if (settingsRes.ok) {
          const data = await settingsRes.json();
          setSystemPrompt(data.system_prompt);
        }

        // Fetch Models
        const modelsRes = await fetch(`http://127.0.0.1:${port}/api/models`, { headers });
        if (modelsRes.ok) {
          const mData = await modelsRes.json();
          setModels(mData.profiles);
          setActiveModel(mData.active_profile);
        }
      } catch (err) {
        console.error(err);
        setSystemPrompt('Error loading settings.');
      }
    };
    
    fetchSettings();
  }, []);

  const handleSave = async () => {
    setSaving(true);
    setStatus('');
    
    try {
      const { port, token } = await getAuthInfo();
      const headers = {
        'Content-Type': 'application/json',
        'X-Sentinel-Session': token
      };

      const res = await fetch(`http://127.0.0.1:${port}/settings`, {
        method: 'POST',
        headers,
        body: JSON.stringify({ system_prompt: systemPrompt })
      });

      if (res.ok) {
        setStatus('Settings saved successfully!');
      } else {
        setStatus('Failed to save settings.');
      }
    } catch (err) {
      setStatus('Network Error.');
      console.error(err);
    } finally {
      setSaving(false);
      setTimeout(() => setStatus(''), 3000);
    }
  };

  const handleModelChange = async (e: React.ChangeEvent<HTMLSelectElement>) => {
    const newModel = e.target.value;
    setActiveModel(newModel);
    try {
      const { port, token } = await getAuthInfo();
      await fetch(`http://127.0.0.1:${port}/api/models/select`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Sentinel-Session': token
        },
        body: JSON.stringify({ profile_id: newModel })
      });
      setStatus('Model profile updated.');
      setTimeout(() => setStatus(''), 3000);
    } catch (e) {
      console.error(e);
    }
  };

  const handleClearMemory = async () => {
    if (!window.confirm("Are you sure you want to permanently clear all personal memory?")) return;
    
    try {
      const { port, token } = await getAuthInfo();
      const res = await fetch(`http://127.0.0.1:${port}/api/research/clear`, {
        method: 'POST',
        headers: { 'X-Sentinel-Session': token }
      });
      if (res.ok) {
        setStatus('Personal memory cleared.');
        setTimeout(() => setStatus(''), 3000);
      }
    } catch (e) {
      console.error(e);
    }
  };

  const handleLocalOnlyChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const isLocal = e.target.checked;
    setLocalOnly(isLocal);
    try {
      const { port, token } = await getAuthInfo();
      await fetch(`http://127.0.0.1:${port}/api/research/mode`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Sentinel-Session': token
        },
        body: JSON.stringify({ local_only: isLocal })
      });
      setStatus(`Local-Only Mode ${isLocal ? 'Enabled' : 'Disabled'}.`);
      setTimeout(() => setStatus(''), 3000);
    } catch (err) {
      console.error(err);
    }
  };

  return (
    <div className="settings-container glass-panel">
      <h2>Sentinel Configuration</h2>
      
      <div className="settings-section">
        <h3>Model Selection</h3>
        <p className="settings-desc">Choose the AI model profile to use for processing.</p>
        <select value={activeModel} onChange={handleModelChange} className="settings-dropdown">
          {models.map(m => (
            <option key={m.id} value={m.id}>{m.name} ({m.description})</option>
          ))}
        </select>
      </div>

      <div className="settings-section">
        <h3>Privacy & Constraints</h3>
        <label className="settings-toggle">
          <input 
            type="checkbox" 
            checked={localOnly} 
            onChange={handleLocalOnlyChange} 
          />
          <span className="toggle-label">Strict Local-Only Mode (Disables Web/Network Skills)</span>
        </label>
        
        <div style={{marginTop: '1rem'}}>
          <button className="save-btn" style={{backgroundColor: 'var(--accent-red)'}} onClick={handleClearMemory}>
            Clear Personal Memory
          </button>
          <p className="settings-desc" style={{marginTop: '0.5rem', fontSize: '0.8rem'}}>
            Permanently deletes all explicitly remembered facts.
          </p>
        </div>
      </div>

      <div className="settings-section">
        <h3>Personality & Core Instructions (System Prompt)</h3>
        <p className="settings-desc">
          This prompt dictates how Sentinel behaves. It is injected into the AI's context window before every conversation.
        </p>
        
        <textarea 
          className="prompt-editor"
          value={systemPrompt}
          onChange={(e) => setSystemPrompt(e.target.value)}
          rows={10}
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
