/**
 * SENTINEL — Base Plugin
 * The abstract foundation for all SENTINEL plugins.
 */
class BasePlugin {
  constructor(name, description, version = '1.0.0') {
    this.name = name;
    this.description = description;
    this.version = version;
    this.tools = []; // Array of tool schemas
  }

  /**
   * Defines a tool schema that the LLM can use
   */
  registerTool(schema, handler) {
    this.tools.push({
      schema,
      handler: handler.bind(this)
    });
  }

  /**
   * Returns all tool schemas for injection into the LLM system prompt
   */
  getSchemas() {
    return this.tools.map(t => t.schema);
  }

  /**
   * Executes a tool by name with provided arguments
   */
  async execute(toolName, args) {
    const tool = this.tools.find(t => t.schema.name === toolName);
    if (!tool) {
      throw new Error(`Tool ${toolName} not found in plugin ${this.name}`);
    }

    try {
      return await tool.handler(args);
    } catch (err) {
      return { error: err.message };
    }
  }
}

module.exports = { BasePlugin };
