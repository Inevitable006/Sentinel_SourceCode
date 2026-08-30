/**
 * SENTINEL — Orb Visualizer
 * Animated AI core visualization using Canvas 2D
 * States: idle, listening, thinking, speaking, loading, error
 */

class SentinelOrb {
  constructor(canvasId) {
    this.canvas = document.getElementById(canvasId);
    this.ctx = this.canvas.getContext('2d');
    this.state = 'idle'; // idle, listening, thinking, speaking, loading, error
    this.time = 0;
    this.particles = [];
    this.rings = [];
    this.dpr = window.devicePixelRatio || 1;

    // High-DPI support
    this.canvas.width = 200 * this.dpr;
    this.canvas.height = 200 * this.dpr;
    this.ctx.scale(this.dpr, this.dpr);

    this.cx = 100;
    this.cy = 100;
    this.baseRadius = 35;

    // Color schemes per state
    this.colors = {
      idle: { primary: '#00d4ff', secondary: '#0088ff', glow: 'rgba(0, 212, 255, 0.15)' },
      listening: { primary: '#00d4ff', secondary: '#00ffcc', glow: 'rgba(0, 212, 255, 0.3)' },
      thinking: { primary: '#8b5cf6', secondary: '#a78bfa', glow: 'rgba(139, 92, 246, 0.25)' },
      speaking: { primary: '#10b981', secondary: '#34d399', glow: 'rgba(16, 185, 129, 0.25)' },
      loading: { primary: '#f59e0b', secondary: '#fbbf24', glow: 'rgba(245, 158, 11, 0.2)' },
      error: { primary: '#ef4444', secondary: '#f87171', glow: 'rgba(239, 68, 68, 0.2)' }
    };

    // Initialize particles
    for (let i = 0; i < 30; i++) {
      this.particles.push({
        angle: (Math.PI * 2 / 30) * i,
        radius: this.baseRadius + 15 + Math.random() * 20,
        speed: 0.005 + Math.random() * 0.01,
        size: 1 + Math.random() * 2,
        offset: Math.random() * Math.PI * 2
      });
    }

    // Initialize orbital rings
    for (let i = 0; i < 3; i++) {
      this.rings.push({
        radius: this.baseRadius + 20 + i * 12,
        speed: 0.003 + i * 0.002,
        angle: (Math.PI * 2 / 3) * i,
        opacity: 0.15 - i * 0.04
      });
    }

    this.animate();
  }

  setState(newState) {
    this.state = newState;
    const container = this.canvas.parentElement;
    container.className = 'orb-container ' + newState;
  }

  animate() {
    this.time += 0.016;
    this.draw();
    requestAnimationFrame(() => this.animate());
  }

  draw() {
    const ctx = this.ctx;
    const colors = this.colors[this.state] || this.colors.idle;

    ctx.clearRect(0, 0, 200, 200);

    // ─── Outer Glow ───
    const glowRadius = this.baseRadius + 30 + Math.sin(this.time * 1.5) * 5;
    const gradient = ctx.createRadialGradient(this.cx, this.cy, 0, this.cx, this.cy, glowRadius);
    gradient.addColorStop(0, colors.glow);
    gradient.addColorStop(0.5, colors.glow.replace(/[\d.]+\)$/, '0.05)'));
    gradient.addColorStop(1, 'transparent');
    ctx.fillStyle = gradient;
    ctx.beginPath();
    ctx.arc(this.cx, this.cy, glowRadius, 0, Math.PI * 2);
    ctx.fill();

    // ─── Orbital Rings ───
    this.rings.forEach((ring, i) => {
      ring.angle += ring.speed;
      ctx.save();
      ctx.translate(this.cx, this.cy);
      ctx.rotate(ring.angle);
      ctx.strokeStyle = colors.primary;
      ctx.globalAlpha = ring.opacity + Math.sin(this.time * 2 + i) * 0.05;
      ctx.lineWidth = 1;
      ctx.setLineDash([4, 8]);
      ctx.beginPath();
      ctx.arc(0, 0, ring.radius, 0, Math.PI * 2);
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.restore();
    });

