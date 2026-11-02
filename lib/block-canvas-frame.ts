import { geoPath } from "d3-geo";
import { BLOCK_MAP_HEIGHT, BLOCK_MAP_WIDTH } from "@/lib/block-map-projection";
import type { BlockMapCollection, BlockMapProjection } from "@/lib/block-map-projection";

/** Draw unmasked features offscreen, then rasterize the complex land mask once.
 * Nothing from a masked frame is presented before that final mask is applied.
 */
export function createBlockCanvasFrame(canvas: HTMLCanvasElement, projection: BlockMapProjection, clip?: BlockMapCollection, atomic = false) {
  const visible = canvas.getContext("2d");
  if (!visible) return null;
  const offscreen = !!clip || atomic;
  const target = offscreen ? canvas.ownerDocument.createElement("canvas") : canvas;
  if (offscreen) { target.width = canvas.width; target.height = canvas.height; }
  const context = offscreen ? target.getContext("2d") : visible;
  if (!context) return null;
  context.setTransform(canvas.width / BLOCK_MAP_WIDTH, 0, 0, canvas.height / BLOCK_MAP_HEIGHT, 0, 0);
  context.clearRect(0, 0, BLOCK_MAP_WIDTH, BLOCK_MAP_HEIGHT);
  let cancelled = false, published = false;
  return {
    context,
    cancel: () => { cancelled = true; },
    publish: () => {
      if (cancelled || published || target.width !== canvas.width || target.height !== canvas.height) return false;
      published = true;
      if (clip) {
        context.save();
        context.globalAlpha = 1;
        context.globalCompositeOperation = "destination-in";
        context.fillStyle = "#fff";
        context.beginPath(); geoPath(projection, context)(clip); context.fill("evenodd");
        context.restore();
      }
      if (offscreen) {
        visible.save();
        visible.setTransform(1, 0, 0, 1, 0, 0);
        visible.globalAlpha = 1;
        visible.clearRect(0, 0, canvas.width, canvas.height);
        visible.drawImage(target, 0, 0);
        visible.restore();
      }
      return true;
    },
  };
}
