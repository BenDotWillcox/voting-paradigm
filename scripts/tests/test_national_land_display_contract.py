import json

import pytest

from test_block_demo_integration_contract import ROOT, run_node


LAYER_FIXTURE = r"""
const h=loadTs('lib/block-national-land-display.ts');
function rectangle(x0,y0,x1,y1) { return [[x0,y0],[x1,y0],[x1,y1],[x0,y1],[x0,y0]]; }
function layers() {
  const plan={id:'26-2',stateFips:'26',districtCount:2,districtPopulations:[10,20],residentPopulation:30};
  const outlines=collection([polygon(rectangle(0,0,5,10),'26'),polygon(rectangle(5,0,10,10),'26')]);
  outlines.metadata={purpose:'display-only',planId:plan.id};
  outlines.features.forEach((f,i)=>f.properties={state_fips:'26',plan_id:plan.id,district_id:i,population:plan.districtPopulations[i]});
  const coast=collection([{type:'Feature',properties:{state_fips:'26',plan_id:plan.id,kind:'state-and-water-shoreline'},
    geometry:{type:'MultiLineString',coordinates:[rectangle(0,0,10,10),rectangle(2,2,8,8),
      rectangle(3,3,4,4),rectangle(3.2,3.2,3.8,3.8),rectangle(20,0,21,1)]}}]);
  coast.metadata={purpose:'display-only',planId:plan.id};
  const dividers=collection([{type:'Feature',properties:{plan_id:plan.id,district_ids:[0,1],kind:'shared-district-divider'},
    geometry:{type:'MultiLineString',coordinates:[[[5,0],[5,2]],[[5,8],[5,10]]]}}]);
  dividers.metadata={purpose:'display-only',planId:plan.id};
  return {plan,outlines,coast,dividers};
}
function validate(f) {return h.validateMichiganNationalLayers(f.outlines,f.coast,f.dividers,f.plan);}
function rings(layer) { return layer.features.flatMap(f=>f.geometry.coordinates); }
"""


def test_only_michigan_geometry_changes_without_mutating_saved_national_plan(tmp_path):
    run_node(tmp_path, r"""
const h=loadTs('lib/block-national-land-display.ts');
const mi=polygon([[0,0],[2,0],[2,2],[0,2],[0,0]],'26');
mi.properties={state_fips:'26',district_id:0,population:123,plan_id:'26-1'};
const ak=polygon([[-190,50],[-130,50],[-130,70],[-190,70],[-190,50]],'02');
ak.properties={state_fips:'02',district_id:0,population:456,coordinate_frame:'alaska-continuous'};
const source=collection([mi,ak]), before=JSON.stringify(source);
const land=polygon([[0,0],[1,0],[1,1],[0,1],[0,0]],'26');
land.properties={district_id:0,population:123};
const result=h.michiganNationalLandView(source,collection([land]));
assert.equal(result.features.length,2);
assert.equal(result.features.find(f=>f.properties.state_fips==='02'),ak);
assert.equal(result.features.find(f=>f.properties.state_fips==='26').geometry,land.geometry);
assert.equal(result.features.find(f=>f.properties.state_fips==='26').properties,mi.properties);
assert.equal(JSON.stringify(source),before);
""")


def test_wrong_anchor_or_population_cannot_replace_saved_national_geometry(tmp_path):
    run_node(tmp_path, r"""
const h=loadTs('lib/block-national-land-display.ts');
const mi=polygon([[0,0],[2,0],[2,2],[0,0]],'26');
mi.properties={state_fips:'26',district_id:0,population:123};
const source=collection([mi]);
assert.throws(()=>h.michiganNationalLandView(source,collection([])),/anchor/);
const bad=structuredClone(mi);bad.properties.population=124;
assert.throws(()=>h.michiganNationalLandView(source,collection([bad])),/population/);
bad.properties.population=123;bad.properties.state_fips='02';
assert.throws(()=>h.michiganNationalLandView(source,collection([bad])),/identity/);
""")


