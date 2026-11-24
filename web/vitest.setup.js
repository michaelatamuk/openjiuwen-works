import "@testing-library/jest-dom/vitest";

// jsdom does not implement the parts of <dialog> or SVG geometry the screens use.
if (typeof HTMLDialogElement !== "undefined") {
  HTMLDialogElement.prototype.showModal = function showModal() {
    this.setAttribute("open", "");
  };
  HTMLDialogElement.prototype.close = function close() {
    this.removeAttribute("open");
  };
}

if (typeof SVGElement !== "undefined") {
  SVGElement.prototype.getTotalLength = function getTotalLength() {
    return 100;
  };
  SVGElement.prototype.getPointAtLength = function getPointAtLength() {
    return { x: 0, y: 0 };
  };
}
