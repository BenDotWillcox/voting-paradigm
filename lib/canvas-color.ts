/**
 * Canvas can't read CSS custom properties, so figures drawn on <canvas>
 * resolve `--name` / `var(--name)` against an element's computed style.
 * Plain CSS colors pass through unchanged.
 */
export function resolveCssColor(element: Element, color: string): string {
  const match = /^(?:var\()?(--[\w-]+)\)?$/.exec(color.trim());
  if (!match) return color;
  return getComputedStyle(element).getPropertyValue(match[1]).trim() || "transparent";
}

/**
 * Re-run `onChange` when the theme switches (class strategy on <html>), since
 * resolved custom-property colors change with it. Returns a cleanup.
 */
export function observeThemeChanges(onChange: () => void): () => void {
  const observer = new MutationObserver(onChange);
  observer.observe(document.documentElement, {
    attributes: true,
    attributeFilter: ["class", "data-theme"],
  });
  return () => observer.disconnect();
}
