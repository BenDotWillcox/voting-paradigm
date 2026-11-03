"""Generated geography is runtime data, not a Tailwind class source.

Use the installed compiler/scanner over a tiny disposable tree. This establishes
the scan exclusion without scanning the real half-million-file asset directory.
It does not claim a measured cause for the earlier production build's memory.
"""
import json

from test_block_demo_integration_contract import run_node


def test_installed_tailwind_excludes_only_generated_maps_and_keeps_ui_sources(tmp_path):
    fixture = tmp_path / "tiny-app"
    for name, content in {
        "app/page.tsx": 'export default () => <main className="flex" />;',
        "components/card.tsx": 'export default () => <aside className="grid" />;',
        "data/other-runtime-info.json": '{"className":"underline"}',
        "data/districting-block-plans/server-index.json": '{"className":"sticky"}',
        "data/districting-block-plans/publication-history/previous.json": '{"className":"fixed"}',
    }.items():
        target = fixture / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    run_node(tmp_path, "const fixture = " + json.dumps(str(fixture)) + ";\n" + r"""
const {compile}=rootRequire('@tailwindcss/node');
const {Scanner}=rootRequire('@tailwindcss/oxide');
const actual=fs.readFileSync(path.join(ROOT,'app/globals.css'),'utf8');
const exclusions=actual.match(/^@source not [^;]+;/gm) || [];
assert.deepEqual(exclusions,['@source not "../data/districting-block-plans";']);

async function scan(directive) {
 const compiler=await compile('@tailwind utilities;\n'+directive,
   {base:path.join(fixture,'app'),onDependency(){}});
 assert.equal(compiler.root,null,'Ordinary UI autodetection remains enabled');
 const scanner=new Scanner({sources:[{base:fixture,pattern:'**/*',negated:false},...compiler.sources]});
 const candidates=scanner.scan();
 return {compiler,scanner,candidates,css:compiler.build(candidates)};
}
const baseline=await scan('');
const patched=await scan(exclusions[0]);
for(const candidate of ['flex','grid','underline']) {
 assert.ok(patched.candidates.includes(candidate),`${candidate} remains discovered`);
 assert.ok(patched.css.includes('.'+candidate),`${candidate} remains compiled`);
}
for(const candidate of ['sticky','fixed']) {
 assert.ok(baseline.candidates.includes(candidate),'Unexcluded generated JSON is actually scanned');
 assert.ok(!patched.candidates.includes(candidate),`${candidate} is no longer scanned`);
 assert.ok(!patched.css.includes('.'+candidate),`${candidate} cannot generate CSS`);
}
const generated=path.resolve(fixture,'data/districting-block-plans');
const insideGenerated=file=>{
 const relative=path.relative(generated,path.resolve(file));
 return relative==='' || (!relative.startsWith('..'+path.sep) && relative!=='..' && !path.isAbsolute(relative));
};
assert.equal(baseline.scanner.files.filter(insideGenerated).length,2);
assert.equal(patched.scanner.files.filter(insideGenerated).length,0);
assert.ok(patched.scanner.files.some(file=>path.resolve(file)===path.join(fixture,'app/page.tsx')));
assert.ok(patched.scanner.files.some(file=>path.resolve(file)===path.join(fixture,'components/card.tsx')));
assert.equal(patched.compiler.sources.length,1);
assert.equal(patched.compiler.sources[0].negated,true);
assert.equal(path.resolve(patched.compiler.sources[0].base,patched.compiler.sources[0].pattern),generated);
""")
