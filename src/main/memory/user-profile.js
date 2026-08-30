const fs = require('fs');
const path = require('path');
const { appPaths } = require('../core/app-paths');
const { logger } = require('../core/logger');
const { errorHandler } = require('../core/error-handler');

/**
 * UserProfile
 * Tracks interaction patterns, preferences, and adapts over time.
 */
class UserProfile {
  constructor() {
    this.initialized = false;
    this.profilePath = null;
    this.profileData = {
      name: 'sir',
      preferences: {
        verbosity: 0.5,
        technicalDepth: 0.5
      },
      topics: {}, // Frequencies of requested topics
      interactionCount: 0,
      lastInteraction: null,
      corrections: [] // Track when user corrected the AI
    };
  }

  init() {
    return errorHandler.wrapSync(() => {
      const profileDir = appPaths.profile;
      this.profilePath = path.join(profileDir, 'user-profile.json');
      
      this.load();
      this.initialized = true;
      logger.info('memory', 'User profile initialized', { path: this.profilePath });
      return true;
    }, 'user-profile.init');
  }

  load() {
    if (fs.existsSync(this.profilePath)) {
      try {
        const data = fs.readFileSync(this.profilePath, 'utf8');
        this.profileData = { ...this.profileData, ...JSON.parse(data) };
        logger.info('memory', 'User profile loaded');
      } catch (err) {
        logger.error('memory', 'Failed to load user profile', { error: err.message });
      }
    } else {
      this.save(); // Create default
    }
  }

  save() {
    try {
      fs.writeFileSync(this.profilePath, JSON.stringify(this.profileData, null, 2), 'utf8');
    } catch (err) {
      logger.error('memory', 'Failed to save user profile', { error: err.message });
    }
  }

  /**
   * Updates profile based on a new interaction
   * @param {string} topic - Broad topic category
   * @param {boolean} wasCorrection - Did the user correct SENTINEL?
   */
  recordInteraction(topic, wasCorrection = false) {
    return errorHandler.wrapSync(() => {
      if (!this.initialized) this.init();

      this.profileData.interactionCount++;
      this.profileData.lastInteraction = new Date().toISOString();

      if (topic) {
        this.profileData.topics[topic] = (this.profileData.topics[topic] || 0) + 1;
      }

      if (wasCorrection) {
        this.profileData.corrections.push({ timestamp: new Date().toISOString(), topic });
        // Cap corrections array
        if (this.profileData.corrections.length > 50) this.profileData.corrections.shift();
      }

      this.save();
    }, 'user-profile.recordInteraction');
  }

  /**
   * Adjusts a preference explicitly
   */
  setPreference(key, value) {
    if (!this.initialized) this.init();
    if (this.profileData.preferences[key] !== undefined) {
      this.profileData.preferences[key] = value;
      this.save();
      logger.info('memory', 'User preference updated', { key, value });
    }
  }

  getProfile() {
    if (!this.initialized) this.init();
    return this.profileData;
  }
}

const userProfile = new UserProfile();
module.exports = { userProfile, UserProfile };
