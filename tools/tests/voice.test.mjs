import test from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { encodeWav } from '../../frontend/src/lib/audio.ts';
const require = createRequire(import.meta.url);
const { installMicrophonePermissions } = require('../../src/main/core/media-permissions.js');

test('WAV contains bounded mono PCM at 16 kHz with clipped samples', async () => {
  const view = new DataView(await encodeWav([new Float32Array([2, -2, 0])], 16000).arrayBuffer());
  assert.equal(view.byteLength, 50);
  assert.equal(view.getUint32(24, true), 16000);
  assert.equal(view.getUint16(22, true), 1);
  assert.equal(view.getUint16(34, true), 16);
  assert.equal(view.getInt16(44, true), 32767);
  assert.equal(view.getInt16(46, true), -32768);
  assert.equal(view.getInt16(48, true), 0);
});

test('WAV downsamples 48 kHz recordings and caps duration at 30 seconds', async () => {
  const recording = new Float32Array(48000 * 31).fill(.5);
  const view = new DataView(await encodeWav([recording], 48000).arrayBuffer());
  assert.equal(view.getUint32(40, true), 16000 * 30 * 2);
  assert.equal(view.getInt16(44, true), 16384);
});

function permissions() {
  let check, request;
  const contents = { getURL: () => 'file:///app/index.html', session: {
    setPermissionCheckHandler: handler => { check = handler; },
    setPermissionRequestHandler: handler => { request = handler; },
  } };
  installMicrophonePermissions(contents, url => url === 'file:///app/index.html');
  const details = { isMainFrame: true, requestingUrl: 'file:///app/index.html', mediaType: 'audio', mediaTypes: ['audio'] };
  return { contents, details, check, request };
}

test('trusted main frame can request audio only', () => {
  const p = permissions();
  assert.equal(p.check(p.contents, 'media', 'file://', p.details), true);
  p.request(p.contents, 'media', allowed => assert.equal(allowed, true), p.details);
});

for (const [name, update, requester, permission] of [
  ['camera', { mediaType: 'video', mediaTypes: ['video'] }],
  ['embedded frame', { isMainFrame: false }],
  ['untrusted page', { requestingUrl: 'https://example.com/' }],
  ['unknown request', { mediaType: 'unknown', mediaTypes: [] }],
  ['different window', {}, {}],
  ['service worker', {}, null],
  ['screen capture', {}, undefined, 'display-capture'],
]) {
  test(`permission denied for ${name}`, () => {
    const p = permissions();
    const contents = requester === undefined ? p.contents : requester;
    const details = { ...p.details, ...update };
    assert.equal(p.check(contents, permission || 'media', 'file://', details), false);
    p.request(contents, permission || 'media', allowed => assert.equal(allowed, false), details);
  });
}

test('combined audio and video request is denied', () => {
  const p = permissions();
  p.request(p.contents, 'media', allowed => assert.equal(allowed, false), { ...p.details, mediaTypes: ['audio', 'video'] });
});
