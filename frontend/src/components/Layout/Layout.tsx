import React, { useState } from 'react';
import './Layout.css';
import Sidebar from '../Sidebar/Sidebar';
import ChatArea from '../Chat/ChatArea';
import SystemStatus from '../SystemStatus/SystemStatus';
import SettingsPanel from '../Settings/SettingsPanel';
import Workspace from '../Workspace/Workspace';
import MemoryView from '../Workspace/MemoryView';
import SecurityView from '../Workspace/SecurityView';
import Portfolio from '../Portfolio/Portfolio';
import Briefing from '../Briefing/Briefing';

const Layout: React.FC = () => {
  const [activeTab, setActiveTab] = useState('today');
  const [resumeRequest, setResumeRequest] = useState<{ threadId: string; nonce: number } | null>(null);

  return (
    <div className="layout-container">
      <Sidebar activeTab={activeTab} setActiveTab={setActiveTab} />
      <main className="main-content">
        {/* The chat stays mounted while other views are open, so switching tabs keeps the conversation. */}
        <div style={{ display: activeTab === 'console' ? 'contents' : 'none' }}>
          <ChatArea resumeRequest={resumeRequest} />
        </div>
        {activeTab === 'workspace' && <Workspace />}
        {activeTab === 'memory' && (
          <MemoryView onResume={(threadId) => { setResumeRequest({ threadId, nonce: Date.now() }); setActiveTab('console'); }} />
        )}
        {activeTab === 'today' && <Briefing go={setActiveTab} />}
        {activeTab === 'portfolio' && <Portfolio />}
        {activeTab === 'security' && <SecurityView />}
        {activeTab === 'settings' && <SettingsPanel />}
      </main>
      <SystemStatus />
    </div>
  );
};

export default Layout;
