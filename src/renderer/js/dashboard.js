/**
 * SENTINEL — Dashboard Controller
 * Real-time system monitoring: CPU, RAM, Disk, Network, GPU
 */

class Dashboard {
  constructor() {
    this.updateInterval = null;
    this.isActive = false;
    this.circumference = 2 * Math.PI * 52; // ring radius = 52
  }

  start() {
    if (this.isActive) return;
    this.isActive = true;
    this.update();
    this.updateInterval = setInterval(() => this.update(), 2000);
  }

  stop() {
    this.isActive = false;
    if (this.updateInterval) {
      clearInterval(this.updateInterval);
      this.updateInterval = null;
    }
  }

  async update() {
    if (!window.sentinel?.system) return;

    try {
      const stats = await window.sentinel.system.getStats();
      if (!stats) return;

      this._updateCPU(stats.cpu);
      this._updateMemory(stats.mem);
      this._updateDisk(stats.disk);
      this._updateNetwork(stats.networkStats);
      this._updateGPU(stats.graphics);
      this._updateOSInfo(stats.osInfo);
    } catch (err) {
      console.error('Dashboard update error:', err);
    }
  }

  _updateCPU(cpu) {
    if (!cpu) return;
    const load = Math.round(cpu.currentLoad);
    
    document.getElementById('cpu-value').textContent = `${load}%`;
    this._setRingProgress('cpu-ring', load);
    document.getElementById('cpu-label').textContent = `${cpu.cpus?.length || '?'} cores`;
  }

  _updateMemory(mem) {
    if (!mem) return;
    const usedGB = (mem.active / (1024 ** 3)).toFixed(1);
    const totalGB = (mem.total / (1024 ** 3)).toFixed(1);
    const percent = Math.round((mem.active / mem.total) * 100);

    document.getElementById('mem-value').textContent = `${percent}%`;
    this._setRingProgress('mem-ring', percent);
    document.getElementById('mem-label').textContent = `${usedGB} / ${totalGB} GB`;
  }

  _updateDisk(disk) {
    if (!disk || disk.length === 0) return;
    // Show primary disk (usually C:)
    const primary = disk[0];
    const usedGB = ((primary.used) / (1024 ** 3)).toFixed(0);
    const totalGB = ((primary.size) / (1024 ** 3)).toFixed(0);
    const percent = Math.round(primary.use);

    document.getElementById('disk-value').textContent = `${percent}%`;
    this._setRingProgress('disk-ring', percent);
    document.getElementById('disk-label').textContent = `${usedGB} / ${totalGB} GB`;
  }

  _updateNetwork(networkStats) {
    if (!networkStats || networkStats.length === 0) return;
    // Aggregate all interfaces
    let txSec = 0, rxSec = 0;
    networkStats.forEach(iface => {
      txSec += iface.tx_sec || 0;
      rxSec += iface.rx_sec || 0;
    });

    document.getElementById('net-upload').textContent = this._formatBytes(txSec) + '/s';
    document.getElementById('net-download').textContent = this._formatBytes(rxSec) + '/s';
    document.getElementById('net-label').textContent = `${networkStats.length} interface${networkStats.length > 1 ? 's' : ''}`;
  }

  _updateGPU(graphics) {
    if (!graphics?.controllers?.length) {
      document.getElementById('gpu-info').textContent = 'No GPU detected';
      return;
    }

    const gpu = graphics.controllers[0];
    const vramGB = gpu.vram ? (gpu.vram / 1024).toFixed(1) : '?';
    
    document.getElementById('gpu-info').innerHTML = `
      <strong>${gpu.model || 'Unknown GPU'}</strong><br>
      VRAM: ${gpu.vram || '?'} MB (${vramGB} GB) &nbsp;|&nbsp; 
      Driver: ${gpu.driverVersion || 'N/A'} &nbsp;|&nbsp;
      Bus: ${gpu.bus || 'N/A'}
    `;
  }

  _updateOSInfo(osInfo) {
    if (!osInfo) return;
    document.getElementById('os-info').textContent = 
      `${osInfo.distro} | ${osInfo.arch} | ${osInfo.hostname}`;
  }

  _setRingProgress(ringId, percent) {
    const ring = document.getElementById(ringId);
    if (!ring) return;
    const offset = this.circumference - (percent / 100) * this.circumference;
    ring.style.strokeDashoffset = offset;
  }

  _formatBytes(bytes) {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
  }
}

// Export globally
window.Dashboard = Dashboard;
