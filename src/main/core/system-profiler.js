/**
 * SENTINEL — System Profiler
 * Detects hardware capabilities and generates a capability profile.
 * 
 * The profile determines:
 * - Which AI model SENTINEL should use
 * - Whether to enable GPU acceleration
 * - UI animation complexity
 * - Monitoring poll frequency
 * - Memory allocation for AI inference
 * 
 * Capability Tiers:
 *   "minimal"  → <4GB RAM, no GPU — Fallback AI only
 *   "low"      → 4-8GB RAM, integrated GPU — Tiny models (0.5B)
 *   "medium"   → 8-16GB RAM, basic GPU — Small models (1-3B)
 *   "high"     → 16-32GB RAM, dedicated GPU — Medium models (3-7B)
 *   "extreme"  → 32GB+ RAM, powerful GPU — Large models (7B+)
 */

const si = require('systeminformation');
const fs = require('fs');
const os = require('os');
const { appPaths } = require('./app-paths');
const { logger } = require('./logger');

// AI model recommendations per tier
const MODEL_RECOMMENDATIONS = {
  minimal: {
    ollama: null,                    // Don't run Ollama
    transformers: null,              // Don't run Transformers.js
    mode: 'fallback',
    reason: 'Insufficient hardware for local AI'
  },
  low: {
    ollama: ['qwen2.5:0.5b', 'tinyllama'],
    transformers: 'onnx-community/Qwen2.5-0.5B-Instruct',
    mode: 'ollama',
    reason: 'Limited RAM — using smallest available model'
  },
  medium: {
    ollama: ['qwen2.5:1.5b', 'llama3.2:1b', 'phi3:mini', 'qwen2.5:0.5b'],
    transformers: 'onnx-community/Qwen2.5-0.5B-Instruct',
    mode: 'ollama',
    reason: 'Moderate hardware — using efficient model'
  },
  high: {
    ollama: ['qwen2.5:3b', 'llama3.2:3b', 'phi3:mini', 'gemma2:2b', 'qwen2.5:1.5b'],
    transformers: 'onnx-community/Qwen2.5-0.5B-Instruct',
    mode: 'ollama',
    reason: 'Strong hardware — using capable model'
  },
  extreme: {
    ollama: ['qwen2.5:7b', 'llama3.1:8b', 'qwen2.5:3b', 'llama3.2:3b'],
    transformers: 'onnx-community/Qwen2.5-0.5B-Instruct',
    mode: 'ollama',
    reason: 'Powerful hardware — using large model'
  }
};

// UI settings per tier
const UI_RECOMMENDATIONS = {
  minimal:  { animationLevel: 'none',    monitoringIntervalMs: 5000 },
  low:      { animationLevel: 'reduced', monitoringIntervalMs: 3000 },
  medium:   { animationLevel: 'full',    monitoringIntervalMs: 2000 },
  high:     { animationLevel: 'full',    monitoringIntervalMs: 2000 },
  extreme:  { animationLevel: 'full',    monitoringIntervalMs: 1000 }
};

class SystemProfiler {
  constructor() {
    this.profile = null;
    this.isProfiled = false;
  }

