// import Diff from 'diff';
const Diff = require("diff");

const one = `a
b
c`;
const other = `a
c
d`;

it("creates diffs", () => {
  const patch = Diff.createPatch("filename", one, other);
  console.log(patch);
});
