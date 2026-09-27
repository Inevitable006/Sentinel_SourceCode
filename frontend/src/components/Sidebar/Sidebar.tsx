import React from 'react';
import { Settings, Database, Home, Shield, Lock } from 'lucide-react';
import { apiPost, notifyLockStateChanged } from '../../lib/backend';
import './Sidebar.css';

interface SidebarProps {
  activeTab: string;
  setActiveTab: (tab: string) => void;
}

const Sidebar: React.FC<SidebarProps> = ({ activeTab, setActiveTab }) => {
  return (
    <aside className="sidebar glass-panel">
      <div className="sidebar-header">
        <div className="brand">
          <div className="logo-glow"></div>
          <h2>Sentinel</h2>
        </div>
        <span className="version">v0.1.0</span>
      </div>

      <nav className="nav-menu">
        <a
          href="#"
          className={`nav-item ${activeTab === 'console' ? 'active' : ''}`}
          onClick={(e) => { e.preventDefault(); setActiveTab('console'); }}
        >
          <Home size={18} />
          <span>Console</span>
        </a>
        <a href="#" className="nav-item">
          <Database size={18} />
          <span>Memory</span>
        </a>
        <a href="#" className="nav-item">
          <Shield size={18} />
          <span>Security</span>
        </a>
        <a
          href="#"
          className={`nav-item ${activeTab === 'settings' ? 'active' : ''}`}
          onClick={(e) => { e.preventDefault(); setActiveTab('settings'); }}
        >
          <Settings size={18} />
          <span>Settings</span>
        </a>
      </nav>

      <div className="sidebar-footer">
        <button
          type="button"
          className="lock-button"
          title="Lock Sentinel: closes the encrypted database until you enter your PIN"
          onClick={async () => {
            try { await apiPost('/api/lock'); } catch { /* the gate re-checks either way */ }
            notifyLockStateChanged();
          }}
        >
          <Lock size={16} />
          <span>Lock Sentinel</span>
        </button>
      </div>
    </aside>
  );
};

export default Sidebar;