    // ─── Particles ───
    this.particles.forEach((p) => {
      let particleRadius = p.radius;
      
      if (this.state === 'thinking') {
        particleRadius += Math.sin(this.time * 3 + p.offset) * 8;
        p.angle += p.speed * 3;
      } else if (this.state === 'speaking') {
        particleRadius += Math.sin(this.time * 5 + p.offset) * 12;
        p.angle += p.speed * 1.5;
      } else if (this.state === 'listening') {
        particleRadius += Math.sin(this.time * 2 + p.offset) * 6;
        p.angle += p.speed * 2;
      } else {
        p.angle += p.speed;
        particleRadius += Math.sin(this.time + p.offset) * 3;
      }

      const x = this.cx + Math.cos(p.angle) * particleRadius;
      const y = this.cy + Math.sin(p.angle) * particleRadius;

      ctx.beginPath();
      ctx.arc(x, y, p.size, 0, Math.PI * 2);
      ctx.fillStyle = colors.primary;
      ctx.globalAlpha = 0.3 + Math.sin(this.time * 2 + p.offset) * 0.2;
      ctx.fill();
      ctx.globalAlpha = 1;
    });

    // ─── Core Orb ───
    const coreGradient = ctx.createRadialGradient(
      this.cx - 5, this.cy - 5, 0,
      this.cx, this.cy, this.baseRadius
    );
    
    const pulseSize = this.state === 'speaking' 
      ? Math.sin(this.time * 6) * 4 
      : Math.sin(this.time * 1.5) * 2;

    coreGradient.addColorStop(0, colors.secondary);
    coreGradient.addColorStop(0.6, colors.primary);
    coreGradient.addColorStop(1, 'rgba(0, 0, 0, 0.3)');

    ctx.beginPath();
    ctx.arc(this.cx, this.cy, this.baseRadius + pulseSize, 0, Math.PI * 2);
    ctx.fillStyle = coreGradient;
    ctx.fill();

    // ─── Core Inner Light ───
    const innerGlow = ctx.createRadialGradient(
      this.cx - 3, this.cy - 3, 0,
      this.cx, this.cy, this.baseRadius * 0.6
    );
    innerGlow.addColorStop(0, 'rgba(255, 255, 255, 0.4)');
    innerGlow.addColorStop(0.5, 'rgba(255, 255, 255, 0.1)');
    innerGlow.addColorStop(1, 'transparent');
    ctx.beginPath();
    ctx.arc(this.cx, this.cy, this.baseRadius * 0.6, 0, Math.PI * 2);
    ctx.fillStyle = innerGlow;
    ctx.fill();

    // ─── Core Ring ───
    ctx.beginPath();
    ctx.arc(this.cx, this.cy, this.baseRadius + pulseSize + 2, 0, Math.PI * 2);
    ctx.strokeStyle = colors.primary;
    ctx.globalAlpha = 0.3;
    ctx.lineWidth = 1.5;
    ctx.stroke();
    ctx.globalAlpha = 1;

    // ─── Loading Spinner (overlay) ───
    if (this.state === 'loading') {
      const spinAngle = this.time * 3;
      ctx.save();
      ctx.translate(this.cx, this.cy);
      ctx.rotate(spinAngle);
      ctx.beginPath();
      ctx.arc(0, 0, this.baseRadius + 10, 0, Math.PI * 0.8);
      ctx.strokeStyle = colors.primary;
      ctx.lineWidth = 3;
      ctx.lineCap = 'round';
      ctx.globalAlpha = 0.8;
      ctx.stroke();
      ctx.restore();
    }
  }
}

// Export globally
window.SentinelOrb = SentinelOrb;
