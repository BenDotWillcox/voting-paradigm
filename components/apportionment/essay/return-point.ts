/**
 * Where the reader left the essay for the explorer, so the explorer's back
 * link can return them there rather than to the top. Kept in session
 * storage (this tab only) and forgotten after half an hour; without
 * storage, the back link simply opens the essay at the top.
 */

const KEY = "nebula-civitas.apportionment.return";
const FRESH_FOR = 30 * 60 * 1000;

interface ReturnPoint {
  /** The essay's scroll position when the reader left. */
  y: number;
  at: number;
  /** Set by the explorer's back link: the essay should restore `y` on arrival. */
  returning?: boolean;
}

/** Call as the reader follows a link from the essay to the explorer. */
export function saveReturnPoint(): void {
  write({ y: Math.round(window.scrollY), at: Date.now() });
}

/** The saved point, if there is a recent one. */
export function readReturnPoint(): ReturnPoint | null {
  try {
    const raw = window.sessionStorage.getItem(KEY);
    if (!raw) return null;
    const point = JSON.parse(raw) as ReturnPoint;
    return typeof point.y === "number" && Date.now() - point.at < FRESH_FOR ? point : null;
  } catch {
    return null;
  }
}

/** Call as the reader follows the explorer's back link. */
export function markReturning(): void {
  const point = readReturnPoint();
  if (point) write({ ...point, returning: true });
}

export function clearReturnPoint(): void {
  try {
    window.sessionStorage.removeItem(KEY);
  } catch {
    // Nothing stored.
  }
}

function write(point: ReturnPoint): void {
  try {
    window.sessionStorage.setItem(KEY, JSON.stringify(point));
  } catch {
    // No storage: the back link opens the essay at the top.
  }
}
