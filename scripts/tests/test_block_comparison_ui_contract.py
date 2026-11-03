"""Exercise the comparison client contracts with real TypeScript in Node."""
from test_block_demo_integration_contract import run_node


FIXTURE = r"""
const refs = loadTs('lib/block-comparison-layers.ts');
function tract(geoid='02001000100', density=10, land=1000000) {
 return {type:'Feature',properties:{geoid,population:10,landAreaM2:land,densityPerKm2:density},
 geometry:{type:'Polygon',coordinates:[[[-170,60],[-169,60],[-169,61],[-170,61],[-170,60]]]}};
}
function metadata(url='/reference/a') {
 return {asset:{url,bytes:100,gzipBytes:50,sha256:url},featureCount:1,label:'Reference',description:'',sourceUrl:'https://www.census.gov',vintage:'2020'};
}
"""


def test_density_distinguishes_zero_population_from_no_land_and_uses_common_bins(tmp_path):
    run_node(tmp_path, FIXTURE + r"""
assert.notEqual(refs.densityColor(0),refs.densityColor(null));
assert.equal(refs.densityColor(0),refs.DENSITY_BINS[0].color);
assert.equal(refs.densityColor(10),refs.DENSITY_BINS[1].color);
assert.equal(refs.densityColor(10.00001),refs.DENSITY_BINS[2].color);
assert.equal(refs.densityColor(1000),refs.DENSITY_BINS[3].color);
assert.equal(refs.densityColor(10000),refs.DENSITY_BINS[4].color);
assert.equal(refs.densityColor(10001),refs.DENSITY_BINS[5].color);
for(const value of [undefined,null,-1,NaN,Infinity,'10']) assert.equal(refs.densityColor(value),refs.DENSITY_NO_LAND_COLOR);
""")


def test_reference_validation_rejects_cross_state_duplicates_and_wrong_counts(tmp_path):
    run_node(tmp_path, FIXTURE + r"""
const good=collection([tract()]);
assert.equal(refs.validateComparisonCollection(good,'02','density',1),good);
assert.throws(()=>refs.validateComparisonCollection(good,'26','density',1),/geography/);
assert.throws(()=>refs.validateComparisonCollection(good,'02','density',2),/count/);
assert.throws(()=>refs.validateComparisonCollection(collection([tract(),tract()]),'02','density',2),/duplicate/);
const bad=collection([tract()]);bad.features[0].geometry.type='LineString';
assert.throws(()=>refs.validateComparisonCollection(bad,'02','density',1),/geography/);
""")


def test_zero_land_requires_null_density_and_invalid_numeric_values_are_rejected(tmp_path):
    run_node(tmp_path, FIXTURE + r"""
assert.doesNotThrow(()=>refs.validateComparisonCollection(collection([tract(undefined,null,0)]),'02','density',1));
for(const feature of [tract(undefined,0,0),tract(undefined,null,1),tract(undefined,-1,1),tract(undefined,NaN,1),tract(undefined,1,-1)]) {
 assert.throws(()=>refs.validateComparisonCollection(collection([feature]),'02','density',1),/density/);
}
const fraction=tract();fraction.properties.population=1.5;
assert.throws(()=>refs.validateComparisonCollection(collection([fraction]),'02','density',1),/density/);
""")


def test_bounded_cache_uses_lru_and_size_limit_without_evicting_on_oversize_insert(tmp_path):
    run_node(tmp_path, FIXTURE + r"""
const cache=new refs.ComparisonLayerCache(2,100), a=collection([tract()]),b=collection([tract()]),c=collection([tract()]);
cache.put('a',a,40);cache.put('b',b,40);assert.equal(cache.get('a'),a);
cache.put('c',c,40);assert.equal(cache.get('b'),null);assert.equal(cache.get('a'),a);
cache.put('huge',c,101);assert.equal(cache.get('huge'),null);assert.equal(cache.get('a'),a);
cache.put('c',c,90);assert.equal(cache.get('a'),null);assert.equal(cache.get('c'),c);
""")


def test_same_asset_is_reused_across_house_anchors_but_not_across_states(tmp_path):
    run_node(tmp_path, FIXTURE + r"""
let calls=0;
global.fetch=async()=>{calls++;return{ok:true,json:async()=>collection([tract()])}};
const layer=metadata(),signal=new AbortController().signal;
const first=await refs.loadComparisonLayer('02','density',layer,signal);
assert.equal(await refs.loadComparisonLayer('02','density',layer,signal),first);
assert.equal(calls,1);
await assert.rejects(refs.loadComparisonLayer('26','density',layer,signal),/geography/);
assert.equal(calls,2);
""")


def test_aborted_fetch_does_not_publish_or_poison_cache_and_retry_can_load(tmp_path):
    run_node(tmp_path, FIXTURE + r"""
const controller=new AbortController(),layer=metadata('/reference/abort');let calls=0;
global.fetch=async()=>{calls++;controller.abort();return{ok:true,json:async()=>collection([tract()])}};
await assert.rejects(refs.loadComparisonLayer('02','density',layer,controller.signal),{name:'AbortError'});
global.fetch=async()=>{calls++;return{ok:true,json:async()=>collection([tract()])}};
await refs.loadComparisonLayer('02','density',layer,new AbortController().signal);
assert.equal(calls,2);
await assert.rejects(refs.loadComparisonLayer('02','density',layer,controller.signal),{name:'AbortError'});
assert.equal(calls,2);
""")


def test_failed_or_malformed_reference_can_be_retried_without_cached_error(tmp_path):
    run_node(tmp_path, FIXTURE + r"""
let calls=0;const layer=metadata('/reference/retry'), signal=new AbortController().signal;
global.fetch=async()=>{calls++;return{ok:false,status:503}};
await assert.rejects(refs.loadComparisonLayer('02','density',layer,signal),/503/);
global.fetch=async()=>{calls++;return{ok:true,json:async()=>collection([])}};
await assert.rejects(refs.loadComparisonLayer('02','density',layer,signal),/count/);
global.fetch=async()=>{calls++;return{ok:true,json:async()=>collection([tract()])}};
await refs.loadComparisonLayer('02','density',layer,signal);
assert.equal(calls,3);
""")


def test_alaska_wrapped_reference_points_align_with_existing_continuous_frame(tmp_path):
    run_node(tmp_path, FIXTURE + r"""
const projection=loadTs('lib/block-map-projection.ts');
const p=projection.makeStateBlockProjection(collection([polygon([[-190,52],[-130,52],[-130,72],[-190,72],[-190,52]],'02')]),'02');
const a=p.projectPoint([178,53]),b=p.projectPoint([-182,53]);
close(a[0],b[0]);close(a[1],b[1]);
assert.ok(Number.isFinite(a[0])&&Number.isFinite(a[1]));
""")
