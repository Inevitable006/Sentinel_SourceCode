import React, { useState } from 'react';
import './Layout.css';
import Sidebar from '../Sidebar/Sidebar';
import ChatArea from '../Chat/ChatArea';
import SystemStatus from '../SystemStatus/SystemStatus';
import SettingsPanel from '../Settings/SettingsPanel';

const Layout: React.FC = () => {
  const [activeTab, setActiveTab] = useState('console');

  return (
    <div className="layout-container">
      <Sidebar activeTab={activeTab} setActiveTab={setActiveTab} />
      <main className="main-content">
        {activeTab === 'console' && <ChatArea />}
        {activeTab === 'settings' && <SettingsPanel />}
      </main>
      <SystemStatus />
    </div>
  );
};

export default Layout;
