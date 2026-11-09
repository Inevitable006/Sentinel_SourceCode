import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { createRequire } from 'node:module';
import vm from 'node:vm';

const require = createRequire(new URL('../../frontend/package.json', import.meta.url));
const ts = require('typescript');
const source = fs.readFileSync(new URL('../../frontend/src/components/Settings/ReadinessPanel.tsx', import.meta.url), 'utf8');
const compiled = ts.transpileModule(source, { compilerOptions: {
  module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.React, esModuleInterop: true,
} }).outputText;

// Executes the production component logic. These adapters do not simulate DOM layout.
function harness() {
  const slots = [], effects = [], requests = [];
  let cursor = 0;
  const react = {
    createElement: (type, props, ...children) => ({ type, props, children }),
    useState(initial) {
      const index = cursor++;
      if (!(index in slots)) slots[index] = initial;
      return [slots[index], value => { slots[index] = value; }];
    },
    useRef(initial) {
      const index = cursor++;
      if (!(index in slots)) slots[index] = { current: initial };
      return slots[index];
    },
    useEffect(effect) { effects.push(effect); },
  };
  class ApiError extends Error {
    constructor(status) { super('synthetic failure'); this.status = status; }
  }
  const backend = { ApiError, apiGet: () => new Promise((resolve, reject) => requests.push({ resolve, reject })) };
  const exports = {};
  vm.runInNewContext(compiled, { exports, require(name) {
    if (name === 'react') return react;
    if (name === '../../lib/backend') return backend;
    if (name.endsWith('.css')) return {};
    throw new Error(`Unexpected import ${name}`);
  } });
  const tree = exports.default();
  const cleanups = effects.map(effect => effect());
  function find(node, predicate) {
    if (!node || typeof node !== 'object') return null;
    if (predicate(node)) return node;
    return (node.children || []).flat(Infinity).map(child => find(child, predicate)).find(Boolean);
  }
  return { exports, slots, requests, ApiError,
    refresh: () => find(tree, node => node.type === 'button').props.onClick(),
    cleanup: () => cleanups.forEach(cleanup => cleanup?.()),
    replay: () => effects.forEach(effect => effect()),
  };
}
const valid = () => ({ version: 1, checks: [{ id: 'chat', label: 'Chat', state: 'ready', detail: 'Local runtime present.' }] });
const settle = () => new Promise(resolve => setImmediate(resolve));

test('actual readiness validator rejects malformed success payloads', () => {
  const h = harness();
  const check = h.exports.validateReadinessResponse;
  assert.equal(check(valid()), null);
  for (const data of [null, { ...valid(), version: 2 }, { ...valid(), checks: Array(7).fill(valid().checks[0]) },
    { ...valid(), checks: Array(2).fill(valid().checks[0]) },
    ...[{ id: 'future' }, { label: '' }, { detail: ' ' }, { state: 'green' }, { label: 'x'.repeat(81) }]
      .map(change => ({ version: 1, checks: [{ ...valid().checks[0], ...change }] }))]) {
    assert.equal(typeof check(data), 'string');
  }
  h.cleanup();
});

test('failed refresh clears previously successful readiness', async () => {
  const h = harness();
  h.requests[0].resolve(valid()); await settle();
  assert.equal(h.slots[0][0].state, 'ready');
  h.refresh(); h.requests[1].reject(new h.ApiError(423)); await settle();
  assert.equal(h.slots[0], null);
  assert.match(h.slots[2], /locked/i);
});

test('StrictMode replay drops older success after newer lock failure', async () => {
  const h = harness();
  h.cleanup(); h.replay();
  h.requests[1].reject(new h.ApiError(423)); await settle();
  h.requests[0].resolve(valid()); await settle();
  assert.equal(h.slots[0], null);
  assert.match(h.slots[2], /locked/i);
  assert.equal(h.slots[1], false);
});

test('cleanup ignores late success and does not update state', async () => {
  const h = harness();
  h.cleanup();
  const before = h.slots.slice(0, 3);
  h.requests[0].resolve(valid()); await settle();
  assert.deepEqual(h.slots.slice(0, 3), before);
});

test('older failure cannot clear a newer pending request', async () => {
  const h = harness();
  h.cleanup(); h.replay();
  h.requests[0].reject(new h.ApiError(401)); await settle();
  assert.equal(h.slots[1], true);
  assert.equal(h.slots[2], null);
  h.requests[1].resolve(valid()); await settle();
  assert.equal(h.slots[0][0].state, 'ready');
  assert.equal(h.slots[1], false);
});

test('invalid refresh discards prior positive badges', async () => {
  const h = harness();
  h.requests[0].resolve(valid()); await settle();
  h.refresh(); h.requests[1].resolve({ ...valid(), version: 99 }); await settle();
  assert.equal(h.slots[0], null);
  assert.match(h.slots[2], /invalid/i);
});
