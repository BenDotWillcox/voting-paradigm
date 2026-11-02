"""Island-chain inspection focuses physical geography without editing sources."""
from test_block_demo_integration_contract import run_node


CAMERA_HOST = r"""
const h=loadTs('lib/state-map-interaction.ts');
const {geoPath}=rootRequire('d3-geo');
const drawing=geoPath();
const ring=(x,y,w,h)=>[[x,y],[x+w,y],[x+w,y+h],[x,y+h],[x,y]];
const feature=coordinates=>({type:'Feature',properties:{district_id:0,population:100},geometry:{type:'MultiPolygon',coordinates}});
function freeze(value){if(value&&typeof value==='object'){Object.freeze(value);Object.values(value).forEach(freeze);}return value;}
"""


def test_scattered_island_focus_uses_largest_area_and_never_mutates_saved_geometry(tmp_path):
    run_node(tmp_path, CAMERA_HOST + r"""
const source=feature([[ring(0,0,5,5)],[ring(400,250,30,25)],[ring(900,500,20,20)]]);
const before=JSON.stringify(source);freeze(source);
const whole=h.fitMapBounds(drawing.bounds(source));assert.ok(whole.k<7);
const focused=h.fitStateInspectionFeature(source,drawing,7);
const largest={...source,geometry:{type:'Polygon',coordinates:source.geometry.coordinates[1]}};
assert.deepEqual(focused,h.fitMapBounds(drawing.bounds(largest)));
assert.ok(focused.k>=7);
assert.ok(h.boundsIntersect(drawing.bounds(largest),h.viewportBounds(focused)));
assert.equal(JSON.stringify(source),before);
""")


def test_overview_and_single_polygon_keep_the_original_fit(tmp_path):
    run_node(tmp_path, CAMERA_HOST + r"""
const scattered=feature([[ring(0,0,5,5)],[ring(900,500,20,20)]]);
assert.deepEqual(h.fitStateInspectionFeature(scattered,drawing),h.fitMapBounds(drawing.bounds(scattered)));
const single={...scattered,geometry:{type:'Polygon',coordinates:[ring(0,0,900,500)]}};
assert.deepEqual(h.fitStateInspectionFeature(single,drawing,7),h.fitMapBounds(drawing.bounds(single)));
const nearby=feature([[ring(0,0,5,5)],[ring(20,20,10,10)]]);
assert.ok(h.fitMapBounds(drawing.bounds(nearby)).k>=7);
assert.deepEqual(h.fitStateInspectionFeature(nearby,drawing,7),h.fitMapBounds(drawing.bounds(nearby)));
""")


def test_alaska_continuous_frame_survives_physical_island_focus(tmp_path):
    run_node(tmp_path, CAMERA_HOST + r"""
const {makeStateBlockProjection}=loadTs('lib/block-map-projection.ts');
const source=feature([[ring(-187,52,.2,.2)],[ring(-170,54,1.5,1)],[ring(-132,55,.5,.5)]]);
const before=JSON.stringify(source);freeze(source);
const projection=makeStateBlockProjection({type:'FeatureCollection',features:[source]},'02');
const path=geoPath(projection), whole=h.fitMapBounds(path.bounds(source));assert.ok(whole.k<7);
const focused=h.fitStateInspectionFeature(source,path,7);
const largest={...source,geometry:{type:'Polygon',coordinates:source.geometry.coordinates[1]}};
assert.deepEqual(focused,h.fitMapBounds(path.bounds(largest)));
assert.ok(h.boundsIntersect(path.bounds(largest),h.viewportBounds(focused)));
assert.equal(JSON.stringify(source),before);
assert.equal(source.geometry.coordinates[0][0][0][0],-187);
""")
