import { listFiles, searchFiles, splitIntoChunks } from "./search";

describe("splitIntoChunks", () => {
  test("splits string into chunks of 40 lines with 30 lines overlapping", () => {
    const input = Array(100).fill("Line").join("\n");
    const result = splitIntoChunks(input);
    expect(result[0].content.split("\n").length).toBe(40);
    expect(result[1].content.split("\n").length).toBe(40);
    expect(result[1].content.split("\n")[0]).toBe("Line");
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
  // for (const file of files) {
  //     console.log(file.name, file.path, file.content?.length)
  // }
  expect(files.length > 0);
});

it("searched for something", async () => {
  const snippets = await searchFiles("./", "class", 100);
  for (const snippet of snippets) {
    console.log(snippet.file, snippet.content);
  }
  expect(snippets.length > 0);
});
