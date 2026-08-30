const { BasePlugin } = require('../base-plugin');
const si = require('systeminformation');
const { logger } = require('../../core/logger');

class SystemMonitorPlugin extends BasePlugin {
  constructor() {
    super('system-monitor', 'Provides real-time hardware diagnostics and system statistics.');
    
    this.registerTool({
      name: 'get_system_stats',
      description: 'Retrieves current system statistics including CPU usage, RAM utilization, and battery level.',
      parameters: {
        type: 'object',
        properties: {
          metrics: { 
            type: 'string', 
            description: 'Comma separated list of metrics to fetch (cpu, memory, battery, os). Leave empty for all.' 
          }
        }
      }
    }, this.getSystemStats);
  }

  async getSystemStats({ metrics = '' }) {
    logger.info('plugin', `Fetching system stats: ${metrics || 'all'}`);
    
    try {
      const result = {};
      const requested = metrics.toLowerCase();
      const fetchAll = !requested || requested === 'all';

      if (fetchAll || requested.includes('cpu')) {
        const cpuLoad = await si.currentLoad();
        const cpuTemp = await si.cpuTemperature();
        result.cpu = {
          usage_percent: Math.round(cpuLoad.currentLoad),
          temperature_c: cpuTemp.main || 'Unknown'
        };
      }

      if (fetchAll || requested.includes('memory')) {
        const mem = await si.mem();
        result.memory = {
          total_gb: (mem.total / 1024 / 1024 / 1024).toFixed(1),
          used_gb: (mem.active / 1024 / 1024 / 1024).toFixed(1),
          free_gb: (mem.available / 1024 / 1024 / 1024).toFixed(1),
          usage_percent: Math.round((mem.active / mem.total) * 100)
        };
      }

      if (fetchAll || requested.includes('battery')) {
        const battery = await si.battery();
        if (battery.hasBattery) {
          result.battery = {
            percent: battery.percent,
            is_charging: battery.isCharging
          };
        } else {
          result.battery = 'No battery detected (Desktop PC)';
        }
      }

      if (fetchAll || requested.includes('os')) {
        const os = await si.osInfo();
        result.os = `${os.distro} ${os.release} (${os.arch})`;
      }

      return { success: true, stats: result };
    } catch (err) {
      return { error: `Failed to fetch system stats: ${err.message}` };
    }
  }
}

module.exports = SystemMonitorPlugin;
