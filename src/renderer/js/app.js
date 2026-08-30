/**
 * SENTINEL — App Controller
 * Main application entry point. Initializes all modules,
 * handles navigation, and orchestrates the AI lifecycle.
 */

class App {
  constructor() {
    this.orb = null;
    this.chat = null;
    this.dashboard = null;
    this.currentView = 'chat';
    this.aiInitialized = false;

    this._init();
  }

  async _init() {
    console.log('[SENTINEL] Initializing application...');

    // Initialize UI components
    this.orb = new SentinelOrb('sentinel-orb');
    this.chat = new ChatInterface();
    this.dashboard = new Dashboard();

    // Bind window controls
    this._bindWindowControls();
    
    // Bind sidebar toggle
    this._bindSidebar();

    // Bind navigation
    this._bindNavigation();

    // Set orb to loading state
    this.orb.setState('loading');

    // Show welcome message
    this._showWelcome();

    // Initialize AI engine
    await this._initializeAI();
  }

  _bindWindowControls() {
    document.getElementById('btn-minimize').addEventListener('click', () => {
      window.sentinel.window.minimize();
    });

    document.getElementById('btn-maximize').addEventListener('click', () => {
      window.sentinel.window.maximize();
    });

    document.getElementById('btn-close').addEventListener('click', () => {
      window.sentinel.window.close();
    });
  }

  _bindSidebar() {
    const menuBtn = document.getElementById('btn-menu');
    const sidebar = document.getElementById('sidebar');
    const overlay = document.getElementById('sidebar-overlay');

    if (!menuBtn || !sidebar || !overlay) return;

    const toggleSidebar = () => {
      const isOpen = sidebar.classList.contains('open');
      if (isOpen) {
        sidebar.classList.remove('open');
        overlay.classList.remove('active');
      } else {
        sidebar.classList.add('open');
        overlay.classList.add('active');
      }
    };

    menuBtn.addEventListener('click', toggleSidebar);
    overlay.addEventListener('click', toggleSidebar);
  }

  _bindNavigation() {
    const navButtons = document.querySelectorAll('.nav-btn[data-view]');
    
    navButtons.forEach(btn => {
      btn.addEventListener('click', () => {
        const viewName = btn.getAttribute('data-view');
        this._switchView(viewName);
        
        // Update active state
        navButtons.forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        
        // Auto-close sidebar on mobile/when overlay is active
        const sidebar = document.getElementById('sidebar');
        const overlay = document.getElementById('sidebar-overlay');
        if (sidebar && overlay && overlay.classList.contains('active')) {
          sidebar.classList.remove('open');
          overlay.classList.remove('active');
        }
      });
    });
  }

  _switchView(viewName) {
    // Hide all views
    document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
    
    // Show selected view
    const view = document.getElementById(`view-${viewName}`);
    if (view) {
      view.classList.add('active');
    }

    // Start/stop dashboard polling
    if (viewName === 'dashboard') {
      this.dashboard.start();
    } else {
      this.dashboard.stop();
    }

    this.currentView = viewName;
  }

  _showWelcome() {
    // Time-based greeting
    const hour = new Date().getHours();
    let greeting;
    if (hour >= 5 && hour < 12) greeting = "Good morning, sir.";
    else if (hour >= 12 && hour < 17) greeting = "Good afternoon, sir.";
    else if (hour >= 17 && hour < 21) greeting = "Good evening, sir.";
    else greeting = "Working late, sir? I'm here whenever you need me.";

    this.chat.addSystemMessage(`⚡ SENTINEL v1.0 — Initializing neural core...`);
    
    setTimeout(() => {
      this.chat.addAssistantMessage(
        `${greeting} I am **SENTINEL** — your personal AI assistant. ` +
        `I run entirely on your local machine. No cloud. No data leaves this system.\n\n` +
        `I'm currently loading my language model. Once ready, I'll be able to:\n` +
        `• **Converse** with you naturally\n` +
        `• **Monitor** your system (CPU, RAM, GPU)\n` +
        `• **Launch** applications\n` +
        `• **Manage** files\n\n` +
        `Please give me a moment to come fully online.`
      );
    }, 500);
  }

  async _initializeAI() {
    const statusIndicator = document.getElementById('ai-status');
    const statusText = document.getElementById('sentinel-status-text');
    
    statusIndicator.className = 'ai-status-indicator loading';
    statusIndicator.querySelector('.status-text').textContent = 'Loading';
    statusText.textContent = 'Loading AI model...';

    try {
      const result = await window.sentinel.ai.initialize();
      
      if (result.success) {
        this.aiInitialized = true;
        
        if (result.mode === 'fallback') {
          statusIndicator.className = 'ai-status-indicator loading';
          statusIndicator.querySelector('.status-text').textContent = 'Limited';
          statusText.textContent = 'Fallback mode — Install Ollama for full AI';
          this.orb.setState('idle');
          
          this.chat.addSystemMessage('⚡ SENTINEL online — Fallback mode (no AI model detected)');
          setTimeout(() => {
            this.chat.addAssistantMessage(
              `I'm online, sir, but running in **fallback mode**. My full conversational abilities require an AI model.\n\n` +
              `To unlock my full potential, install **Ollama**:\n` +
              `1. Download from **https://ollama.ai**\n` +
              `2. Run: \`ollama pull qwen2.5:0.5b\`\n` +
              `3. Restart SENTINEL\n\n` +
              `In the meantime, the **System Dashboard** is fully operational. Try clicking the System tab in the sidebar!`
            );
          }, 300);
        } else {
          statusIndicator.className = 'ai-status-indicator online';
          statusIndicator.querySelector('.status-text').textContent = 'Online';
          const modeLabel = result.mode === 'ollama' ? `Ollama (${result.model})` : `ONNX (${result.model})`;
          statusText.textContent = `Online — ${modeLabel}`;
          this.orb.setState('idle');
          
          this.chat.addSystemMessage(`✅ Neural core online via ${result.mode}. SENTINEL is ready.`);
          setTimeout(() => {
            this.chat.addAssistantMessage(
              `All systems are operational, sir. My language model is loaded and running locally via **${result.mode}**. ` +
              `How may I assist you today?`
            );
          }, 300);
        }
      } else {
        this._handleAIError(result.error);
      }
    } catch (err) {
      this._handleAIError(err.message);
    }
  }

  _handleAIError(errorMessage) {
    const statusIndicator = document.getElementById('ai-status');
    const statusText = document.getElementById('sentinel-status-text');
    
    statusIndicator.className = 'ai-status-indicator error';
    statusIndicator.querySelector('.status-text').textContent = 'Error';
    statusText.textContent = 'Model load failed';
    
    this.orb.setState('error');
    
    this.chat.addSystemMessage(`⚠️ AI model failed to load: ${errorMessage}`);
    this.chat.addAssistantMessage(
      `I apologize, sir. My neural core encountered an issue during initialization.\n\n` +
      `**Error:** ${errorMessage}\n\n` +
      `**Possible fixes:**\n` +
      `• Ensure you have a stable internet connection for the first model download\n` +
      `• Check that you have at least 2GB of free disk space\n` +
      `• Try restarting the application\n\n` +
      `The system dashboard and other features are still available while I troubleshoot this.`
    );
  }
}

// ─── Initialize App ─────────────────────────────────────────────
window.addEventListener('DOMContentLoaded', () => {
  window.app = new App();
});