  /**
   * Run full system profiling. This is an expensive operation — 
   * results are cached to disk after first run.
   * 
   * @param {boolean} [forceRefresh=false] - Force re-profiling even if cached
   * @returns {Object} Complete system profile with capability tier
   */
  async profile_system(forceRefresh = false) {
    const timer = logger.startTimer('System profiling');

    // Check for cached profile
    if (!forceRefresh && this._loadCachedProfile()) {
      timer.stop({ cached: true, tier: this.profile.tier });
      return this.profile;
    }

    logger.info('system', 'Running full system profile...');

    try {
      // Gather all hardware info in parallel
      const [cpuInfo, cpuSpeed, memInfo, diskInfo, gpuInfo, osInfo, networkInfo] = 
        await Promise.all([
          si.cpu(),
          si.cpuCurrentSpeed(),
          si.mem(),
          si.diskLayout(),
          si.graphics(),
          si.osInfo(),
          si.networkInterfaces()
        ]);

      // Build the profile
      this.profile = {
        // ─── Timestamps ───
        profiledAt: new Date().toISOString(),
        version: '1.0.0',

        // ─── CPU ───
        cpu: {
          manufacturer: cpuInfo.manufacturer || 'Unknown',
          brand: cpuInfo.brand || 'Unknown CPU',
          cores: cpuInfo.cores || os.cpus().length,
          physicalCores: cpuInfo.physicalCores || Math.floor(os.cpus().length / 2),
          speed: cpuSpeed.avg || cpuInfo.speed || 0,
          maxSpeed: cpuSpeed.max || cpuInfo.speedMax || 0,
          architecture: os.arch(),
          is64bit: os.arch() === 'x64' || os.arch() === 'arm64'
        },

        // ─── Memory ───
        memory: {
          totalBytes: memInfo.total,
          totalGB: parseFloat((memInfo.total / (1024 ** 3)).toFixed(1)),
          availableBytes: memInfo.available,
          availableGB: parseFloat((memInfo.available / (1024 ** 3)).toFixed(1)),
          usedPercent: Math.round((memInfo.active / memInfo.total) * 100)
        },

        // ─── GPU ───
        gpu: this._analyzeGPU(gpuInfo),

        // ─── Disk ───
        disk: {
          drives: (diskInfo || []).map(d => ({
            name: d.name || 'Unknown',
            type: d.type || 'Unknown',    // 'SSD', 'HDD'
            size: d.size || 0,
            sizeGB: parseFloat(((d.size || 0) / (1024 ** 3)).toFixed(0)),
            interfaceType: d.interfaceType || 'Unknown'
          })),
          hasSSD: (diskInfo || []).some(d => 
            (d.type || '').toLowerCase().includes('ssd') || 
            (d.interfaceType || '').toLowerCase().includes('nvme')
          )
        },

        // ─── OS ───
        os: {
          platform: os.platform(),
          distro: osInfo.distro || os.type(),
          release: osInfo.release || os.release(),
          arch: osInfo.arch || os.arch(),
          hostname: os.hostname(),
          uptime: os.uptime()
        },

        // ─── Network ───
        network: {
          interfaces: (networkInfo || []).filter(n => !n.internal).length,
          hasWifi: (networkInfo || []).some(n => 
            (n.type || '').toLowerCase().includes('wireless') ||
            (n.type || '').toLowerCase().includes('wifi')
          ),
          hasEthernet: (networkInfo || []).some(n => 
            (n.type || '').toLowerCase().includes('wired') ||
            (n.type || '').toLowerCase().includes('ethernet')
          )
        },

        // ─── Capability Assessment ───
        tier: null,
        aiRecommendation: null,
        uiRecommendation: null,
        scores: null
      };

      // Calculate capability tier
      this._calculateTier();

      // Cache to disk
      this._saveCachedProfile();

      this.isProfiled = true;
      timer.stop({ tier: this.profile.tier });

      logger.info('system', `System profiled — Capability tier: ${this.profile.tier.toUpperCase()}`, {
        cpu: this.profile.cpu.brand,
        ram: `${this.profile.memory.totalGB} GB`,
        gpu: this.profile.gpu.primary?.model || 'None',
        tier: this.profile.tier
      });

      return this.profile;

    } catch (err) {
      logger.error('system', 'System profiling failed', { error: err.message });
      
      // Return a minimal profile based on what we can get from Node.js directly
      this.profile = this._getMinimalProfile();
      this._calculateTier();
      this.isProfiled = true;
      
      timer.stop({ fallback: true, tier: this.profile.tier });
      return this.profile;
    }
  }

