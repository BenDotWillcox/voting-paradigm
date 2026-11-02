"""Benchmark metadata release keeps immutable evidence and prepared inputs."""
from test_block_demo_integration_contract import run_node


def test_lookup_release_precedes_collection_and_preserves_nonlookup_references(tmp_path):
    run_node(tmp_path, r"""
const {releaseAssetLookups}=rootRequire('./scripts/state_explorer_benchmark_memory.cjs');
const proofs=Object.freeze({catalogSha256:'source-proof'}), buffers=new Map([['chunk',Buffer.from('pinned-buffer')]]);
const index={assets:{first:{path:'saved-a'},second:{path:'saved-b'}},proofs};
const blocks={assets:{third:{path:'saved-c'}},plans:Object.freeze({'02-2':{stateFips:'02'}})};
const geometry={assets:{fourth:{path:'saved-d'}},record:Object.freeze({coverage:'census'})};
const savedPlans=blocks.plans,savedGeometry=geometry.record;let collected=0;
const result=releaseAssetLookups([{name:'index',owner:index},{name:'blocks',owner:blocks},{name:'geometry',owner:geometry}],{
 collectGarbage(){collected++;assert.equal(Object.keys(index.assets).length,0);assert.equal(Object.keys(blocks.assets).length,0);assert.equal(Object.keys(geometry.assets).length,0);}
});
assert.equal(collected,1);assert.equal(result.garbageCollectionRequested,true);
assert.deepEqual(result.released.map(item=>item.releasedAssetEntries),[2,1,1]);
assert.ok(result.released.every(item=>item.retainedAssetEntries===0));
assert.equal(index.proofs,proofs);assert.equal(blocks.plans,savedPlans);assert.equal(geometry.record,savedGeometry);
assert.equal(buffers.get('chunk').toString(),'pinned-buffer');
assert.equal(JSON.stringify(result).includes('saved-a'),false,'Evidence must not accidentally retain old dictionaries');
""")


def test_lookup_release_rejects_invalid_owner_list_without_partial_mutation(tmp_path):
    run_node(tmp_path, r"""
const {releaseAssetLookups}=rootRequire('./scripts/state_explorer_benchmark_memory.cjs');
const retained={a:1},index={assets:retained};
assert.throws(()=>releaseAssetLookups([{name:'index',owner:index},{name:'missing',owner:{}}]));
assert.equal(index.assets,retained);
assert.throws(()=>releaseAssetLookups([{name:'index',owner:index},{name:'duplicate',owner:index}]));
assert.equal(index.assets,retained);
""")


def test_scoping_retains_only_exact_allowlisted_entries_and_rejects_mismatches(tmp_path):
    run_node(tmp_path, r"""
const {scopeAssetLookups}=rootRequire('./scripts/state_explorer_benchmark_memory.cjs');
const asset={url:'/api/district-plans/hash/blocks.json',sha256:'hash',bytes:100,gzipBytes:50};
const entry=Object.freeze({rawSha256:'hash',rawBytes:100,gzipBytes:50,path:'original-file'});
const lookup=Object.freeze({'hash/blocks.json':entry,'unused/other.json':Object.freeze({path:'unrelated'})});
const scoped=scopeAssetLookups(lookup,[asset,asset]);
assert.deepEqual(Object.keys(scoped),['hash/blocks.json']);assert.equal(scoped['hash/blocks.json'],entry);
assert.equal(Object.keys(lookup).length,2,'Never modify the full source dictionary while selecting references');
for(const patch of [{url:'/other/blocks.json'},{url:'/api/district-plans/missing/blocks.json'},{sha256:'wrong'},{bytes:101},{gzipBytes:51}]){
 assert.throws(()=>scopeAssetLookups(lookup,[{...asset,...patch}]));
}
""")
