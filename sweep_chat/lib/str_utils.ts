import { PullRequest } from "./types";

export const renderPRDiffs = (pr: PullRequest) => {
  return pr.file_diffs.map((diff, index) => (
    `@@ ${diff.filename} @@\n${diff.patch}`
  )).join("\n\n")
}

export const sliceLines = (content: string, start: number, end: number) => {
  return content.split("\n").slice(Math.max(start - 1, 0), end).join("\n");
}

export const getJSONPrefix = (buffer: string): [any[], number] => {
  let stack: string[] = [];
  const matchingBrackets: Record<string, string> = {
    '[': ']',
    '{': '}',
    '(': ')'
  };
  var currentIndex = 0;
  const results = [];
  let inString = false;
  let escapeNext = false;

  for (let i = 0; i < buffer.length; i++) {
    const char = buffer[i];

    if (escapeNext) {
      escapeNext = false;
      continue;
    }

    if (char === '\\') {
      escapeNext = true;
      continue;
    }

    if (char === '"') {
      inString = !inString;
    }

    if (!inString) {
      if (matchingBrackets[char]) {
        stack.push(char);
      } else if (matchingBrackets[stack[stack.length - 1]] === char) {
        stack.pop();
        if (stack.length === 0) {
          try {
            results.push(JSON.parse(buffer.slice(currentIndex, i + 1)));
            currentIndex = i + 1;
          } catch (e) {
            continue;
          }
        }
      }
    }
  }
  // if (currentIndex == 0) {
  //   console.log(buffer); // TODO: optimize later
  // }
  return [results, currentIndex];
}

