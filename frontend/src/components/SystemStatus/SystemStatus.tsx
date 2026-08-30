import React from 'react';
import { Cpu, HardDrive, Wifi, Activity } from 'lucide-react';
import './SystemStatus.css';

const SystemStatus: React.FC = () => {
  return (
    <aside className="system-status glass-panel">
      <div className="status-header">
        <h3>System Telemetry</h3>
        <Activity size={16} className="icon-pulse" />
      </div>

      <div className="telemetry-widgets">
        {/* Core Processing Widget */}
        <div className="widget">
          <div className="widget-header">
            <Cpu size={16} />
            <span>AI Core Processor</span>
          </div>
          <div className="widget-body">
            <div className="metric">
              <span className="label">Status</span>
              <span className="value success">Active</span>
            </div>
            <div className="metric">
              <span className="label">Model</span>
              <span className="value">Qwen-1.5B (GGUF)</span>
            </div>
            <div className="metric">
              <span className="label">Inference</span>
              <span className="value">CPU-only (AVX2)</span>
            </div>
            <div className="progress-bar-container">
              <div className="progress-label">
                <span>Load</span>
                <span>24%</span>
              </div>
              <div className="progress-bg">
                <div className="progress-fill" style={{ width: '24%' }}></div>
              </div>
            </div>
          </div>
        </div>

        {/* Memory Widget */}
        <div className="widget">
          <div className="widget-header">
            <HardDrive size={16} />
            <span>System Memory</span>
          </div>
          <div className="widget-body">
            <div className="progress-bar-container">
              <div className="progress-label">
                <span>RAM Usage</span>
                <span>4.2 / 16.0 GB</span>
              </div>
              <div className="progress-bg">
                <div className="progress-fill warning" style={{ width: '26%' }}></div>
              </div>
            </div>
            <div className="progress-bar-container">
              <div className="progress-label">
                <span>VRAM (Shared)</span>
                <span>1.1 / 2.0 GB</span>
              </div>
              <div className="progress-bg">
                <div className="progress-fill danger" style={{ width: '55%' }}></div>
              </div>
            </div>
          </div>
        </div>

        {/* Network Widget */}
        <div className="widget">
          <div className="widget-header">
            <Wifi size={16} />
            <span>Backend Connectivity</span>
          </div>
          <div className="widget-body">
            <div className="metric">
              <span className="label">API Gateway</span>
              <span className="value success">21ms</span>
            </div>
            <div className="metric">
              <span className="label">WebSocket</span>
              <span className="value success">Connected</span>
            </div>
          </div>
        </div>
      </div>
    </aside>
  );
};

export default SystemStatus;
