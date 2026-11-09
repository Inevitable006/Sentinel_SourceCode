import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { createRequire } from 'node:module';
import vm from 'node:vm';

const require = createRequire(new URL('../package.json', import.meta.url));
const ts = require('typescript');

const modelStatusSource = fs.readFileSync(new URL('../src/components/Settings/ModelStatus.tsx', import.meta.url), 'utf8');
const compiledModelStatus = ts.transpileModule(modelStatusSource, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.React, esModuleInterop: true },
}).outputText;

const settingsPanelSource = fs.readFileSync(new URL('../src/components/Settings/SettingsPanel.tsx', import.meta.url), 'utf8');
const compiledSettingsPanel = ts.transpileModule(settingsPanelSource, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.React, esModuleInterop: true },
}).outputText;

function textContent(node) {
  if (!node) return '';
  if (typeof node === 'string' || typeof node === 'number') return String(node);
  const children = Array.isArray(node.children) ? node.children : (node.props?.children ? [node.props.children] : []);
  return children.flat(Infinity).map(textContent).join('');
}

function find(node, predicate) {
  if (!node || typeof node !== 'object') return null;
  if (predicate(node)) return node;
  const children = Array.isArray(node.children) ? node.children : [];
  for (const child of children) {
    const match = find(child, predicate);
    if (match) return match;
  }
  return null;
}

function findAll(node, predicate, acc = []) {
  if (!node || typeof node !== 'object') return acc;
  if (predicate(node)) acc.push(node);
  const children = Array.isArray(node.children) ? node.children : [];
  for (const child of children) {
    findAll(child, predicate, acc);
  }
  return acc;
}

function renderModelStatus(props) {
  const react = {
    createElement: (type, elProps, ...children) => {
      const flat = children.flat(Infinity);
      const childProp = flat.length === 1 ? flat[0] : (flat.length === 0 ? undefined : flat);
      const props = { ...(elProps || {}), children: childProp };
      if (typeof type === 'function') {
        return type(props);
      }
      return {
        type,
        props,
        children: flat,
      };
    },
  };

  const sandbox = {
    exports: {},
    Error: globalThis.Error,
    require(name) {
      if (name === 'react') return react;
      throw new Error(`Unexpected import in ModelStatus: ${name}`);
    },
  };

  vm.runInNewContext(compiledModelStatus, sandbox);
  const Component = sandbox.exports.ModelStatus || sandbox.exports.default;
  return Component(props);
}

test('ModelStatus: renders loading message when info is null', () => {
  const tree = renderModelStatus({ info: null, activeProfile: 'auto' });
  const text = textContent(tree);
  assert.ok(text.includes('Loading model information…'), `Expected loading text, got: ${text}`);
});

test('ModelStatus: auto selected policy with concrete model loaded in memory', () => {
  const mockInfo = {
    active_profile: 'auto',
    profiles: [
      { id: 'auto', name: 'Auto (Recommended)', downloaded: null, description: 'Automatic selection' },
      { id: 'qwen2.5-7b', name: 'Qwen 2.5 7B', downloaded: true, description: 'Default general model' },
    ],
    loaded: {
      profile_id: 'qwen2.5-7b',
      name: 'Qwen 2.5 7B',
      engine: 'gpu',
      notes: ['Fastest local profile', 'Warm cache ready'],
    },
    gpu_engine: {
      available: true,
      running: true,
      model: 'qwen2.5-7b',
      vram_mb: 8192,
      reason: null,
      last_error: null,
    },
    last_load_error: null,
  };

  const tree = renderModelStatus({ info: mockInfo, activeProfile: 'auto' });
  const text = textContent(tree);

  // Selected policy: Auto is policy, not downloadable file
  assert.ok(
    text.includes('Automatic selection policy (picks best downloaded model)'),
    `Expected automatic policy explanation, got: ${text}`
  );
  // Loaded model details
  assert.ok(text.includes('Qwen 2.5 7B on GPU'), `Expected loaded model name and engine, got: ${text}`);
  // Mismatch indicator since activeProfile ('auto') !== loaded.profile_id ('qwen2.5-7b')
  assert.ok(
    text.includes('Selected profile differs from currently loaded model'),
    `Expected difference note, got: ${text}`
  );
  // Notes rendered
  assert.ok(
    text.includes('Fastest local profile · Warm cache ready'),
    `Expected selection notes, got: ${text}`
  );
  // GPU running with measured VRAM
  assert.ok(text.includes('running (8.0 GB VRAM)'), `Expected GPU running status, got: ${text}`);
});

