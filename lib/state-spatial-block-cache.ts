import type { StateSpatialBlockChunk } from "@/types/block-districting";
import type { StatePreparedCounty } from "@/lib/state-map-interaction";

export interface StateSpatialSnapshot {
  ready: boolean; data: StatePreparedCounty[]; renderData: StatePreparedCounty[]; loaded: number; total: number;
  error: string | null; pending: boolean; cacheSize: number; cachedBytes: number;
  inFlight: number; networkRequests: number; preparedChunks: number;
}

/** One inspection session owns requests and prepared chunks independently of
 * React viewport renders. The byte budget measures raw JSON, not heap usage. */
export class StateSpatialBlockCache {
  private readonly chunks: Map<string, StateSpatialBlockChunk>;
  private readonly load: (chunk: StateSpatialBlockChunk, signal: AbortSignal) => Promise<StatePreparedCounty>;
  private readonly onChange: () => void;
  private readonly budget: number;
  private readonly concurrency: number;
  private readonly cache = new Map<string, { data: StatePreparedCounty; touched: number; bytes: number }>();
  private readonly inFlight = new Map<string, AbortController>();
  private readonly errors = new Map<string, string>();
  private needed = new Set<string>();
  private disposed = false;
  private clock = 0;
  private revision = 0;
  private networkRequests = 0;
  private preparedChunks = 0;
  private memo: { key: string; revision: number; value: StateSpatialSnapshot } | null = null;
  private rendered: { key: string; ids: string[]; data: StatePreparedCounty[] } | null = null;

  constructor(options: {
    chunks: readonly StateSpatialBlockChunk[];
    load: (chunk: StateSpatialBlockChunk, signal: AbortSignal) => Promise<StatePreparedCounty>;
    onChange: () => void; retainBytes?: number; concurrency?: number;
  }) {
    this.chunks = new Map(options.chunks.map((chunk) => [chunk.chunkId, chunk]));
    if (this.chunks.size !== options.chunks.length) throw new Error("Spatial chunk identifiers must be unique.");
    this.load = options.load; this.onChange = options.onChange;
    this.budget = Math.max(0, options.retainBytes ?? 64 * 1024 * 1024);
    this.concurrency = Math.max(1, Math.floor(options.concurrency ?? 2));
  }

  private changed() { this.revision++; this.memo = null; if (!this.disposed) this.onChange(); }
  private bytes() { let total = 0; for (const entry of this.cache.values()) total += entry.bytes; return total; }
  private evict() {
    let bytes = this.bytes();
    const inactive = [...this.cache].filter(([id]) => !this.needed.has(id)).sort((a, b) => a[1].touched - b[1].touched);
    for (const [id, entry] of inactive) { if (bytes <= this.budget) break; this.cache.delete(id); bytes -= entry.bytes; }
  }

  setNeeded(ids: readonly string[]) {
    if (this.disposed) return;
    this.needed = new Set(ids);
    for (const id of this.needed) {
      if (!this.chunks.has(id)) throw new Error(`Unknown spatial chunk ${id}.`);
      const entry = this.cache.get(id); if (entry) entry.touched = ++this.clock;
    }
    for (const [id, controller] of this.inFlight) if (!this.needed.has(id)) { controller.abort(); this.inFlight.delete(id); }
    this.evict(); this.changed(); this.pump();
  }

  private pump() {
    if (this.disposed) return;
    for (const id of this.needed) {
      if (this.inFlight.size >= this.concurrency) break;
      if (this.cache.has(id) || this.inFlight.has(id) || this.errors.has(id)) continue;
      const chunk = this.chunks.get(id)!, controller = new AbortController();
      this.inFlight.set(id, controller); this.networkRequests += chunk.assignments ? 2 : 1;
      void this.load(chunk, controller.signal).then((data) => {
        if (this.disposed || controller.signal.aborted || this.inFlight.get(id) !== controller) return;
        this.preparedChunks++;
        this.cache.set(id, { data, bytes: chunk.asset.bytes + (chunk.assignments?.bytes ?? 0), touched: ++this.clock }); this.errors.delete(id);
      }).catch((cause: unknown) => {
        if (!this.disposed && !controller.signal.aborted && this.inFlight.get(id) === controller) this.errors.set(id, cause instanceof Error ? cause.message : "Unable to load spatial block detail.");
      }).finally(() => {
        if (this.disposed || this.inFlight.get(id) !== controller) return;
        this.inFlight.delete(id); this.evict(); this.changed(); this.pump();
      });
    }
    this.changed();
  }

  snapshot(ids: readonly string[]): StateSpatialSnapshot {
    const key = JSON.stringify(ids);
    if (this.memo?.key === key && this.memo.revision === this.revision) return this.memo.value;
    let error: string | null = null;
    const data: StatePreparedCounty[] = [], cachedIds: string[] = [];
    for (const id of ids) {
      if (!this.chunks.has(id)) error = `Unknown spatial chunk ${id}.`;
      error ??= this.errors.get(id) ?? null;
      const entry = this.cache.get(id); if (entry) { data.push(entry.data); cachedIds.push(id); }
    }
    const loaded = data.length;
    const duplicateError = () => {
      const seen = new Set<string>();
      for (const chunk of data) for (const feature of chunk.collection.features) {
        const geoid = String(feature.properties.geoid);
        if (seen.has(geoid)) return `Duplicate census block ${geoid} in spatial chunks.`;
        seen.add(geoid);
      }
      return null;
    };
    // Capture the cached overlap when a new viewport is requested, even before
    // React's setNeeded effect runs. Newly arriving chunks remain private until
    // the whole target validates, avoiding a redraw for every network response.
    if (!this.disposed && this.rendered?.key !== key) {
      const duplicate = duplicateError();
      error ??= duplicate;
      const old = this.rendered;
      const keep = old?.ids.flatMap((id, i) => ids.includes(id) ? [i] : []) ?? [];
      this.rendered = duplicate ? { key, ids: keep.map((i) => old!.ids[i]), data: keep.map((i) => old!.data[i]) }
        : { key, ids: cachedIds, data };
    }
    if (!error && loaded === ids.length) error = duplicateError();
    const ready = !this.disposed && !error && ids.length > 0 && loaded === ids.length;
    if (ready && (this.rendered?.data.length !== data.length || data.some((chunk, i) => chunk !== this.rendered?.data[i]))) {
      this.rendered = { key, ids: cachedIds, data };
    }
    const renderData = this.disposed ? [] : this.rendered?.data ?? [];
    const value = { ready, data: ready ? renderData : [], renderData, loaded, total: ids.length, error, pending: !this.disposed && !error && loaded < ids.length,
      cacheSize: this.cache.size, cachedBytes: this.bytes(), inFlight: this.inFlight.size, networkRequests: this.networkRequests, preparedChunks: this.preparedChunks };
    this.memo = { key, revision: this.revision, value }; return value;
  }

  retry() { if (!this.disposed) { for (const id of this.needed) this.errors.delete(id); this.changed(); this.pump(); } }
  dispose() {
    this.disposed = true;
    for (const controller of this.inFlight.values()) controller.abort();
    this.inFlight.clear(); this.cache.clear(); this.errors.clear(); this.needed.clear(); this.rendered = null; this.memo = null; this.revision++;
  }
}
