// F17: main.js calls errorHandler.enterSafeMode(); that public method must exist and work.
import test from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const require = createRequire(import.meta.url);
const core = path.join(path.dirname(fileURLToPath(import.meta.url)), '..', '..', 'src', 'main', 'core');

// The real logger/app-paths need Electron; stub them before loading the error handler.
const quiet = { info() {}, warn() {}, error() {}, debug() {} };
require.cache[require.resolve(path.join(core, 'logger.js'))] = { exports: { logger: quiet } };
require.cache[require.resolve(path.join(core, 'app-paths.js'))] = { exports: { appPaths: { didCrash: () => false } } };
const { ErrorHandler } = require(path.join(core, 'error-handler.js'));

test('enterSafeMode is public, notifies once, and is idempotent', () => {
  const handler = new ErrorHandler();
  const calls = [];
  handler.onSafeModeChange = (on) => calls.push(on);
  assert.equal(typeof handler.enterSafeMode, 'function');
  handler.enterSafeMode(new Error('Backend could not be restarted'));
  handler.enterSafeMode(new Error('again'));
  assert.equal(handler.isSafeMode(), true);
  assert.deepEqual(calls, [true]);
});

test('main.js only calls error-handler methods that exist', async () => {
  const fs = await import('node:fs');
  const main = fs.readFileSync(path.join(core, '..', 'main.js'), 'utf8');
  const handler = new ErrorHandler();
  for (const [, name] of main.matchAll(/errorHandler\.(\w+)\(/g)) {
    assert.equal(typeof handler[name], 'function', `errorHandler.${name} is missing`);
  }
});
