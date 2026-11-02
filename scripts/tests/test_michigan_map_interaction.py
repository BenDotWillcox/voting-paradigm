"""Exercise the actual map transforms, block picking and population contracts."""
from test_block_demo_integration_contract import run_node


def test_inspection_zoom_limits_allow_geography_and_keep_blocks_in_detail_range(tmp_path):
    run_node(tmp_path, r"""
const h=loadTs('lib/michigan-map-interaction.ts');
for(const inspection of ['districts','counties']){
 assert.deepEqual(h.michiganZoomLimits(inspection),{min:1,max:256});
 assert.equal(h.michiganBlockDetailReady(inspection,256),false);
}
assert.deepEqual(h.michiganZoomLimits('blocks'),{min:6,max:256});
for(const zoom of [1,5.999,NaN,Infinity])assert.equal(h.michiganBlockDetailReady('blocks',zoom),false);
for(const zoom of [6,7,256])assert.equal(h.michiganBlockDetailReady('blocks',zoom),true);
const view={x:-800,y:-600,k:4},anchor=[500,310],limits=h.michiganZoomLimits('blocks');
const constrained=h.constrainViewport(view,limits,anchor);
assert.equal(constrained.k,6);
close((anchor[0]-view.x)/view.k,(anchor[0]-constrained.x)/constrained.k);
close((anchor[1]-view.y)/view.k,(anchor[1]-constrained.y)/constrained.k);
""")


def test_responsive_pointer_coordinates_and_zoom_preserve_the_cursor_anchor(tmp_path):
    run_node(tmp_path, r"""
const h=loadTs('lib/michigan-map-interaction.ts');
const view={x:-350,y:-90,k:4},rect={left:30,top:80,width:500,height:310};
const client=[230,180],screen=[400,200];
const before=h.mapPoint(client,rect,view);
assert.deepEqual(before,[187.5,72.5]);
const after=h.zoomAt(view,2,screen);
assert.deepEqual(h.mapPoint(client,rect,after),before);
assert.equal(after.k,8);
assert.equal(h.zoomAt(view,10000,screen).k,256);
assert.equal(h.zoomAt(view,0.0001,screen).k,1);
assert.equal(h.zoomAt(view,NaN,screen),view);
const fit=h.fitMapBounds([[100,50],[300,150]]);
assert.ok(fit.k>1);
close((100+300)/2*fit.k+fit.x,500);
close((50+150)/2*fit.k+fit.y,310);
assert.deepEqual(h.fitMapBounds([[Infinity,0],[1,1]]),h.INITIAL_VIEW);
const base={projectPoint:p=>[p[0]*2,-p[1]*3]};
const projected=h.transformedProjection(base,view);
assert.deepEqual(projected.projectPoint([10,20]),[-270,-330]);
""")


def test_block_picking_respects_holes_islands_and_grid_overflow(tmp_path):
    run_node(tmp_path, r"""
const h=loadTs('lib/michigan-map-interaction.ts');
const ring=(x,y,size)=>[[x,y],[x+size,y],[x+size,y+size],[x,y+size],[x,y]];
const geom={type:'MultiPolygon',coordinates:[[ring(0,0,10),ring(2,2,4)],[ring(20,20,2)]]};
const project=p=>[p[0]*3+10,p[1]*2-5];
assert.equal(h.pointInProjectedGeometry(geom,project([1,1]),project),true);
assert.equal(h.pointInProjectedGeometry(geom,project([3,3]),project),false,'Water hole is not a block hit');
assert.equal(h.pointInProjectedGeometry(geom,project([21,21]),project),true,'Multipart island remains selectable');
assert.equal(h.pointInProjectedGeometry(geom,project([15,15]),project),false);
const boxes=[[[0,0],[1,1]],[[7,7],[12,12]],[[-1000,-1000],[1000,1000]]];
const candidates=h.makeBoundsIndex(boxes);
assert.deepEqual(candidates([0.5,0.5]),[0,2]);
assert.deepEqual(candidates([9,9]),[1,2]);
assert.deepEqual(candidates([1001,1001]),[]);
assert.equal(h.boundsIntersect([[0,0],[10,10]],[[9,9],[11,11]]),true);
assert.equal(h.boundsIntersect([[0,0],[10,10]],[[11,11],[12,12]]),false);
""")


SUMMARY = r"""
const h=loadTs('lib/michigan-map-interaction.ts');
const plan={id:'26-2',stateFips:'26',coordinateFrame:'source',residentPopulation:100,blockCount:4,districtCount:2,districtPopulations:[60,40]};
const summary={planId:plan.id,stateFips:'26',residentPopulation:100,blockCount:4,
 counties:[{fips:'081',name:'Kent',population:100,blockCount:3,bbox:[-86,42,-85,43],districtShares:[
 {districtId:0,population:60,blockCount:1,percent:60},{districtId:1,population:40,blockCount:2,percent:40}]},
 {fips:'001',name:'Example',population:0,blockCount:1,bbox:[-84,44,-83,45],districtShares:[{districtId:0,population:0,blockCount:1,percent:0}]}],
 districts:[{districtId:0,population:60,blockCount:2,countyFips:['001','081']},{districtId:1,population:40,blockCount:2,countyFips:['081']}]};
"""


def test_population_shares_validate_residents_not_block_or_area_proportions(tmp_path):
    run_node(tmp_path, SUMMARY + r"""
assert.equal(h.validateMichiganSummary(summary,plan),summary);
for(const mutate of [
 s=>s.planId='26-3', s=>s.stateFips='02', s=>s.counties[0].districtShares[0].percent=100/3,
 s=>s.counties[0].districtShares[0].population=59, s=>s.counties[0].districtShares[1].districtId=0,
 s=>s.counties[0].bbox=[0,0,Infinity,1], s=>s.counties[0].bbox=[2,0,1,1],
 s=>s.counties[1].fips='081',s=>s.districts[0].countyFips=['081'],s=>s.districts[0].districtId=undefined,
 s=>s.districts[0].districtId=0.5,s=>s.districts[0].districtId=2,
]){const changed=structuredClone(summary);mutate(changed);assert.throws(()=>h.validateMichiganSummary(changed,plan));}
""")


def test_county_blocks_keep_zero_population_and_district_zero_and_reject_wrong_county(tmp_path):
    run_node(tmp_path, SUMMARY + r"""
const geometry={type:'Polygon',coordinates:[[[0,0],[1,0],[1,1],[0,1],[0,0]]]};
const doc=collection([{type:'Feature',geometry,properties:{geoid:'260810001001001',district_id:0,population:0}},
 {type:'Feature',geometry,properties:{geoid:'260810001001002',district_id:1,population:40}}]);
assert.equal(h.validateCountyBlocks(doc,plan,'081',40,2),doc);
assert.throws(()=>h.validateCountyBlocks(doc,plan,'001',40,2));
assert.throws(()=>h.validateCountyBlocks(doc,plan,'081',41,2));
assert.throws(()=>h.validateCountyBlocks(doc,plan,'081',40,3));
for(const mutate of [d=>d.features[0].properties.district_id=-1,d=>d.features[0].properties.district_id=2,
 d=>d.features[0].properties.geoid=d.features[1].properties.geoid,d=>d.features[0].properties.population=-1,
 d=>d.features[0].geometry=null]){const changed=structuredClone(doc);mutate(changed);assert.throws(()=>h.validateCountyBlocks(changed,plan,'081',40,2));}
""")