test('ModelStatus: selected model differs from loaded model shows guidance note', () => {
  const mockInfo = {
    active_profile: 'llama3-8b',
    profiles: [
      { id: 'llama3-8b', name: 'Llama 3 8B', downloaded: true },
      { id: 'qwen2.5-7b', name: 'Qwen 2.5 7B', downloaded: true },
    ],
    loaded: {
      profile_id: 'qwen2.5-7b',
      name: 'Qwen 2.5 7B',
      engine: 'gpu',
      notes: [],
    },
    gpu_engine: {
      available: true,
      running: false,
      model: null,
      vram_mb: 8192,
      reason: null,
      last_error: null,
    },
    last_load_error: null,
  };

  const treeDiff = renderModelStatus({ info: mockInfo, activeProfile: 'llama3-8b' });
  const textDiff = textContent(treeDiff);
  assert.ok(
    textDiff.includes('Selected profile differs from currently loaded model. Re-load model in Console to apply.'),
    `Expected diff warning, got: ${textDiff}`
  );

  // When selected matches loaded, no warning should appear
  const treeSame = renderModelStatus({ info: mockInfo, activeProfile: 'qwen2.5-7b' });
  const textSame = textContent(treeSame);
  assert.ok(
    !textSame.includes('Selected profile differs from currently loaded model'),
    `Expected NO diff warning when matching, got: ${textSame}`
  );
});

test('ModelStatus: not downloaded profile vs downloaded profile status', () => {
  const mockInfo = {
    active_profile: 'deepseek-r1',
    profiles: [
      { id: 'deepseek-r1', name: 'DeepSeek R1', downloaded: false },
      { id: 'qwen2.5-7b', name: 'Qwen 2.5 7B', downloaded: true },
    ],
    loaded: null,
    gpu_engine: null,
    last_load_error: null,
  };

  // Not downloaded
  const treeNotDown = renderModelStatus({ info: mockInfo, activeProfile: 'deepseek-r1' });
  const textNotDown = textContent(treeNotDown);
  assert.ok(
    textNotDown.includes('Not downloaded (GGUF file missing in models folder)'),
    `Expected not downloaded status, got: ${textNotDown}`
  );

  // Downloaded
  const treeDown = renderModelStatus({ info: mockInfo, activeProfile: 'qwen2.5-7b' });
  const textDown = textContent(treeDown);
  assert.ok(
    textDown.includes('Downloaded (ready to load)'),
    `Expected downloaded status, got: ${textDown}`
  );
});

test('ModelStatus: no model loaded right now', () => {
  const mockInfo = {
    active_profile: 'qwen2.5-7b',
    profiles: [{ id: 'qwen2.5-7b', name: 'Qwen 2.5 7B', downloaded: true }],
    loaded: null,
    gpu_engine: { available: true, running: false, model: null, vram_mb: 6144, reason: null, last_error: null },
    last_load_error: null,
  };

  const tree = renderModelStatus({ info: mockInfo, activeProfile: 'qwen2.5-7b' });
  const text = textContent(tree);
  assert.ok(text.includes('No model loaded right now.'), `Expected no model loaded message, got: ${text}`);
});

