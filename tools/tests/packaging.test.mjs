// F06: the installer ships its own runtime and never the developer's virtual environment.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.join(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
const pkg = JSON.parse(fs.readFileSync(path.join(root, 'package.json'), 'utf8'));
const main = fs.readFileSync(path.join(root, 'src', 'main', 'main.js'), 'utf8');

test('backend resources exclude the dev venv, models and logs but keep the verified GPU engine', () => {
  const backend = pkg.build.extraResources.find(r => r.from === 'backend');
  for (const rule of ['!.venv/**', '!models/**', '!**/*.log', '!tests/**']) assert.ok(backend.filter.includes(rule), rule);
  assert.ok(!backend.filter.includes('!llama-bin.zip'), 'GPU engine archive (hash-checked at runtime) must ship');
});

test('a portable Python runtime is packaged and used when installed', () => {
  assert.ok(pkg.build.extraResources.some(r => r.from === 'build/python-runtime' && r.to === 'python'));
  assert.match(main, /path\.join\(process\.resourcesPath, 'python', 'python\.exe'\)/);
  assert.doesNotMatch(main, /Users\\\\|OneDrive|AppData\\\\Local\\\\Python/);
});
