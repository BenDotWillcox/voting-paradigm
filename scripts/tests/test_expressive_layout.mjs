// Exercise actual plot/strip effects with explicit commit, layout, and paint
// phases. Browser measurements and scroll positions are modeled; these checks
// catch a regression to passive effects without requiring a DOM dependency.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { createContext, runInContext } from "node:vm";
import ts from "typescript";

const source = readFileSync(new URL("../../components/expressive/electorate-results.tsx", import.meta.url), "utf8");
const { outputText } = ts.transpileModule(`${source}\nexport { Plot, VoterStrip };`, {
  compilerOptions: { target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX },
});
const nodes = (node) => node == null || typeof node !== "object" ? [] : Array.isArray(node)
  ? node.flatMap(nodes) : [node, ...nodes(node.props?.children)];
const sameDependencies = (first, second) => first && second && first.length === second.length && first.every((value, index) => Object.is(value, second[index]));

function createHost(component, props, width) {
  const hooks = [], layoutEffects = [], passiveEffects = [], observers = [], frames = new Map();
  const geometry = { width };
  let cursor = 0, dirty = true, tree, mounted = true, nextFrame = 1;
  const container = {};
  const svg = { getBoundingClientRect: () => ({ width: geometry.width }) };
  const strip = { scrollLeft: 0, get clientWidth() { return geometry.width; } };
  function effect(queue, create, dependencies) {
    const index = cursor++;
    const previous = hooks[index];
    if (previous && sameDependencies(previous.dependencies, dependencies)) return;
    const hook = hooks[index] = { dependencies, cleanup: previous?.cleanup };
    queue.push(() => { hook.cleanup?.(); hook.cleanup = create(); });
  }
  const react = {
    memo: (value) => value,
    useState(initial) {
      const index = cursor++;
      if (!(index in hooks)) hooks[index] = typeof initial === "function" ? initial() : initial;
      return [hooks[index], (value) => {
        assert.ok(mounted, "An unmounted component must not receive state updates");
        const next = typeof value === "function" ? value(hooks[index]) : value;
        if (!Object.is(hooks[index], next)) { hooks[index] = next; dirty = true; }
      }];
    },
    useRef(initial) { const index = cursor++; return hooks[index] ??= { current: initial }; },
    useId() { return `layout-test-${cursor++}`; },
    useMemo(create, dependencies) {
      const index = cursor++;
      if (!hooks[index] || !sameDependencies(hooks[index].dependencies, dependencies)) hooks[index] = { dependencies, value: create() };
      return hooks[index].value;
    },
    useCallback(callback, dependencies) { return react.useMemo(() => callback, dependencies); },
    useLayoutEffect(create, dependencies) { effect(layoutEffects, create, dependencies); },
    useEffect(create, dependencies) { effect(passiveEffects, create, dependencies); },
  };
  const jsx = (type, props, key) => ({ type, props: props ?? {}, key });
  const context = createContext({
    ResizeObserver: class {
      constructor(callback) { this.callback = callback; this.disconnected = false; observers.push(this); }
      observe(target) { this.target = target; }
      disconnect() { this.disconnected = true; }
    },
    requestAnimationFrame(callback) { const id = nextFrame++; frames.set(id, callback); return id; },
    cancelAnimationFrame(id) { frames.delete(id); },
  });
  const dependencies = {
    react,
    "react/jsx-runtime": { jsx, jsxs: jsx },
    "next/link": { default: "Link" },
    "lucide-react": {},
    "@/lib/expressive-scalar-graph": { scalarTransitionTicks: () => [] },
    "@/lib/use-scalar-viewport": {},
    "./electorate-results.module.css": { default: new Proxy({}, { get: (_, key) => key }) },
  };
  const exports = {};
  runInContext(`(function(exports, require) { ${outputText}\n })`, context)(exports, (name) => {
    assert.ok(name in dependencies, `Unexpected layout dependency: ${name}`);
    return dependencies[name];
  });
  function attachRefs() {
    let cardIndex = 0;
    for (const node of nodes(tree)) {
      const ref = node.props.ref;
      if (!ref) continue;
      let element;
      if (node.type === "svg") element = svg;
      else if (node.type === "button") {
        const index = cardIndex++;
        element = { offsetWidth: 96, get offsetLeft() { return (geometry.width - 96) / 2 + index * 104; } };
      } else element = node.props.role === "group" ? strip : container;
      if (typeof ref === "function") ref(element);
      else ref.current = element;
    }
  }
  function beforePaint(nextProps = props) {
    if (nextProps !== props) { props = nextProps; dirty = true; }
    for (let iteration = 0; iteration < 20; iteration++) {
      if (dirty) { cursor = 0; dirty = false; tree = exports[component](props); attachRefs(); }
      for (const run of layoutEffects.splice(0)) run();
      if (!dirty && layoutEffects.length === 0) return tree;
    }
    assert.fail("Layout did not settle before paint");
  }
  return {
    beforePaint, strip, observers, frames,
    find: (predicate) => nodes(tree).find(predicate),
    resize(nextWidth) {
      geometry.width = nextWidth;
      for (const observer of observers) if (!observer.disconnected) observer.callback([{ target: observer.target, contentRect: { width: nextWidth } }]);
      return beforePaint();
    },
    scroll() { nodes(tree).find((node) => node.props.role === "group").props.onScroll(); },
    frame() { const pending = [...frames.values()]; frames.clear(); for (const callback of pending) callback(); },
    unmount() { mounted = false; for (const hook of hooks) hook?.cleanup?.(); },
  };
}

