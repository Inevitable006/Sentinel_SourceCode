/**
 * SENTINEL — AI Personality Engine
 * Defines SENTINEL's professional Jarvis-like personality.
 */

class Personality {
  constructor() {
    this.name = 'SENTINEL';
    this.fullName = 'Smart Engine for Natural Talk & Intelligent Local Execution';
    this.greetings = {
      morning: [
        "Good morning, sir. All systems are operational. How may I assist you today?",
        "Good morning. I've been monitoring your system — everything is running optimally.",
        "Rise and shine, sir. SENTINEL is at your service."
      ],
      afternoon: [
        "Good afternoon, sir. What can I do for you?",
        "Afternoon, sir. Systems are nominal. How may I help?",
        "Good afternoon. I'm here and ready to assist."
      ],
      evening: [
        "Good evening, sir. How can I be of service?",
        "Evening, sir. All systems are running smoothly.",
        "Good evening. SENTINEL is standing by."
      ],
      night: [
        "Burning the midnight oil, sir? I'm here if you need me.",
        "It's quite late, sir. Shall I keep watch while you work?",
        "Working late, I see. SENTINEL doesn't sleep — I'm at your disposal."
      ]
    };
    this.fallbackResponses = [
      "I'm processing that request, sir. One moment.",
      "Understood. Let me work on that.",
      "Right away, sir.",
      "Consider it done."
    ];
  }

  getGreeting() {
    const hour = new Date().getHours();
    let timeOfDay;
    
    if (hour >= 5 && hour < 12) timeOfDay = 'morning';
    else if (hour >= 12 && hour < 17) timeOfDay = 'afternoon';
    else if (hour >= 17 && hour < 21) timeOfDay = 'evening';
    else timeOfDay = 'night';

    const greetings = this.greetings[timeOfDay];
    return greetings[Math.floor(Math.random() * greetings.length)];
  }

  getLoadingMessage(progress) {
    if (progress < 10) return "Initializing neural pathways...";
    if (progress < 30) return "Loading cognitive modules...";
    if (progress < 50) return "Calibrating language processors...";
    if (progress < 70) return "Synchronizing response matrix...";
    if (progress < 90) return "Running final diagnostics...";
    return "Systems coming online...";
  }

  getErrorRecoveryMessage() {
    return "I've encountered an issue, sir. My systems are attempting auto-recovery. Please stand by.";
  }

  getFallbackResponse() {
    return this.fallbackResponses[Math.floor(Math.random() * this.fallbackResponses.length)];
  }
}

module.exports = { Personality };
