import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { createRequire } from 'node:module';
import vm from 'node:vm';

const require = createRequire(new URL('../package.json', import.meta.url));
const ts = require('typescript');
const source = fs.readFileSync(new URL('../src/components/Settings/BackupSettings.tsx', import.meta.url), 'utf8');
const compiled = ts.transpileModule(source, {
  compilerOptions: {
    module: ts.ModuleKind.CommonJS,
    jsx: ts.JsxEmit.React,
    esModuleInterop: true,
  },
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

function createHarness(options = {}) {
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

  const backend = {
    ApiError,
    apiGet: options.apiGet || (() => Promise.resolve({ backups: [] })),
    apiPost: options.apiPost || (() => Promise.resolve({})),
    backendInfo: options.backendInfo || (() => Promise.resolve({ port: 8000, token: 'test-token' })),
  };

  const mockDocument = options.document || {
    createElement: () => ({ click: () => {} }),
  };

  const mockURL = options.URL || {
    createObjectURL: () => 'blob:mock',
    revokeObjectURL: () => {},
  };

  const mockFetch = options.fetch || (() => Promise.resolve({
    ok: true,
    blob: () => Promise.resolve({ size: 1024 }),
  }));

  const sandbox = {
    exports: {},
    Error: globalThis.Error,
    require(name) {
      if (name === 'react') return react;
      if (name === '../../lib/backend') return backend;
      throw new Error(`Unexpected import: ${name}`);
    },
    fetch: mockFetch,
    document: mockDocument,
    URL: mockURL,
    setTimeout: (fn) => setTimeout(fn, 0),
  };

  vm.runInNewContext(compiled, sandbox);

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
    textContent,
    ApiError,
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

test('create backup PIN retry dispatches create with exact untrimmed PIN', async () => {
  const postCalls = [];
  let rejectWithPinRequired = true;

  const h = createHarness({
    apiGet: () => Promise.resolve({ backups: [] }),
    apiPost: (url, body) => {
      postCalls.push({ url, body });
      if (url === '/api/backup/create') {
        if (rejectWithPinRequired) {
          rejectWithPinRequired = false;
          return Promise.reject(new h.ApiError(403, { code: 'pin_required', message: 'Owner PIN required.' }));
        }
        return Promise.resolve({ name: 'sentinel-20261101.enc', size: 1048576 });
      }
      return Promise.resolve({});
    },
  });

  await settle();

  // Initially: no PIN form is shown
  assert.equal(h.find(n => n.type === 'form'), null);

  // Click "Create backup now"
  const createBtn = h.find(n => n.type === 'button' && textContent(n).includes('Create backup now'));
  assert.ok(createBtn, 'Create backup button should be present');
  createBtn.props.onClick();
  await settle();

  // PIN prompt is now visible
  assert.ok(h.find(n => n.type === 'form'), 'PIN form should appear after pin_required');

  const pinInput = h.find(n => n.props?.id === 'backup-pin-input');
  assert.ok(pinInput, 'PIN input should be present');

  // Owner enters exact PIN containing whitespace
  const whitespacePin = '  secret pin 123  ';
  pinInput.props.onChange({ target: { value: whitespacePin } });

  // Get re-rendered form with updated state closure and submit
  const form = h.find(n => n.type === 'form');
  assert.ok(form, 'Form should be present');
  let prevented = false;
  form.props.onSubmit({ preventDefault: () => { prevented = true; } });
  assert.ok(prevented, 'onSubmit should preventDefault');

  await settle();

  // Verify create was retried with exact untrimmed PIN
  assert.equal(postCalls.length, 2);
  assert.equal(postCalls[0].url, '/api/backup/create');
  assert.equal(postCalls[0].body.pin, undefined);

  assert.equal(postCalls[1].url, '/api/backup/create');
  assert.equal(postCalls[1].body.pin, whitespacePin, 'Whitespace in PIN must be preserved exactly without trimming');

  // Verify PIN prompt dismissed and state reset
  assert.equal(h.find(n => n.type === 'form'), null);
  h.cleanup();
});

test('save backup copy PIN retry dispatches download for target file with exact untrimmed PIN', async () => {
  const fetchCalls = [];
  const postCalls = [];
  let rejectFetchWithPin = true;

  const backupList = [{ name: 'sentinel-20261101.enc', size: 2097152, created: '2026-11-01T10:00:00' }];

  const h = createHarness({
    apiGet: () => Promise.resolve({ backups: backupList }),
    apiPost: (url, body) => {
      postCalls.push({ url, body });
      return Promise.resolve({});
    },
    fetch: (url, options) => {
      fetchCalls.push({ url, options });
      if (rejectFetchWithPin) {
        rejectFetchWithPin = false;
        return Promise.resolve({
          ok: false,
          status: 403,
          json: () => Promise.resolve({ detail: { code: 'pin_required', message: 'Enter your PIN to save a backup copy.' } }),
        });
      }
      return Promise.resolve({
        ok: true,
        blob: () => Promise.resolve({ size: 2097152 }),
      });
    },
  });

  await settle();

  // Find "Save a copy…" button for the backup
  const saveBtn = h.find(n => n.type === 'button' && n.props?.['aria-label']?.includes('Save a copy'));
  assert.ok(saveBtn, 'Save button should be present in listing');

  // Click "Save a copy…"
  saveBtn.props.onClick();
  await settle();

  // Form should now appear for PIN
  assert.ok(h.find(n => n.type === 'form'), 'PIN form should appear');

  const pinInput = h.find(n => n.props?.id === 'backup-pin-input');
  assert.ok(pinInput, 'PIN input should be present');

  // Enter exact PIN with leading and trailing spaces
  const exactPin = '   pin with spaces   ';
  pinInput.props.onChange({ target: { value: exactPin } });

  // Get re-rendered form with updated state closure and submit PIN
  const form = h.find(n => n.type === 'form');
  assert.ok(form, 'Form should be present');
  form.props.onSubmit({ preventDefault: () => {} });
  await settle();

  // Verify apiPost('/api/backup/create') was NEVER called!
  assert.equal(postCalls.length, 0, 'Must NOT dispatch create when saving a copy');

  // Verify fetch was called with the exact download URL and untrimmed PIN
  assert.equal(fetchCalls.length, 2);
  assert.ok(fetchCalls[0].url.includes('/api/backup/download/sentinel-20261101.enc'));

  assert.ok(fetchCalls[1].url.includes('/api/backup/download/sentinel-20261101.enc'));
  const bodyParsed = JSON.parse(fetchCalls[1].options.body);
  assert.equal(bodyParsed.pin, exactPin, 'Download PIN must be preserved exactly without trimming');

  // Form is closed after success
  assert.equal(h.find(n => n.type === 'form'), null);
  h.cleanup();
});

test('PIN cancellation clears pendingOp, needPin, and PIN input without dispatching action', async () => {
  const postCalls = [];
  const backupList = [{ name: 'sentinel-20261101.enc', size: 1024, created: '2026-11-01T10:00:00' }];

  const h = createHarness({
    apiGet: () => Promise.resolve({ backups: backupList }),
    apiPost: (url, body) => {
      postCalls.push({ url, body });
      return Promise.reject(new h.ApiError(403, { code: 'pin_required', message: 'PIN needed' }));
    },
  });

  await settle();

  // Trigger PIN prompt via create
  const createBtn = h.find(n => n.type === 'button' && textContent(n).includes('Create backup now'));
  createBtn.props.onClick();
  await settle();

  assert.ok(h.find(n => n.type === 'form'));

  // Type a partial PIN
  const pinInput = h.find(n => n.props?.id === 'backup-pin-input');
  pinInput.props.onChange({ target: { value: ' 12345 ' } });

  // Click Cancel button
  const cancelBtn = h.find(n => n.type === 'button' && textContent(n) === 'Cancel');
  assert.ok(cancelBtn, 'Cancel button should be present in PIN form');
  cancelBtn.props.onClick();

  // Form should be gone
  assert.equal(h.find(n => n.type === 'form'), null, 'PIN form should be dismissed on cancel');

  // Status message indicates cancellation
  const msg = h.find(n => n.props?.role === 'status' && textContent(n).includes('Operation cancelled.'));
  assert.ok(msg, 'Status message should announce cancellation');

  // Click create again - verify clean state (pin was cleared and previous pendingOp was cleared)
  createBtn.props.onClick();
  await settle();

  const freshPinInput = h.find(n => n.props?.id === 'backup-pin-input');
  assert.equal(freshPinInput.props.value, '', 'PIN field should be reset to empty');

  h.cleanup();
});

test('stale load response from earlier generation is rejected and does not overwrite current state', async () => {
  const pendingResolvers = [];

  const h = createHarness({
    apiGet: () => new Promise((resolve, reject) => {
      pendingResolvers.push({ resolve, reject });
    }),
  });

  // Request 1 is dispatched by initial mount
  assert.equal(pendingResolvers.length, 1);

  // Simulate StrictMode effect replay: cleanup then replay
  h.cleanup();
  h.replayEffects();

  // Request 2 is dispatched by replayed effect
  assert.equal(pendingResolvers.length, 2);

  // Request 2 (the current request) fails with an error
  pendingResolvers[1].reject(new Error('Locked storage'));
  await settle();

  // Verify component displays load error
  const alertEl = h.find(n => n.props?.role === 'alert');
  assert.ok(alertEl, 'Alert message should be rendered on failure');
  assert.ok(textContent(alertEl).includes('Locked storage'));

  // Stale Request 1 now resolves with an old backup list
  pendingResolvers[0].resolve({
    backups: [{ name: 'stale-backup.enc', size: 999999, created: '2026-10-01T00:00:00' }],
  });
  await settle();

  // Stale response must be dropped: alert remains, stale backups NOT rendered
  const staleAlert = h.find(n => n.props?.role === 'alert');
  assert.ok(staleAlert, 'Alert message should persist; stale data must not overwrite error');
  assert.ok(textContent(staleAlert).includes('Locked storage'));

  const staleItem = h.find(n => textContent(n).includes('stale-backup.enc'));
  assert.equal(staleItem, null, 'Stale backup entry must not be rendered');

  h.cleanup();
});
