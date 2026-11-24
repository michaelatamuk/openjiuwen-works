describe("frontend toolchain", () => {
  it("runs TypeScript tests under jsdom", () => {
    expect(typeof window).toBe("object");
  });
});
