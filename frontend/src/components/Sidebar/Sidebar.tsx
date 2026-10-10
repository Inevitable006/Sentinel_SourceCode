import React from 'react';
import { Settings, Database, Home, Shield, Lock, ListTodo, PieChart } from 'lucide-react';
import { apiPost, notifyLockStateChanged } from '../../lib/backend';
import './Sidebar.css';

interface SidebarProps {
  activeTab: string;
  setActiveTab: (tab: string) => void;
}

const NAV = [
  { id: 'console', label: 'Console', Icon: Home },
  { id: 'workspace', label: 'Workspace', Icon: ListTodo },
  { id: 'memory', label: 'Memory', Icon: Database },
  { id: 'portfolio', label: 'Portfolio', Icon: PieChart },
  { id: 'security', label: 'Security', Icon: Shield },
  { id: 'settings', label: 'Settings', Icon: Settings },
];

const Sidebar: React.FC<SidebarProps> = ({ activeTab, setActiveTab }) => {
  return (
    <aside className="sidebar glass-panel">
      <div className="sidebar-header">
        <div className="brand">
          <div className="logo-glow"></div>
          <h2>Sentinel</h2>
        </div>
        <span className="version">v1.0.0</span>
      </div>

      <nav className="nav-menu">
        {NAV.map(({ id, label, Icon }) => (
          <a
            key={id}
            href="#"
            className={`nav-item ${activeTab === id ? 'active' : ''}`}
            aria-current={activeTab === id ? 'page' : undefined}
            onClick={(e) => { e.preventDefault(); setActiveTab(id); }}
          >
            <Icon size={18} />
            <span>{label}</span>
          </a>
        ))}
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
