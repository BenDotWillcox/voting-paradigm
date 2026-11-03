"""Bound Next automatic discovery while retaining explicit runtime includes."""
import json

from test_block_demo_integration_contract import run_node


def test_content_hash_prefix_globs_preserve_every_asset_and_existing_metadata(tmp_path):
    run_node(tmp_path, r"""
const config=loadTs('next.config.ts').default;
const picomatch=rootRequire('next/dist/compiled/picomatch');
const includes=config.outputFileTracingIncludes['/api/district-plans/*'];
const prefixes='0123456789abcdef'.split('');
const assets=prefixes.map(prefix=>`./data/districting-block-plans/assets/${prefix}*.gz`);
const metadata=['./data/districting-block-plans/manifest.json','./data/districting-block-plans/server-index.json','./prompts/state-block-final-catalog.json'];
assert.deepEqual(includes.filter(value=>!value.includes('/assets/')),metadata);
assert.deepEqual(includes.filter(value=>value.includes('/assets/')),assets);
assert.deepEqual(config.outputFileTracingIncludes['/districts'],metadata);
assert.deepEqual(config.outputFileTracingExcludes['/*'],[
 './data/districting/**/*','./.cache/**/*','./public/data/districting/**/*',
 './public/data/district-plans/**/*.topo.json','./public/data/us-states.json']);
const matches=assets.map(pattern=>picomatch(pattern.slice(2),{dot:true}));
const original=picomatch('data/districting-block-plans/assets/*.gz',{dot:true});
for(const prefix of prefixes)for(const label of ['01-7-overview.geojson','02-shared-block-c001.geojson','48-88-assignments.json']){
 const name=`data/districting-block-plans/assets/${prefix}${'a'.repeat(63)}-${label}.gz`;
 assert.equal(original(name),true);
 assert.equal(matches.filter(match=>match(name)).length,1,'Each content-addressed asset belongs to exactly one bucket');
}
""")