  /**
   * Analyze GPU capabilities.
   */
  _analyzeGPU(gpuInfo) {
    const controllers = gpuInfo?.controllers || [];
    
    if (controllers.length === 0) {
      return { hasDedicatedGPU: false, primary: null, all: [] };
    }

    const gpus = controllers.map(gpu => ({
      model: gpu.model || 'Unknown',
      vendor: gpu.vendor || 'Unknown',
      vramMB: gpu.vram || 0,
      vramGB: parseFloat(((gpu.vram || 0) / 1024).toFixed(1)),
      driverVersion: gpu.driverVersion || 'N/A',
      bus: gpu.bus || 'N/A',
      isDedicated: this._isDedicatedGPU(gpu)
    }));

    const dedicated = gpus.find(g => g.isDedicated);

    return {
      hasDedicatedGPU: !!dedicated,
      primary: dedicated || gpus[0],
      all: gpus
    };
  }

  /**
   * Determine if a GPU is dedicated (vs integrated).
   */
  _isDedicatedGPU(gpu) {
    const model = (gpu.model || '').toLowerCase();
    const vendor = (gpu.vendor || '').toLowerCase();
    
    // NVIDIA GPUs (except integrated)
    if (vendor.includes('nvidia') || model.includes('geforce') || model.includes('rtx') || model.includes('gtx') || model.includes('quadro')) {
      return true;
    }
    
    // AMD Radeon dedicated GPUs
    if ((vendor.includes('amd') || vendor.includes('ati')) && 
        (model.includes('radeon') && !model.includes('vega') && !model.includes('graphics'))) {
      return true;
    }
    
    // Intel Arc
    if (model.includes('arc a') || model.includes('arc b')) {
      return true;
    }

    // High VRAM usually means dedicated
    if ((gpu.vram || 0) >= 2048) {
      return true;
    }

    return false;
  }

  /**
   * Calculate the capability tier based on hardware specs.
   */
  _calculateTier() {
    if (!this.profile) return;

    const ramGB = this.profile.memory.totalGB;
    const hasDedicatedGPU = this.profile.gpu.hasDedicatedGPU;
    const gpuVRAM = this.profile.gpu.primary?.vramMB || 0;
    const cpuCores = this.profile.cpu.cores;

    // Scoring system (0-100)
    let ramScore = 0;
    if (ramGB >= 32) ramScore = 100;
    else if (ramGB >= 16) ramScore = 75;
    else if (ramGB >= 8) ramScore = 50;
    else if (ramGB >= 4) ramScore = 25;
    else ramScore = 10;

    let gpuScore = 0;
    if (hasDedicatedGPU) {
      if (gpuVRAM >= 8192) gpuScore = 100;
      else if (gpuVRAM >= 4096) gpuScore = 75;
      else if (gpuVRAM >= 2048) gpuScore = 50;
      else gpuScore = 30;
    } else {
      gpuScore = 10;
    }

    let cpuScore = 0;
    if (cpuCores >= 16) cpuScore = 100;
    else if (cpuCores >= 8) cpuScore = 75;
    else if (cpuCores >= 4) cpuScore = 50;
    else cpuScore = 25;

    // Weighted total: RAM matters most for AI, then GPU, then CPU
    const totalScore = (ramScore * 0.45) + (gpuScore * 0.35) + (cpuScore * 0.20);

    // Determine tier
    let tier;
    if (totalScore >= 80) tier = 'extreme';
    else if (totalScore >= 60) tier = 'high';
    else if (totalScore >= 40) tier = 'medium';
    else if (totalScore >= 20) tier = 'low';
    else tier = 'minimal';

    // Store results
    this.profile.tier = tier;
    this.profile.scores = { ram: ramScore, gpu: gpuScore, cpu: cpuScore, total: Math.round(totalScore) };
    this.profile.aiRecommendation = MODEL_RECOMMENDATIONS[tier];
    this.profile.uiRecommendation = UI_RECOMMENDATIONS[tier];
  }