def test_state_border_replacement_preserves_other_states_and_rejects_wrong_identity(tmp_path):
    run_node(tmp_path, r"""
const h=loadTs('lib/block-national-land-display.ts');
const mi=polygon([[0,0],[2,0],[2,2],[0,0]],'26');
const ak=polygon([[-190,50],[-130,50],[-130,70],[-190,50]],'02');
const small=polygon([[0,0],[1,0],[1,1],[0,0]],'26');
const result=h.michiganLandStateBorder(collection([mi,ak]),collection([small]));
assert.equal(result.features[1],ak);
assert.equal(result.features[0].geometry,small.geometry);
assert.throws(()=>h.michiganLandStateBorder(collection([mi,ak]),collection([ak])),/invalid/);
""")


def test_only_outer_shorelines_get_gold_inland_lakes_and_islands_stay_subdued(tmp_path):
    run_node(tmp_path, LAYER_FIXTURE + r"""
const f=layers(), before=JSON.stringify(f);
const result=validate(f), original=rings(f.coast);
// Mainland and offshore island are exterior. Lake, island-in-lake, and its
// nested lake all stay inland, even when the ring encloses land.
assert.deepEqual(rings(result.exteriorCoast),[original[0],original[4]]);
assert.deepEqual(rings(result.interiorWater),[original[1],original[2],original[3]]);
for(const ring of [...rings(result.exteriorCoast),...rings(result.interiorWater)]) assert.ok(original.includes(ring));
assert.equal(result.exteriorCoast.features[0].properties,f.coast.features[0].properties);
assert.equal(result.interiorWater.metadata,f.coast.metadata);
assert.equal(JSON.stringify(f),before);
// Shoreline classification must not depend on winding or feature ordering.
f.coast.features[0].geometry.coordinates=original.map(r=>[...r].reverse()).reverse();
const reversed=validate(f);
assert.equal(rings(reversed.exteriorCoast).length,2);
assert.equal(rings(reversed.interiorWater).length,3);
assert.deepEqual(rings(reversed.exteriorCoast).map(r=>r[0]),[[20,0],[0,0]]);
// A single LineString shoreline is accepted too.
f.coast.features[0].geometry={type:'LineString',coordinates:original[0]};
assert.equal(rings(validate(f).exteriorCoast).length,1);
assert.equal(validate(f).interiorWater.features.length,0);
""")


def test_matched_layers_preserve_dividers_and_saved_district_data(tmp_path):
    run_node(tmp_path, LAYER_FIXTURE + r"""
const f=layers(), before=JSON.stringify(f);
const national=collection([...f.outlines.features,polygon(rectangle(-190,50,-130,70),'02')]);
const nonMichigan=national.features[2], props=f.outlines.features.map(f=>f.properties);
validate(f);
const combined=h.michiganNationalLandView(national,f.outlines);
assert.equal(combined.features.find(f=>f.properties.state_fips==='02'),nonMichigan);
assert.deepEqual(combined.features.filter(f=>f.properties.state_fips==='26').map(f=>f.properties),props);
assert.equal(JSON.stringify(f),before);
assert.deepEqual(f.dividers.features[0].geometry.coordinates,[[[5,0],[5,2]],[[5,8],[5,10]]]);
""")


