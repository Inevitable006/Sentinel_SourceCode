// F16: Windows lock and sleep lock Sentinel. (Static check; the real event needs a manual test.)
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.join(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
const main = fs.readFileSync(path.join(root, 'src', 'main', 'main.js'), 'utf8');
const preload = fs.readFileSync(path.join(root, 'src', 'main', 'preload.js'), 'utf8');

test('powerMonitor lock-screen and suspend call the authenticated lock endpoint', () => {
  assert.match(main, /powerMonitor\.on\('lock-screen',\s*\(\)\s*=>\s*lockSentinel\(/);
  assert.match(main, /powerMonitor\.on\('suspend',\s*\(\)\s*=>\s*lockSentinel\(/);
  assert.match(main, /path:\s*'\/api\/lock',\s*method:\s*'POST'/);
  assert.match(main, /'X-Sentinel-Session':\s*global\.SENTINEL_SESSION_TOKEN/);
  assert.match(main, /host:\s*'127\.0\.0\.1'/);
});

test('the renderer can only listen for the lock notice, not trigger anything', () => {
  assert.match(preload, /ipcRenderer\.on\('sentinel-locked'/);
  assert.doesNotMatch(preload, /ipcRenderer\.(send|invoke)\('sentinel-locked'/);
});
