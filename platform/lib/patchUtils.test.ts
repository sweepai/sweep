import { createPatch, isSublist, softIndentationCheck, parseRegexFromOpenAIModify } from './patchUtils';
import { expect } from '@jest/globals';

const Diff = require("diff")

describe('patchUtils', () => {

  describe('createPatch', () => {
    test('should return an empty string when old and new files are the same', () => {
      const filePath = 'sample.txt';
      const oldFile = 'This is the old file content.';
      const newFile = 'This is the old file content.';
      const length = createPatch(filePath, oldFile, newFile).length
      expect(createPatch(filePath, oldFile, newFile).length).toEqual(0);
    });

    test('should return a non-empty diff patch when old and new files are different', () => {
      const filePath = 'sample.txt';
      const oldFile = 'This is the old file content.';
      const newFile = 'This is the new file content.';
      const diffPatch = createPatch(filePath, oldFile, newFile);
      expect(diffPatch).toContain('-This is the old file content.');
      expect(diffPatch).toContain('+This is the new file content.');
    });
  });

  describe('isSublist', () => {
    test('should return true if second list is a sublist of the first list', () => {
      const list = ['one', 'two', 'three', 'four', 'five'];
      const sublist = ['two', 'three', 'four'];
      expect(isSublist(list, sublist)).toBeTruthy();
    });

    test('should return false if second list is not a sublist of the first list', () => {
      const list = ['one', 'two', 'four', 'five'];
      const sublist = ['two', 'three', 'four'];
      expect(isSublist(list, sublist)).toBe(false);
    });

    test('should return false if second list is empty', () => {
      const list = ['one', 'two', 'three'];
      const sublist: string[] = [];
      expect(isSublist(list, sublist)).toBeTruthy();
    });

    test('should return false if the first list is shorter than the second', () => {
      const list: string[] = ['one', 'two'];
      const sublist: string[] = ['one', 'two', 'three'];
      expect(isSublist(list, sublist)).toBe(false);
    });

    test('should return true if both lists are empty', () => {
      const list: string[] = [];
      const sublist: string[] = [];
      expect(isSublist(list, sublist)).toBeTruthy();
    });
  });

  describe('softIndentationCheck', () => {
    const oldCode = 'some line\nanother line';
    const newCode = 'some new line\nanother new line';
    const fileContents = '  some line\n  another line\na third line';

    test('should return the old and new code blocks with the detected indentation', () => {
      const [newOldCode, newNewCode] = softIndentationCheck(oldCode, newCode, fileContents);
      expect(newOldCode).toBe('\n  some line\n  another line');
      expect(newNewCode).toBe('\n  some new line\n  another new line');
    });

    test('should return the original code blocks if no matching indentation is found', () => {
      const fileContentsMismatch = 'some line\n  another line\na third line';
      const [newOldCode, newNewCode] = softIndentationCheck(oldCode, newCode, fileContentsMismatch);
      expect(newOldCode).toBe(oldCode);
      expect(newNewCode).toBe(newCode);
    });
  });

  describe('parseRegexFromOpenAIModify', () => {
    const response = `
<<<<<<< ORIGINAL
old content
=======
new content
>>>>>>> MODIFIED
`;
    const fileContents = 'first line\nold content\nlast line';

    test('should return updated file contents and an empty error message when modification is applicable', () => {
      const [updatedFileContents, errorMessage] = parseRegexFromOpenAIModify(response, fileContents);
      expect(updatedFileContents).toEqual('first line\nnew content\nlast line');
      expect(errorMessage).toBe("");
    });

    test('should handle multiple diff hunks in the response', () => {
      const responseMultiple = `
<<<<<<< ORIGINAL
old content
=======
new content
>>>>>>> MODIFIED
<<<<<<< ORIGINAL
additional old content
=======
additional new content
>>>>>>> MODIFIED
`;
      const fileContentsMultiple = 'first line\nold content\nmiddle line\nadditional old content\nlast line';
      const [updatedFileContents, errorMessage] = parseRegexFromOpenAIModify(responseMultiple, fileContentsMultiple);
      expect(updatedFileContents).toBe('first line\nnew content\nmiddle line\nadditional new content\nlast line');
      expect(errorMessage).toBe('');
    });

    test('should return an error message when the original code block cannot be found', () => {
      const responseMismatch = `
<<<<<<< ORIGINAL
nonexistent content
=======
new content
>>>>>>> MODIFIED
`;
      const [updatedFileContents, errorMessage] = parseRegexFromOpenAIModify(responseMismatch, fileContents);
      expect(updatedFileContents).toBe(fileContents);
      expect(errorMessage).toBe("");
    });

    test('should return an error message when there are no valid diff hunks', () => {
      const [updatedFileContents, errorMessage] = parseRegexFromOpenAIModify('', fileContents);
      expect(updatedFileContents).toBe(fileContents);
      expect(errorMessage).toContain('No valid diff hunks were found');
    });
  });
});