def automatic_trace_probe(tmp_path):
    """Only source text and metadata are read; every glob/dependency is blocked."""
    return json.loads(run_node(tmp_path, r"""
const config=loadTs('next.config.ts').default;
const nextVersion=rootRequire('next/package.json').version;
const {TraceEntryPointsPlugin}=rootRequire('next/dist/build/webpack/plugins/next-trace-entrypoints-plugin');
const {nodeFileTrace}=rootRequire('next/dist/compiled/@vercel/nft');
const picomatch=rootRequire('next/dist/compiled/picomatch');
const ignores=['**/data/districting-block-plans/**','**/.cache','**/.cache/**'];
const plugin=new TraceEntryPointsPlugin({rootDir:ROOT,appDir:path.join(ROOT,'app'),pagesDir:undefined,
  compilerType:'server',appDirEnabled:true,traceIgnores:['**/existing-ignored/**']});
const untouched={apply(){}};
const webpack={plugins:[untouched,plugin]};
const includesBefore=JSON.stringify(config.outputFileTracingIncludes);
const routeExcludesBefore=JSON.stringify(config.outputFileTracingExcludes['/*']);
assert.equal(config.webpack(webpack,{dev:false,isServer:true,nextRuntime:'nodejs'}),webpack);
assert.equal(webpack.plugins[0],untouched);
assert.deepEqual(plugin.traceIgnores,['**/existing-ignored/**',...ignores]);
config.webpack(webpack,{dev:false,isServer:true,nextRuntime:'nodejs'});
assert.equal(plugin.traceIgnores.length,4,'The hook remains idempotent');
assert.equal(JSON.stringify(config.outputFileTracingIncludes),includesBefore);
assert.equal(JSON.stringify(config.outputFileTracingExcludes['/*']),routeExcludesBefore);
assert.deepEqual(config.outputFileTracingExcludes['next-server'],ignores);
const earlyMatcher=picomatch(plugin.traceIgnores,{contains:true,dot:true});
const sharedMatcher=picomatch(config.outputFileTracingExcludes['next-server'],{contains:true,dot:true});
assert.equal(picomatch('next-server')('next-server'),true,'Installed shared-ignore selector');
for(const route of ['/districts','/api/district-plans/[...asset]','/api/district-plans/example'])
 assert.equal(picomatch('next-server',{contains:true,dot:true})(route),false,'Special scope cannot remove final route includes');

async function observe(relative,source) {
 const entry=path.join(ROOT,relative),seen=[],metadataPaths=new Set();
 const result=await nodeFileTrace([entry],{base:ROOT,processCwd:ROOT,
  readFile:async file=>file.toLowerCase()===entry.toLowerCase()?source:'',
  readlink:async()=>null,
  stat:async file=>{metadataPaths.add(file);try{return await fs.promises.stat(file);}catch{return null;}},
  ignore:file=>{seen.push(file);return true;}, // No real glob or dependency traversal.
 });
 return {globPatterns:[...new Set(seen.filter(file=>file.includes('*')).map(file=>file.replaceAll('\\','/')))],
  metadataCalls:metadataPaths.size,warnings:[...result.warnings].map(error=>error.message)};
}
const source=fs.readFileSync(path.join(ROOT,'lib/load-block-plans.ts'),'utf8');
const transpiled=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
const observed=await observe('lib/load-block-plans.ts',transpiled);
assert.ok(observed.globPatterns.includes('**/*/.cache'),'Positive evidence of recursive cache-root discovery');
assert.ok(observed.globPatterns.includes('**/*/data/districting-block-plans/server-index.json'),'Positive evidence of recursive index discovery');
for(const glob of observed.globPatterns) {
 assert.equal(earlyMatcher(glob),true,glob);
 assert.equal(sharedMatcher(glob),true,glob);
 assert.equal(earlyMatcher(glob.replaceAll('/','\\')),true,'Windows path form');
}
const control=await observe('control.js','const fs=require("fs"),path=require("path");fs.readFileSync(path.join(process.cwd(),"data",process.env.PROBE_NAME));');
assert.deepEqual(control.globPatterns,['data/**/*'],'Positive control proves the probe can discover a real directory glob');
for(const file of ['app/districts/page.tsx','lib/load-block-plans.ts','prompts/state-block-final-catalog.json','public/data/methods/presets.json']) {
 assert.equal(earlyMatcher(file),false,file);assert.equal(sharedMatcher(file),false,file);
}

// Final Next processing adds includes, then removes only matching route scopes.
const includeMatchers=config.outputFileTracingIncludes['/api/district-plans/*'].map(p=>picomatch(p.slice(2),{dot:true}));
const finalExcludeMatchers=Object.entries(config.outputFileTracingExcludes)
 .filter(([scope])=>picomatch(scope,{contains:true,dot:true})('/api/district-plans/[...asset]'))
 .flatMap(([,patterns])=>patterns.map(p=>picomatch(p.replace(/^\.\//,''),{contains:true,dot:true})));
const runtimeFiles=['data/districting-block-plans/manifest.json','data/districting-block-plans/server-index.json','prompts/state-block-final-catalog.json',
 ...'0123456789abcdef'.split('').map(prefix=>`data/districting-block-plans/assets/${prefix}${'0'.repeat(63)}-sample.json.gz`)];
for(const file of runtimeFiles) {
 assert.equal(includeMatchers.some(match=>match(file)),true,file);
 assert.equal(finalExcludeMatchers.some(match=>match(file)),false,file);
}
console.log(JSON.stringify({status:'passed',nextVersion,observed,control,earlyAutomaticIgnores:plugin.traceIgnores,
 sharedAutomaticIgnores:config.outputFileTracingExcludes['next-server'],explicitIncludeCount:config.outputFileTracingIncludes['/api/district-plans/*'].length,
 verifiedRuntimeExampleCount:runtimeFiles.length,generatedDirectoriesScanned:0,
 sourceSha256:rootRequire('node:crypto').createHash('sha256').update(source).digest('hex'),
 externalCacheContract:'Historical assets/proofs retain their read-only BLOCK_PLAN_CACHE_ROOT mount; not all are contained in Next traces.'}));
"""))


def test_installed_nft_recursive_globs_are_blocked_in_both_stages_without_losing_runtime(tmp_path):
    evidence = automatic_trace_probe(tmp_path)
    assert evidence["status"] == "passed"
    assert evidence["nextVersion"] == "15.2.8"
    assert evidence["generatedDirectoriesScanned"] == 0


def test_automatic_trace_hook_only_changes_node_production_and_fails_loud_on_api_drift(tmp_path):
    run_node(tmp_path, r"""
const config=loadTs('next.config.ts').default;
for(const context of [{dev:true,isServer:true,nextRuntime:'nodejs'},{dev:false,isServer:false},
 {dev:false,isServer:true,nextRuntime:'edge'}]) {
 const webpack={plugins:[]};assert.equal(config.webpack(webpack,context),webpack);
}
const node={dev:false,isServer:true,nextRuntime:'nodejs'};
class TraceEntryPointsPlugin {
 constructor(compilerType='server',traceIgnores=[]) {Object.assign(this,{compilerType,traceIgnores});}
}
assert.throws(()=>config.webpack({plugins:[]},node),/tracing contract changed/);
assert.throws(()=>config.webpack({plugins:[new TraceEntryPointsPlugin(),new TraceEntryPointsPlugin()]},node),/tracing contract changed/);
assert.throws(()=>config.webpack({plugins:[new TraceEntryPointsPlugin('edge-server')]},node),/tracing contract changed/);
for(const invalid of [null,{},['valid',123]])
 assert.throws(()=>config.webpack({plugins:[new TraceEntryPointsPlugin('server',invalid)]},node),/traceIgnores contract changed/);
""")
