// import Diff from 'diff';
import { expect } from "@jest/globals";
const Diff = require("diff");

const one = `a
b
c`;
const other = `a
c
d`;

describe("Diff library test suite", () => {
  describe("createPatch function", () => {
    it("creates a patch for simple strings", () => {
      const patch = Diff.createPatch("filename", one, other);
      console.log(patch);
    });

    it("creates a patch for strings with no differences", () => {
      const sameText1 = `a
b
c`;
      const sameText2 = `a
b
c`;
      const patch = Diff.createPatch("filename", sameText1, sameText2);
      expect(patch).toBe(
        `Index: filename\n===================================================================\n--- filename\n+++ filename\n`,
      );
    });

    it("creates a patch for strings with different new lines", () => {
      const textWithNewLine = `a
b
c
`;
      const textWithoutNewLine = `a
b
c`;
      const patch = Diff.createPatch(
        "filename",
        textWithNewLine,
        textWithoutNewLine,
      );
      expect(patch).toContain("@@");
    });

    it("creates a patch for complex multiline strings", () => {
      const multilineString1 = `The quick brown fox
jumps over the lazy dog.`;
      const multilineString2 = `The swift brown fox
hops over the lazy dog.`;
      const patch = Diff.createPatch(
        "filename",
        multilineString1,
        multilineString2,
      );
      expect(patch).toContain("@@");
    });
  });
});