test('ModelStatus: GPU unavailable shows honest reason', () => {
  const mockInfo = {
    active_profile: 'qwen2.5-7b',
    profiles: [{ id: 'qwen2.5-7b', name: 'Qwen 2.5 7B', downloaded: true }],
    loaded: null,
    gpu_engine: {
      available: false,
      running: false,
      model: null,
      vram_mb: 0,
      reason: 'NVIDIA driver not installed or CUDA runtime missing',
      last_error: null,
    },
    last_load_error: null,
  };

  const tree = renderModelStatus({ info: mockInfo, activeProfile: 'qwen2.5-7b' });
  const text = textContent(tree);
  assert.ok(
    text.includes('unavailable (NVIDIA driver not installed or CUDA runtime missing)'),
    `Expected unavailable reason, got: ${text}`
  );
});

test('ModelStatus: missing or zero VRAM reports unmeasured, never deceptive 0.0 GB', () => {
  // Case A: vram_mb is 0
  const infoZero = {
    active_profile: 'qwen2.5-7b',
    profiles: [{ id: 'qwen2.5-7b', name: 'Qwen 2.5 7B', downloaded: true }],
    loaded: null,
    gpu_engine: {
      available: true,
      running: false,
      model: null,
      vram_mb: 0,
      reason: null,
      last_error: null,
    },
    last_load_error: null,
  };

  const treeZero = renderModelStatus({ info: infoZero, activeProfile: 'qwen2.5-7b' });
  const textZero = textContent(treeZero);
  assert.ok(textZero.includes('VRAM: unmeasured'), `Expected 'VRAM: unmeasured', got: ${textZero}`);
  assert.ok(!textZero.includes('0.0 GB'), `Must NEVER show 0.0 GB for unmeasured VRAM, got: ${textZero}`);
  assert.ok(!textZero.includes('0 GB'), `Must not show 0 GB for unmeasured VRAM, got: ${textZero}`);

  // Case B: vram_mb is null / undefined
  const infoNull = {
    active_profile: 'qwen2.5-7b',
    profiles: [{ id: 'qwen2.5-7b', name: 'Qwen 2.5 7B', downloaded: true }],
    loaded: null,
    gpu_engine: {
      available: true,
      running: false,
      model: null,
      vram_mb: null,
      reason: null,
      last_error: null,
    },
    last_load_error: null,
  };

  const treeNull = renderModelStatus({ info: infoNull, activeProfile: 'qwen2.5-7b' });
  const textNull = textContent(treeNull);
  assert.ok(textNull.includes('VRAM: unmeasured'), `Expected 'VRAM: unmeasured', got: ${textNull}`);
  assert.ok(!textNull.includes('0.0 GB'), `Must NEVER show 0.0 GB for null VRAM, got: ${textNull}`);
});

test('ModelStatus: prior load error displayed with alert role when no model loaded', () => {
  const mockInfo = {
    active_profile: 'qwen2.5-7b',
    profiles: [{ id: 'qwen2.5-7b', name: 'Qwen 2.5 7B', downloaded: true }],
    loaded: null,
    gpu_engine: { available: true, running: false, model: null, vram_mb: 8192, reason: null, last_error: null },
    last_load_error: 'CUDA out of memory during context allocation (requested 16384 context tokens)',
  };

  const tree = renderModelStatus({ info: mockInfo, activeProfile: 'qwen2.5-7b' });
  const alertNode = find(tree, node => node.props && node.props.role === 'alert');
  assert.ok(alertNode, 'Expected an element with role="alert" for load error');
  const alertText = textContent(alertNode);
  assert.ok(
    alertText.includes('CUDA out of memory during context allocation'),
    `Expected error detail in alert, got: ${alertText}`
  );
});

test('ModelStatus: renders authoritative memory explanation and avoids fabricated claims', () => {
  const mockInfo = {
    active_profile: 'auto',
    profiles: [{ id: 'auto', name: 'Auto', downloaded: null }],
    loaded: null,
    gpu_engine: { available: true, running: false, model: null, vram_mb: 4096, reason: null, last_error: null },
    last_load_error: null,
  };

  const tree = renderModelStatus({ info: mockInfo, activeProfile: 'auto' });
  const text = textContent(tree);

  // Authoritative guidance
  assert.ok(
    text.includes("Model weights, context cache, and runtime all consume memory. Sentinel's runtime load and fit checks remain authoritative."),
    `Expected memory explanation, got: ${text}`
  );

  // Negative checks: no fabricated metrics, no Colibri mention, no fake download buttons
  assert.ok(!text.toLowerCase().includes('colibri'), `Must not claim Colibri integration, got: ${text}`);
  assert.ok(!text.includes('fit score'), `Must not fabricate fit score, got: ${text}`);
  assert.ok(!text.includes('tok/s'), `Must not fabricate token speed ratings, got: ${text}`);
});

