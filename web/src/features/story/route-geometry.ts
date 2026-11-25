// Geometry for the fix route: a calm curve from intake to delivery.

export type Point = { x: number; y: number };

export const ROUTE_X0 = 160;
export const ROUTE_X1 = 1040;
// A calm route: a small rise, a dip, then a gradual climb that ends higher than it started.
export const ROUTE_KNOTS: readonly number[] = [270, 242, 275, 212, 166, 175];

export function routeYAt(index: number, count: number): number {
  if (count === ROUTE_KNOTS.length) return ROUTE_KNOTS[index];
  if (count <= 1) return ROUTE_KNOTS[0];
  const position = (index / (count - 1)) * (ROUTE_KNOTS.length - 1);
  const low = Math.floor(position);
  const high = Math.min(ROUTE_KNOTS.length - 1, low + 1);
  const fraction = position - low;
  return ROUTE_KNOTS[low] + (ROUTE_KNOTS[high] - ROUTE_KNOTS[low]) * fraction;
}

export function smoothPath(points: Point[]): string {
  if (!points.length) return "";
  if (points.length === 1) return `M ${points[0].x} ${points[0].y}`;
  const parts = [`M ${points[0].x} ${points[0].y}`];
  for (let index = 0; index < points.length - 1; index += 1) {
    const p0 = points[index - 1] || points[index];
    const p1 = points[index];
    const p2 = points[index + 1];
    const p3 = points[index + 2] || p2;
    const c1x = p1.x + (p2.x - p0.x) / 6;
    const c1y = p1.y + (p2.y - p0.y) / 6;
    const c2x = p2.x - (p3.x - p1.x) / 6;
    const c2y = p2.y - (p3.y - p1.y) / 6;
    parts.push(`C ${c1x.toFixed(2)} ${c1y.toFixed(2)} ${c2x.toFixed(2)} ${c2y.toFixed(2)} ${p2.x.toFixed(2)} ${p2.y.toFixed(2)}`);
  }
  return parts.join(" ");
}

export function lengthAtX(path: SVGPathElement, x: number): number {
  let low = 0;
  let high = path.getTotalLength();
  for (let step = 0; step < 24; step += 1) {
    const middle = (low + high) / 2;
    if (path.getPointAtLength(middle).x < x) low = middle;
    else high = middle;
  }
  return (low + high) / 2;
}