const range = { minimum: 2.5, maximum: 6.5 };
const plotProps = { viewport: { view: range, from: range, target: range, progress: 1 }, label: "Selected voter", children: () => null };
const viewBox = (host) => host.find((node) => node.type === "svg").props.viewBox;
const voters = Array.from({ length: 100 }, (_, index) => ({
  id: `voter-${index}`, label: `Voter ${index}`, ballot: { ideal: index }, binary_vote: "no", path: "M 0 1", miniatureRange: range,
}));

test("the first painted mobile and desktop plots use their displayed content width", () => {
  for (const [width, height] of [[320, 277], [960, 317]]) {
    const host = createHost("Plot", plotProps, width);
    host.beforePaint();
    assert.equal(viewBox(host), `0 0 ${width} ${height}`, "The first paint must not use the 800px fallback ratio");
    assert.equal(host.observers.length, 1, "Responsive observation must be installed before paint");
    host.unmount();
    assert.ok(host.observers[0].disconnected);
  }
});

test("responsive updates and dataset remounts keep the plot geometry settled", () => {
  const previous = createHost("Plot", plotProps, 960);
  previous.beforePaint();
  previous.resize(360);
  assert.equal(viewBox(previous), "0 0 360 277");
  previous.unmount();
  const next = createHost("Plot", { ...plotProps, label: "New electorate" }, 360);
  next.beforePaint();
  assert.equal(viewBox(next), "0 0 360 277", "A keyed dataset remount must not shrink before it is remeasured");
  next.unmount();
});

test("the voter strip centers its selected voter before paint and keeps scroll selection consistent", () => {
  const selected = [];
  const props = { voters, selectedIndex: 73, onSelect: (index) => selected.push(index) };
  const host = createHost("VoterStrip", props, 320);
  host.beforePaint();
  assert.equal(host.strip.scrollLeft, 73 * 104, "The strip must not paint at its initial left edge");
  host.scroll();
  host.frame();
  assert.deepEqual(selected, [73], "The resulting scroll event must keep the intended voter selected");
  host.beforePaint({ ...props, selectedIndex: 18 });
  assert.equal(host.strip.scrollLeft, 18 * 104, "External voter selection must be centered before paint too");
  host.resize(640);
  assert.equal(host.strip.scrollLeft, 18 * 104);
  host.unmount();
});

test("a dataset remount centers the new You position and cancels the old scroll callback", () => {
  const oldSelections = [];
  const previous = createHost("VoterStrip", { voters, selectedIndex: 61, onSelect: (index) => oldSelections.push(index) }, 320);
  previous.beforePaint();
  previous.scroll();
  assert.equal(previous.frames.size, 1);
  previous.unmount();
  assert.equal(previous.frames.size, 0, "An old scroll callback must not survive the dataset change");
  assert.ok(previous.observers[0].disconnected);
  previous.frame();
  assert.deepEqual(oldSelections, []);

  const next = createHost("VoterStrip", { voters, selectedIndex: 9, onSelect() {} }, 320);
  next.beforePaint();
  assert.equal(next.strip.scrollLeft, 9 * 104, "The remounted strip must paint centered on the new dataset's selected voter");
  next.unmount();
});