function createSettingsPanelHarness(options = {}) {
  const stateSlots = [];
  const effectSlots = [];
  let stateCursor = 0;
  let effectCursor = 0;
  let tree = null;

  const react = {
    createElement: (type, elProps, ...children) => {
      const flat = children.flat(Infinity);
      const childProp = flat.length === 1 ? flat[0] : (flat.length === 0 ? undefined : flat);
      const props = { ...(elProps || {}), children: childProp };
      if (typeof type === 'function') {
        return type(props);
      }
      return {
        type,
        props,
        children: flat,
      };
    },
    useState(initial) {
      const idx = stateCursor++;
      if (!(idx in stateSlots)) {
        stateSlots[idx] = initial;
      }
      const setState = (next) => {
        stateSlots[idx] = typeof next === 'function' ? next(stateSlots[idx]) : next;
        render();
      };
      return [stateSlots[idx], setState];
    },
    useEffect(effect, deps) {
      const idx = effectCursor++;
      effectSlots[idx] = { effect, deps };
    },
  };

  const modelStatusSandbox = {
    exports: {},
    Error: globalThis.Error,
    require(name) {
      if (name === 'react') return react;
      throw new Error(`Unexpected import in ModelStatus: ${name}`);
    },
  };
  vm.runInNewContext(compiledModelStatus, modelStatusSandbox);

  const dummyComponent = () => ({ type: 'div', props: {}, children: [] });

  const fetchCalls = [];
  const apiGetCalls = [];
  const fetchMock = options.fetch || (async (url, init = {}) => {
    fetchCalls.push({ url: String(url), init });
    if (String(url).endsWith('/settings')) {
      return { ok: true, json: async () => ({ system_prompt: 'System prompt' }) };
    }
    if (String(url).endsWith('/api/models')) {
      return {
        ok: true,
        json: async () => options.initialModelsInfo || {
          active_profile: 'auto',
          profiles: [
            { id: 'auto', name: 'Auto', downloaded: null },
            { id: 'qwen2.5-7b', name: 'Qwen 2.5 7B', downloaded: true },
          ],
          loaded: null,
          gpu_engine: { available: true, running: false, vram_mb: 8192 },
        },
      };
    }
    if (String(url).endsWith('/api/models/select')) {
      return { ok: true, json: async () => ({ status: 'ok' }) };
    }
    return { ok: true, json: async () => ({}) };
  });

  const backend = {
    apiGet: async (url) => {
      apiGetCalls.push(url);
      if (url === '/api/models') {
        return options.updatedModelsInfo || {
          active_profile: 'qwen2.5-7b',
          profiles: [
            { id: 'auto', name: 'Auto', downloaded: null },
            { id: 'qwen2.5-7b', name: 'Qwen 2.5 7B', downloaded: true },
          ],
          loaded: { profile_id: 'qwen2.5-7b', name: 'Qwen 2.5 7B', engine: 'gpu' },
          gpu_engine: { available: true, running: true, vram_mb: 8192 },
        };
      }
      if (url.includes('/api/egress/status')) {
        return { offline: false, local_only: false };
      }
      if (url.includes('/api/egress/log')) {
        return { events: [] };
      }
      if (url.includes('/api/unlock/status')) {
        return { is_unlocked: true, auto_lock_minutes: 15 };
      }
      if (url.includes('/api/secrets')) {
        return { secrets: [] };
      }
      if (url.includes('/api/retention')) {
        return { retention_chat_days: 180, retention_research_days: 90 };
      }
      return {};
    },
    apiPost: async () => ({}),
    ApiError: class ApiError extends Error {},
    timeAgo: () => 'just now',
  };

  const sandbox = {
    exports: {},
    Error: globalThis.Error,
    console: { log: () => {}, error: () => {}, warn: () => {} },
    setTimeout: (fn, ms) => setTimeout(fn, ms || 0),
    clearTimeout: (id) => clearTimeout(id),
    setInterval: (fn, ms) => setInterval(fn, ms || 0),
    clearInterval: (id) => clearInterval(id),
    window: {
      confirm: () => true,
      setInterval: () => 1,
      clearInterval: () => {},
      setTimeout: (fn, ms) => setTimeout(fn, ms || 0),
      clearTimeout: (id) => clearTimeout(id),
      sentinel: {
        auth: {
          getBackendPort: async () => 8000,
          getSessionToken: async () => 'test-token',
        },
      },
    },
    fetch: fetchMock,
    require(name) {
      if (name === 'react') return react;
      if (name === './SettingsPanel.css') return {};
      if (name === './VoiceSettings') return dummyComponent;
      if (name === './BackupSettings') return dummyComponent;
      if (name === './GoogleSettings') return dummyComponent;
      if (name === './ReadinessPanel') return dummyComponent;
      if (name === './ModelStatus') return modelStatusSandbox.exports.default || modelStatusSandbox.exports.ModelStatus;
      if (name === '../../lib/backend') return backend;
      throw new Error(`Unexpected import in SettingsPanel: ${name}`);
    },
  };

  vm.runInNewContext(compiledSettingsPanel, sandbox);

  function render() {
    stateCursor = 0;
    effectCursor = 0;
    tree = sandbox.exports.default({});
    return tree;
  }

  render();
  const cleanups = effectSlots.map(entry => entry.effect ? entry.effect() : undefined);

  return {
    get tree() { return tree; },
    render,
    find: (predicate, startNode) => find(startNode || tree, predicate),
    findAll: (predicate, startNode) => findAll(startNode || tree, predicate),
    fetchCalls,
    apiGetCalls,
    cleanup: () => cleanups.forEach(c => c && c()),
  };
}

