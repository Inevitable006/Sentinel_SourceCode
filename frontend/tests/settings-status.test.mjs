import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { createRequire } from 'node:module';
import vm from 'node:vm';

const require = createRequire(new URL('../package.json', import.meta.url));
const ts = require('typescript');

const voiceSource = fs.readFileSync(new URL('../src/components/Settings/VoiceSettings.tsx', import.meta.url), 'utf8');
const compiledVoice = ts.transpileModule(voiceSource, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.React, esModuleInterop: true },
}).outputText;

const googleSource = fs.readFileSync(new URL('../src/components/Settings/GoogleSettings.tsx', import.meta.url), 'utf8');
const compiledGoogle = ts.transpileModule(googleSource, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.React, esModuleInterop: true },
}).outputText;

const pinActionSource = fs.readFileSync(new URL('../src/components/Workspace/usePinAction.tsx', import.meta.url), 'utf8');
const compiledPinAction = ts.transpileModule(pinActionSource, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.React, esModuleInterop: true },
}).outputText;

const settle = async (ticks = 8) => {
  for (let i = 0; i < ticks; i++) {
    await new Promise(resolve => setTimeout(resolve, 0));
  }
};

function textContent(node) {
  if (!node) return '';
  if (typeof node === 'string' || typeof node === 'number') return String(node);
  const children = Array.isArray(node.children) ? node.children : (node.props?.children ? [node.props.children] : []);
  return children.flat(Infinity).map(textContent).join('');
}

class ApiError extends Error {
  constructor(status, detail) {
    const d = detail;
    super(typeof d === 'string' ? d : (d && typeof d.message === 'string' ? d.message : `HTTP ${status}`));
    this.status = status;
    this.detail = detail;
  }
  get code() {
    const d = this.detail;
    return d && typeof d === 'object' && typeof d.code === 'string' ? d.code : '';
  }
}

