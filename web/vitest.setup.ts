import "@testing-library/jest-dom/vitest";

// jsdom does not implement the parts of <dialog> or SVG geometry the screens use.
if (typeof HTMLDialogElement !== "undefined") {
  HTMLDialogElement.prototype.showModal = function showModal(this: HTMLDialogElement) {
    this.setAttribute("open", "");
  };
  HTMLDialogElement.prototype.close = function close(this: HTMLDialogElement) {
    this.removeAttribute("open");
  };
}

if (typeof SVGElement !== "undefined") {
  const geometry = SVGElement.prototype as unknown as {
    getTotalLength(): number;
    getPointAtLength(length: number): DOMPoint;
  };
  geometry.getTotalLength = function getTotalLength() {
    return 100;
  };
  geometry.getPointAtLength = function getPointAtLength() {
    return { x: 0, y: 0 } as DOMPoint;
  };
}
