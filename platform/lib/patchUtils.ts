const Diff = require("diff")

export const createPatch = (filePath: string, oldFile: string, newFile: string) => {
  if (oldFile === newFile) {
    return "";
  }
  return Diff.createPatch(filePath, oldFile, newFile);
};

export const isSublist = (lines: string[], subList: string[]): boolean => {
  for (let i = 0; i <= lines.length - subList.length; i++) {
    let match = true;
    for (let j = 0; j < subList.length; j++) {
      if (lines[i + j] !== subList[j]) {
        match = false;
        break;
      }
    }
    if (match) return true;
  }
  return false;
};

export const softIndentationCheck = (
  oldCode: string,
  newCode: string,
  fileContents: string,
): [string, string] => {
  // TODO: Unit test this
  let newOldCode = oldCode;
  let newNewCode = newCode;
  // expect there to be a newline at the beginning of oldCode
  // find correct indentaton - try up to 16 spaces (8 indentations worth)

  const lines = fileContents.split("\n")
  for (let i of [2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 22, 24]) {
    // split new code by \n and add the same indentation to each line, then rejoin with new lines
    newOldCode =
      "\n" +
      oldCode
        .split("\n")
        .map((line) => " ".repeat(i) + line)
        .join("\n");
    var newOldCodeLines = newOldCode.split("\n")
    if (newOldCodeLines[0].length === 0) {
      newOldCodeLines = newOldCodeLines.slice(1);
    }
    if (isSublist(lines, newOldCodeLines)) {
      newNewCode =
        "\n" +
        newCode
          .split("\n")
          .map((line) => " ".repeat(i) + line)
          .join("\n");
      return [newOldCode, newNewCode];
    }
  }
  return [oldCode, newCode];
};

export const parseRegexFromOpenAIModify = (
  response: string,
  fileContents: string,
): [string, string] => {
  let errorMessage = "";
  const diffRegexModify =
    /<<<<<<< ORIGINAL(\n+?)(?<oldCode>.*?)(\n*?)=======(\n+?)(?<newCode>.*?)(\n*?)($|>>>>>>> MODIFIED)/gs;
  const diffMatches = [...response.matchAll(diffRegexModify)];
  var currentFileContents = fileContents;
  var changesMade = false;
  for (const diffMatch of diffMatches) {
    changesMade = true;
    let oldCode = diffMatch.groups!.oldCode ?? "";
    let newCode = diffMatch.groups!.newCode ?? "";

    let didFind = false;
    if (oldCode.startsWith("\n")) {
      oldCode = oldCode.slice(1);
    }
    if (oldCode.trim().length === 0) {
      errorMessage += "ORIGINAL code block can not be empty.\n\n";
      continue;
    }
    if (!isSublist(currentFileContents.split("\n"), oldCode.split("\n"))) {
      const [newOldCode, newNewCode] = softIndentationCheck(
        oldCode,
        newCode,
        currentFileContents,
      );
      if (currentFileContents.includes(newOldCode)) {
        didFind = true;
      }
      currentFileContents = currentFileContents.replace(
        newOldCode,
        newNewCode,
      );
    } else {
      didFind = true;
      currentFileContents = currentFileContents.replace(oldCode, newCode);
    }
  }
  if (!changesMade) {
    errorMessage += "No valid diff hunks were found in the response.\n\n";
  }
  return [currentFileContents, errorMessage];
};