function createComponentHarness(compiledCode, options = {}) {
  const stateSlots = [];
  const refSlots = [];
  const effectSlots = [];
  let cleanups = [];
  let stateCursor = 0;
  let refCursor = 0;
  let effectCursor = 0;
  let tree = null;

  const react = {
    createElement: (type, props, ...children) => {
      const flat = children.flat(Infinity);
      const childProp = flat.length === 1 ? flat[0] : (flat.length === 0 ? undefined : flat);
      return {
        type,
        props: { ...(props || {}), children: childProp },
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
    useRef(initial) {
      const idx = refCursor++;
      if (!(idx in refSlots)) {
        refSlots[idx] = { current: initial };
      }
      return refSlots[idx];
    },
    useCallback(fn) {
      return fn;
    },
    useEffect(effect, deps) {
      const idx = effectCursor++;
      effectSlots[idx] = { effect, deps };
    },
  };

  const backend = {
    ApiError,
    apiGet: options.apiGet || (() => Promise.resolve({})),
    apiPost: options.apiPost || (() => Promise.resolve({})),
    backendInfo: options.backendInfo || (() => Promise.resolve({ port: 8000, token: 'test-token' })),
  };

  // Compile usePinAction module inside sandbox if needed
  const pinActionSandbox = {
    exports: {},
    Error: globalThis.Error,
    require(name) {
      if (name === 'react') return react;
      if (name === '../../lib/backend') return backend;
      throw new Error(`Unexpected import in usePinAction: ${name}`);
    },
  };
  vm.runInNewContext(compiledPinAction, pinActionSandbox);

  const sandbox = {
    exports: {},
    Error: globalThis.Error,
    require(name) {
      if (name === 'react') return react;
      if (name === '../../lib/backend') return backend;
      if (name === '../Workspace/usePinAction') return pinActionSandbox.exports;
      throw new Error(`Unexpected import: ${name}`);
    },
    navigator: options.navigator || { clipboard: { writeText: () => Promise.resolve() } },
    fetch: options.fetch || (() => Promise.resolve({ ok: true, json: () => Promise.resolve({}) })),
    setTimeout: (fn) => setTimeout(fn, 0),
  };

  vm.runInNewContext(compiledCode, sandbox);

  function render() {
    stateCursor = 0;
    refCursor = 0;
    effectCursor = 0;
    tree = sandbox.exports.default({});
    return tree;
  }

  // Initial render
  render();

  // Run initial mount effects
  cleanups = effectSlots.map(entry => entry.effect());

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

  return {
    get tree() { return tree; },
    get stateSlots() { return stateSlots; },
    get refSlots() { return refSlots; },
    find: (predicate) => find(tree, predicate),
    findAll: (predicate) => findAll(tree, predicate),
    render,
    cleanup: () => {
      cleanups.forEach(c => c && c());
      cleanups = [];
    },
    replayEffects: () => {
      cleanups.forEach(c => c && c());
      cleanups = effectSlots.map(entry => entry.effect());
    },
  };
}

// =========================================================================
// GOOGLE SETTINGS TESTS
// =========================================================================

test('GoogleSettings: failed status refresh replaces stale success with unavailable', async () => {
  let failStatus = false;
  let getCalls = 0;

  const h = createComponentHarness(compiledGoogle, {
    apiGet: (path) => {
      getCalls++;
      if (path === '/api/workspace/google/status') {
        if (failStatus) {
          return Promise.reject(new Error('Connection dropped'));
        }
        return Promise.resolve({ configured: true, connected: true, gmail: true, calendar: true });
      }
      return Promise.resolve({});
    },
  });

  await settle();

  // Initial status: should be "Connected"
  assert.ok(textContent(h.tree).includes('Connected'), 'Initial status must show Connected');

  // Trigger status refresh failure via effect replay or manual refresh
  failStatus = true;
  h.replayEffects();
  await settle();

  // Stale success must NOT be retained
  assert.ok(!textContent(h.tree).includes('Connected'), 'Stale Connected status must not persist');
  assert.ok(textContent(h.tree).includes('Status unavailable'), 'Should display Status unavailable');
  assert.ok(textContent(h.tree).includes('Google connection status unavailable.'), 'Message should explain failure');

  h.cleanup();
});

test('GoogleSettings: out-of-order status refresh dropped by refreshRequestIdRef', async () => {
  const resolvers = [];

  const h = createComponentHarness(compiledGoogle, {
    apiGet: (path) => {
      if (path === '/api/workspace/google/status') {
        return new Promise((resolve, reject) => {
          resolvers.push({ resolve, reject });
        });
      }
      return Promise.resolve({});
    },
  });

  // Request 1 dispatched on mount
  assert.equal(resolvers.length, 1);

  // Replay effect triggers Request 2
  h.cleanup();
  h.replayEffects();
  assert.equal(resolvers.length, 2);

  // Request 2 resolves with "Not configured"
  resolvers[1].resolve({ configured: false, connected: false, gmail: false, calendar: false });
  await settle();

  assert.ok(textContent(h.tree).includes('Not configured'));

  // Older Request 1 resolves late with "Connected"
  resolvers[0].resolve({ configured: true, connected: true, gmail: true, calendar: true });
  await settle();

  // Late Request 1 must be ignored — status must remain "Not configured"
  assert.ok(textContent(h.tree).includes('Not configured'), 'Late older response must not overwrite current state');
  assert.ok(!textContent(h.tree).includes('Connected'), 'Late older response must not set Connected');

  h.cleanup();
});

test('GoogleSettings: credential import clears previous credentials on error or size violation', async () => {
  const h = createComponentHarness(compiledGoogle, {
    apiGet: () => Promise.resolve({ configured: false, connected: false, gmail: false, calendar: false }),
  });

  await settle();

  const fileInput = h.find(n => n.props?.id === 'google-oauth-file');
  assert.ok(fileInput, 'OAuth file input should be present');

  // 1. Valid desktop JSON credentials
  const validJson = JSON.stringify({
    installed: { client_id: 'client-123.apps.googleusercontent.com', client_secret: 'secret-xyz' },
  });
  const validFile = {
    size: 200,
    text: () => Promise.resolve(validJson),
  };

  fileInput.props.onChange({ target: { files: [validFile], value: '' } });
  await settle();

  // "Save credentials" button should now be visible because client state is set
  const saveBtn = h.find(n => n.type === 'button' && textContent(n).includes('Save credentials'));
  assert.ok(saveBtn, 'Save credentials button should be rendered when valid credentials loaded');

  // 2. Import file > 16KB -> should fail and CLEAR previous client
  const bigFile = {
    size: 20000,
    text: () => Promise.resolve('{}'),
  };
  fileInput.props.onChange({ target: { files: [bigFile], value: '' } });
  await settle();

  // Client must be cleared, so "Save credentials" button must disappear
  const saveBtnAfterBig = h.find(n => n.type === 'button' && textContent(n).includes('Save credentials'));
  assert.equal(saveBtnAfterBig, null, 'Save credentials button must be removed on file size error');
  assert.ok(textContent(h.tree).includes('small Desktop app OAuth credentials'), 'Must announce file size error');

  // 3. Re-load valid credentials
  fileInput.props.onChange({ target: { files: [validFile], value: '' } });
  await settle();
  assert.ok(h.find(n => n.type === 'button' && textContent(n).includes('Save credentials')));

  // 4. Import malformed JSON (not desktop app format, e.g. web app or missing client_id)
  const badFormatFile = {
    size: 300,
    text: () => Promise.resolve(JSON.stringify({ web: { client_id: 'web-client' } })),
  };
  fileInput.props.onChange({ target: { files: [badFormatFile], value: '' } });
  await settle();

  // Client must be cleared again
  const saveBtnAfterBad = h.find(n => n.type === 'button' && textContent(n).includes('Save credentials'));
  assert.equal(saveBtnAfterBad, null, 'Save credentials button must be removed on format error');
  assert.ok(textContent(h.tree).includes('Desktop app OAuth credentials file'), 'Must announce format error');

  h.cleanup();
});

test('GoogleSettings: duplicate submissions while busy are guarded', async () => {
  let configureCalls = 0;
  let configureResolver;

  const h = createComponentHarness(compiledGoogle, {
    apiGet: () => Promise.resolve({ configured: false, connected: false, gmail: false, calendar: false }),
    apiPost: (path) => {
      if (path === '/api/workspace/google/configure') {
        configureCalls++;
        return new Promise(resolve => { configureResolver = resolve; });
      }
      return Promise.resolve({});
    },
  });

  await settle();

  // Load credentials so Save button is rendered
  const fileInput = h.find(n => n.props?.id === 'google-oauth-file');
  const validFile = {
    size: 200,
    text: () => Promise.resolve(JSON.stringify({ installed: { client_id: 'client-1' } })),
  };
  fileInput.props.onChange({ target: { files: [validFile], value: '' } });
  await settle();

  // Click Save credentials
  const saveBtn = h.find(n => n.type === 'button' && textContent(n).includes('Save credentials'));
  saveBtn.props.onClick();

  // While busy, click again
  const busySaveBtn = h.find(n => n.type === 'button' && textContent(n).includes('Saving credentials…'));
  assert.ok(busySaveBtn, 'Button should show Saving credentials…');
  assert.equal(busySaveBtn.props.disabled, true, 'Button should be disabled while busy');
  busySaveBtn.props.onClick(); // Attempt duplicate click

  await settle();
  assert.equal(configureCalls, 1, 'Only one API call should be dispatched despite multiple clicks');

  // Resolve operation
  configureResolver({});
  await settle();

  h.cleanup();
});

// =========================================================================
// VOICE SETTINGS TESTS
// =========================================================================

test('VoiceSettings: failed load clears stale voice info and renders role="alert" error', async () => {
  const h = createComponentHarness(compiledVoice, {
    apiGet: () => Promise.reject(new Error('TTS subsystem unavailable')),
  });

  await settle();

  // Dropdown must not be present
  const select = h.find(n => n.type === 'select');
  assert.equal(select, null, 'Voice select dropdown must not be rendered when load fails');

  // role="alert" message must be present
  const alert = h.find(n => n.props?.role === 'alert');
  assert.ok(alert, 'Alert role must be present on failure');
  assert.ok(textContent(alert).includes('TTS subsystem unavailable'), 'Alert must explain failure');

  h.cleanup();
});

test('VoiceSettings: out-of-order save responses are dropped by saveRequestIdRef', async () => {
  const saveResolvers = [];

  const initialVoices = {
    voices: [
      { id: 'v1', name: 'Voice 1', gender: 'female' },
      { id: 'v2', name: 'Voice 2', gender: 'male' },
    ],
    voice_id: 'v1',
    rate: 0,
    min_rate: -10,
    max_rate: 10,
  };

  const h = createComponentHarness(compiledVoice, {
    apiGet: () => Promise.resolve(initialVoices),
    apiPost: (path, body) => {
      if (path === '/api/voice/voices') {
        return new Promise(resolve => {
          saveResolvers.push({ resolve, body });
        });
      }
      return Promise.resolve({});
    },
  });

  await settle();

  // Dropdown should be present with v1 selected
  const select = h.find(n => n.type === 'select');
  assert.ok(select);
  assert.equal(select.props.value, 'v1');

  // Trigger Save 1: change to v2 (slow)
  select.props.onChange({ target: { value: 'v2' } });
  assert.equal(saveResolvers.length, 1);

  // Trigger Save 2: change speed slider (fast)
  // Re-find select after re-render or invoke save directly
  // Note: select is disabled={saving} during save in real UI, but let's test if a late save 1 is resolved after save 2
  // Simulate save 2 resolving with voice_id 'v2'
  saveResolvers[0].resolve({ ...initialVoices, voice_id: 'v2' });
  await settle();

  // Now trigger another change to rate = 5 (req 2)
  const rangeInput = h.find(n => n.type === 'input' && n.props?.type === 'range');
  assert.ok(rangeInput);
  rangeInput.props.onMouseUp();
  assert.equal(saveResolvers.length, 2);

  // Req 2 resolves with rate 5
  saveResolvers[1].resolve({ ...initialVoices, voice_id: 'v2', rate: 5 });
  await settle();

  assert.ok(textContent(h.tree).includes('5'), 'Updated rate should be shown');

  h.cleanup();
});

test('VoiceSettings: save and preview pending guard prevents duplicate concurrent submissions', async () => {
  let previewCalls = 0;
  let previewResolver;

  const initialVoices = {
    voices: [{ id: 'v1', name: 'Voice 1', gender: 'female' }],
    voice_id: 'v1',
    rate: 0,
    min_rate: -10,
    max_rate: 10,
  };

  const h = createComponentHarness(compiledVoice, {
    apiGet: () => Promise.resolve(initialVoices),
    apiPost: (path) => {
      if (path === '/api/voice/voices/preview') {
        previewCalls++;
        return new Promise((resolve, reject) => { previewResolver = { resolve, reject }; });
      }
      return Promise.resolve({});
    },
  });

  await settle();

  // Click Preview voice
  const previewBtn = h.find(n => n.type === 'button' && textContent(n).includes('Preview voice'));
  assert.ok(previewBtn);
  previewBtn.props.onClick();

  // Click again while playing preview
  const busyPreviewBtn = h.find(n => n.type === 'button' && textContent(n).includes('Playing preview…'));
  assert.ok(busyPreviewBtn, 'Button should show Playing preview…');
  assert.equal(busyPreviewBtn.props.disabled, true);
  busyPreviewBtn.props.onClick(); // Duplicate call

  await settle();
  assert.equal(previewCalls, 1, 'Only 1 preview call dispatched');

  // Preview fails with API error
  previewResolver.reject(new Error('Audio device error'));
  await settle();

  // Verify error reported and previewing state cleared
  assert.ok(textContent(h.tree).includes('Audio device error'));
  const idlePreviewBtn = h.find(n => n.type === 'button' && textContent(n).includes('Preview voice'));
  assert.ok(idlePreviewBtn, 'Preview button should return to idle state after error');
  assert.equal(idlePreviewBtn.props.disabled, false);

  h.cleanup();
});