  /**
   * Get a minimal profile using only Node.js built-in os module.
   * Used when systeminformation fails.
   */
  _getMinimalProfile() {
    const cpus = os.cpus();
    const totalMem = os.totalmem();

    return {
      profiledAt: new Date().toISOString(),
      version: '1.0.0',
      cpu: {
        manufacturer: 'Unknown',
        brand: cpus[0]?.model || 'Unknown CPU',
        cores: cpus.length,
        physicalCores: Math.floor(cpus.length / 2),
        speed: cpus[0]?.speed || 0,
        maxSpeed: 0,
        architecture: os.arch(),
        is64bit: os.arch() === 'x64' || os.arch() === 'arm64'
      },
      memory: {
        totalBytes: totalMem,
        totalGB: parseFloat((totalMem / (1024 ** 3)).toFixed(1)),
        availableBytes: os.freemem(),
        availableGB: parseFloat((os.freemem() / (1024 ** 3)).toFixed(1)),
        usedPercent: Math.round(((totalMem - os.freemem()) / totalMem) * 100)
      },
      gpu: { hasDedicatedGPU: false, primary: null, all: [] },
      disk: { drives: [], hasSSD: false },
      os: {
        platform: os.platform(),
        distro: os.type(),
        release: os.release(),
        arch: os.arch(),
        hostname: os.hostname(),
        uptime: os.uptime()
      },
      network: { interfaces: 0, hasWifi: false, hasEthernet: false },
      tier: null,
      aiRecommendation: null,
      uiRecommendation: null,
      scores: null
    };
  }

  // ─── Cache Management ──────────────────────────────────────────

  /**
   * Load cached profile from disk.
   * Cache is valid for 7 days — hardware doesn't change often.
   */
  _loadCachedProfile() {
    try {
      if (!fs.existsSync(appPaths.systemProfile)) return false;

      const content = fs.readFileSync(appPaths.systemProfile, 'utf8');
      const cached = JSON.parse(content);

      // Check if cache is still valid (7 days)
      const profiledAt = new Date(cached.profiledAt);
      const maxAge = 7 * 24 * 60 * 60 * 1000; // 7 days in ms
      if (Date.now() - profiledAt.getTime() > maxAge) {
        logger.info('system', 'Cached system profile expired — re-profiling');
        return false;
      }

      this.profile = cached;
      this.isProfiled = true;
      logger.info('system', `Loaded cached system profile — Tier: ${cached.tier}`, {
        cachedAt: cached.profiledAt
      });
      return true;

    } catch (err) {
      logger.warn('system', 'Failed to load cached profile', { error: err.message });
      return false;
    }
  }

  /**
   * Save profile to disk cache.
   */
  _saveCachedProfile() {
    try {
      fs.writeFileSync(appPaths.systemProfile, JSON.stringify(this.profile, null, 2), 'utf8');
    } catch (err) {
      logger.warn('system', 'Failed to cache system profile', { error: err.message });
    }
  }

  // ─── Public API ────────────────────────────────────────────────

  /**
   * Get the current profile. Returns null if not yet profiled.
   */
  getProfile() {
    return this.profile;
  }

  /**
   * Get the capability tier.
   */
  getTier() {
    return this.profile?.tier || 'minimal';
  }

  /**
   * Get AI model recommendations for this system.
   */
  getAIRecommendation() {
    return this.profile?.aiRecommendation || MODEL_RECOMMENDATIONS.minimal;
  }

  /**
   * Get UI recommendations for this system.
   */
  getUIRecommendation() {
    return this.profile?.uiRecommendation || UI_RECOMMENDATIONS.minimal;
  }

  /**
   * Get a human-readable summary of the system profile.
   */
  getSummary() {
    if (!this.profile) return 'System not profiled yet.';

    const p = this.profile;
    return {
      cpu: `${p.cpu.brand} (${p.cpu.cores} cores)`,
      ram: `${p.memory.totalGB} GB total, ${p.memory.availableGB} GB free`,
      gpu: p.gpu.primary ? `${p.gpu.primary.model} (${p.gpu.primary.vramGB} GB VRAM)` : 'Integrated/None',
      disk: p.disk.hasSSD ? 'SSD detected' : 'HDD or unknown',
      os: `${p.os.distro} ${p.os.arch}`,
      tier: p.tier.toUpperCase(),
      score: p.scores?.total || 0
    };
  }
}

// Singleton
const systemProfiler = new SystemProfiler();

module.exports = { systemProfiler, SystemProfiler, MODEL_RECOMMENDATIONS, UI_RECOMMENDATIONS };