test('SettingsPanel: renders ModelStatus component and preserves dropdown onChange', async () => {
  const harness = createSettingsPanelHarness();

  // Allow initial mount effect to complete
  await new Promise(r => setTimeout(r, 10));
  harness.render();

  // Find the select dropdown
  const selectNode = harness.find(n => n.type === 'select' && n.props?.className === 'settings-dropdown');
  assert.ok(selectNode, 'Expected to find model select dropdown in SettingsPanel');

  // Verify dropdown contains options
  const optionNodes = harness.findAll(n => n.type === 'option', selectNode);
  assert.ok(optionNodes.length >= 2, `Expected at least 2 model options, found ${optionNodes.length}`);

  // Find model-status-container rendered by ModelStatus
  const statusContainer = harness.find(n => n.props?.className === 'model-status-container');
  assert.ok(statusContainer, 'Expected ModelStatus component to be mounted in SettingsPanel');

  // Simulate user changing dropdown selection to 'qwen2.5-7b'
  assert.equal(typeof selectNode.props.onChange, 'function', 'onChange handler must be attached to select');
  await selectNode.props.onChange({ target: { value: 'qwen2.5-7b' } });

  // Settle async operations
  await new Promise(r => setTimeout(r, 20));

  // Verify POST /api/models/select was dispatched with exact payload
  const selectPost = harness.fetchCalls.find(c => c.url.includes('/api/models/select'));
  assert.ok(selectPost, 'Expected fetch POST to /api/models/select');
  assert.equal(selectPost.init.method, 'POST');
  assert.equal(selectPost.init.headers['X-Sentinel-Session'], 'test-token');
  const parsedBody = JSON.parse(selectPost.init.body);
  assert.deepEqual(parsedBody, { profile_id: 'qwen2.5-7b' });

  // Verify /api/models was refreshed after change
  assert.ok(harness.apiGetCalls.includes('/api/models'), 'Expected apiGet /api/models refresh');

  harness.cleanup();
});

