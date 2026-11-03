/** Release server-only lookup ownership before measuring client preparation. */
const assert = require('node:assert/strict');
const {performance} = require('node:perf_hooks');

function releaseAssetLookups(owners, {collectGarbage = global.gc} = {}) {
  assert.ok(Array.isArray(owners) && owners.length);
  assert.equal(new Set(owners.map(item => item.owner)).size, owners.length);
  for (const {name, owner} of owners) {
    assert.ok(typeof name === 'string' && name && owner && owner.assets && typeof owner.assets === 'object');
  }
  const before = process.memoryUsage();
  const released = owners.map(({name, owner}) => {
    const entries = Object.keys(owner.assets).length;
    owner.assets = {};
    return {name, releasedAssetEntries: entries, retainedAssetEntries: Object.keys(owner.assets).length};
  });
  // A caller can retain unrelated source proofs, buffer hashes and metadata.
  // Never retain the released dictionaries in this function's return value.
  const start = performance.now();
  if (typeof collectGarbage === 'function') collectGarbage();
  return {released, before, after: process.memoryUsage(), garbageCollectionRequested: typeof collectGarbage === 'function',
    garbageCollectionMs: performance.now() - start};
}

function scopeAssetLookups(assets, references) {
  const scoped = {};
  for (const asset of references) {
    assert.ok(asset.url.startsWith('/api/district-plans/'));
    const key = asset.url.slice('/api/district-plans/'.length);
    const entry = assets[key]; assert.ok(entry, asset.url);
    assert.equal(entry.rawSha256, asset.sha256); assert.equal(entry.rawBytes, asset.bytes); assert.equal(entry.gzipBytes, asset.gzipBytes);
    scoped[key] = entry;
  }
  return scoped;
}

module.exports = {releaseAssetLookups, scopeAssetLookups};
