import React from 'react';
import Layout from './components/Layout/Layout';
import UnlockGate from './components/Unlock/UnlockGate';

const App: React.FC = () => {
  return (
    <UnlockGate>
      <Layout />
    </UnlockGate>
  );
};

export default App;
