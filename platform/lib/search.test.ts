import { listFiles, searchFiles, splitIntoChunks } from "./search";
import { expect } from "@jest/globals";

describe("splitIntoChunks", () => {
  test("splits string into chunks of 40 lines with 30 lines overlapping", () => {
    const input = Array(100).fill("Line").join("\n");
    const result = splitIntoChunks(input);
    expect(result[0].content.split("\n")).toHaveLength(40);
    expect(result[1].content.split("\n")).toHaveLength(40);
    expect(result[1].content.split("\n")[0]).toEqual("Line");
  });

  test("handles empty string", () => {
    expect(splitIntoChunks("")).toEqual([]);
  });

  test("handles string with fewer than 40 lines", () => {
    const shortString = Array(20).fill("Line").join("\n");
    expect(splitIntoChunks(shortString)).toEqual([
      {
        file: "",
        start: 0,
        end: 20,
        entireFile: shortString,
        content: shortString,
      },
    ]);
  });
});

it("fetches all the files", async () => {
  const files = await listFiles("./");
  expect(files.length).toBeGreaterThan(0);
});

it("searched for something", async () => {
  const snippets = await searchFiles("./", "class", 100);
  for (const snippet of snippets) {
    console.log(snippet.file, snippet.content);
  }
  expect(snippets.length).toBeGreaterThan(0);
});
