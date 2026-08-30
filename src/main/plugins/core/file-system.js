const { BasePlugin } = require('../base-plugin');
const fs = require('fs/promises');
const path = require('path');
const { appPaths } = require('../../core/app-paths');
const { logger } = require('../../core/logger');

class FileSystemPlugin extends BasePlugin {
  constructor() {
    super('file-system', 'Safely reads and writes files within the SENTINEL workspace.');
    
    this.registerTool({
      name: 'read_file',
      description: 'Reads the contents of a file within the SENTINEL workspace.',
      parameters: {
        type: 'object',
        properties: {
          filename: { type: 'string', description: 'The name of the file to read (relative to workspace)' }
        },
        required: ['filename']
      }
    }, this.readFile);

    this.registerTool({
      name: 'write_file',
      description: 'Writes content to a file within the SENTINEL workspace.',
      parameters: {
        type: 'object',
        properties: {
          filename: { type: 'string', description: 'The name of the file to write (relative to workspace)' },
          content: { type: 'string', description: 'The content to write' }
        },
        required: ['filename', 'content']
      }
    }, this.writeFile);
  }

  _getSafePath(filename) {
    const workspace = path.join(appPaths.userData, 'workspace');
    const targetPath = path.resolve(workspace, filename);
    if (!targetPath.startsWith(workspace)) {
      throw new Error('Path traversal detected. Access denied outside workspace.');
    }
    return targetPath;
  }

  async readFile({ filename }) {
    try {
      const targetPath = this._getSafePath(filename);
      const content = await fs.readFile(targetPath, 'utf8');
      return { success: true, content };
    } catch (err) {
      return { error: `Failed to read file: ${err.message}` };
    }
  }

  async writeFile({ filename, content }) {
    try {
      const targetPath = this._getSafePath(filename);
      // Ensure directory exists
      await fs.mkdir(path.dirname(targetPath), { recursive: true });
      await fs.writeFile(targetPath, content, 'utf8');
      logger.info('plugin', `File written: ${filename}`);
      return { success: true, message: `File ${filename} written successfully.` };
    } catch (err) {
      return { error: `Failed to write file: ${err.message}` };
    }
  }
}

module.exports = FileSystemPlugin;