def test_stale_plan_malformed_geometry_and_invalid_divider_pairs_are_rejected(tmp_path):
    run_node(tmp_path, LAYER_FIXTURE + r"""
const mutations=[
 f=>f.plan.stateFips='02', f=>f.plan.residentPopulation++,
 f=>delete f.outlines.metadata, f=>f.coast.metadata.planId='26-3', f=>f.dividers.metadata.planId='26-3',
 f=>f.outlines.features[0].properties.population++, f=>f.outlines.features[0].properties.district_id=1,
 f=>f.outlines.features[0].properties.state_fips='02', f=>f.outlines.features[0].properties.plan_id='26-3',
 f=>f.outlines.features[0].geometry.coordinates[0][0][0]=Infinity,
 f=>f.coast.features[0].properties.state_fips='02', f=>f.coast.features[0].properties.plan_id='26-3',
 f=>f.coast.features[0].geometry.coordinates[0][0][0]=NaN,
 f=>f.coast.features[0].geometry.coordinates[0][0][0]='0',
 f=>f.coast.features[0].geometry.coordinates[0].pop(),
 f=>f.coast.features[0].geometry.coordinates[0]=[[0,0],[1,1],[2,2],[0,0]],
 f=>f.coast.features[0].geometry.coordinates.push(f.coast.features[0].geometry.coordinates[0]),
 f=>f.dividers.features[0].properties.plan_id='26-3',
 f=>f.dividers.features[0].properties.state_fips='06',
 f=>f.dividers.features[0].properties.district_ids=[0,2],
 f=>f.dividers.features[0].properties.district_ids=[0,0],
 f=>f.dividers.features[0].properties.district_ids=['0',1],
 f=>f.dividers.features[0].geometry.coordinates[0]=[[5,0]],
 f=>f.dividers.features[0].geometry.coordinates[0][1][1]=Infinity,
 f=>f.dividers.features.push({...f.dividers.features[0],properties:{...f.dividers.features[0].properties,district_ids:[1,0]}}),
];
for (const mutation of mutations) {
 const f=layers(); mutation(f);
 assert.throws(()=>validate(f),/selected plan|invalid geometry/,String(mutation));
}
""")


def test_all_four_saved_michigan_clean_layers_remain_valid_and_unchanged(tmp_path):
    report_path = ROOT / "data/districting-block-plans/michigan-explorer-geometry-report.json"
    if not report_path.exists():
        pytest.skip("Michigan display assets have not been prepared locally")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    required = [ROOT / report["assets"][asset["url"].removeprefix("/api/district-plans/")]["path"]
                for plan in report["plans"].values() for kind, asset in plan.items()
                if kind in {"overview", "coast", "dividers"}]
    if not all(asset.exists() for asset in required):
        pytest.skip("Michigan display gzip assets have not been prepared locally")
    run_node(tmp_path, LAYER_FIXTURE + r"""
const zlib=require('node:zlib'), crypto=require('node:crypto');
const report=JSON.parse(fs.readFileSync(path.join(ROOT,'data/districting-block-plans/michigan-explorer-geometry-report.json'),'utf8'));
assert.deepEqual(Object.keys(report.plans),['26-13','26-18','26-21','26-30']);
for (const [id,assets] of Object.entries(report.plans)) {
  const read=kind=>{
    const descriptor=report.assets[assets[kind].url.replace('/api/district-plans/','')];
    const raw=zlib.gunzipSync(fs.readFileSync(path.join(ROOT,descriptor.path)));
    assert.equal(crypto.createHash('sha256').update(raw).digest('hex'),assets[kind].sha256);
    return JSON.parse(raw);
  };
  const outlines=read('overview'), coast=read('coast'), dividers=read('dividers');
  const districtPopulations=outlines.features.map(f=>f.properties.population);
  const plan={id,stateFips:'26',districtCount:districtPopulations.length,districtPopulations,residentPopulation:10077331};
  const f={outlines,coast,dividers,plan}, before=JSON.stringify(f), all=rings(coast);
  const result=validate(f), exteriors=rings(result.exteriorCoast), interiors=rings(result.interiorWater);
  // Independent containment audit of these preserved assets: 378 outer rings,
  // 84 inland lake rings, and 43 islands inside those lakes at every anchor.
  assert.equal(exteriors.length,378);
  assert.equal(interiors.length,84+43);
  assert.equal(exteriors.length+interiors.length,all.length);
  for (const ring of [...exteriors,...interiors]) assert.ok(all.includes(ring));
  assert.equal(JSON.stringify(f),before);
  coast.features.forEach(f=>f.geometry.coordinates.forEach(r=>r.reverse()));
  const reversed=validate(f);
  assert.equal(rings(reversed.exteriorCoast).length,exteriors.length);
  assert.equal(rings(reversed.interiorWater).length,interiors.length);
  console.log(id,exteriors.length,'exterior rings',interiors.length,'interior water rings');
}
""")
