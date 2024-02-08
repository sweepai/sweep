import { FileChangeRequest, Snippet } from "../lib/types";

const fcrEqual = (a: FileChangeRequest, b: FileChangeRequest) => {
  return (
    a.snippet.file === b.snippet.file &&
    a.snippet.start === b.snippet.start &&
    a.snippet.end === b.snippet.end
  );
}

const undefinedCheck = (variable: any) => {
  if (typeof variable === "undefined") {
    throw new Error("Variable is undefined");
  }
};

export const setIsLoading = (newIsLoading: boolean, fcr: FileChangeRequest, fcrs: FileChangeRequest[], setFCRs: any) => {
  try {
    const fcrIndex = fcrs.findIndex((fileChangeRequest: FileChangeRequest) =>
      fcrEqual(fileChangeRequest, fcr)
    );
    undefinedCheck(fcrIndex);
    setFCRs((prev: FileChangeRequest[]) => {
      return [
        ...prev.slice(0, fcrIndex),
        {
          ...prev[fcrIndex],
          isLoading: newIsLoading,
        },
        ...prev.slice(fcrIndex + 1),
      ];
    });
  } catch (error) {
    console.error("Error in setIsLoading: ", error);
  }
};

export const setStatusForFCR = (newStatus: "queued" | "in-progress" | "done" | "error" | "idle", fcr: FileChangeRequest, fcrs: FileChangeRequest[], setFCRs: any) => {
  try {
    const fcrIndex = fcrs.findIndex((fileChangeRequest: FileChangeRequest) =>
      fcrEqual(fileChangeRequest, fcr)
    );
    undefinedCheck(fcrIndex);
    setFCRs((prev: FileChangeRequest[]) => {
      return [
        ...prev.slice(0, fcrIndex),
        {
          ...prev[fcrIndex],
          status: newStatus,
        },
        ...prev.slice(fcrIndex + 1),
      ];
    });
  } catch (error) {
    console.error("Error in setStatus: ", error);
  }
};

export const setStatusForAll = (newStatus: "queued" | "in-progress" | "done" | "error" | "idle", setFCRs: any) => {
  setFCRs((prev: FileChangeRequest[]) => {
    return prev.map((fileChangeRequest) => {
      return {
        ...fileChangeRequest,
        status: newStatus,
      };
    });
  });
}

export const setFileForFCR = (newFile: string, fcr: FileChangeRequest, fcrs: FileChangeRequest[], setFCRs: any) => {
  try {
    const fcrIndex = fcrs.findIndex(
      (fileChangeRequest: FileChangeRequest) =>
        fcrEqual(fileChangeRequest, fcr)
    );
    undefinedCheck(fcrIndex);
    setFCRs((prev: FileChangeRequest[]) => {
      return [
        ...prev.slice(0, fcrIndex),
        {
          ...prev[fcrIndex],
          newContents: newFile,
        },
        ...prev.slice(fcrIndex + 1),
      ];
    });
  } catch (error) {
    console.error("Error in setFileForFCR: ", error);
  }
};

export const setOldFileForFCR = (newOldFile: string, fcr: FileChangeRequest, fcrs: FileChangeRequest[], setFCRs: any) => {
  try {
    const fcrIndex = fcrs.findIndex((fileChangeRequest: FileChangeRequest) =>
      fcrEqual(fileChangeRequest, fcr)
    );
    undefinedCheck(fcrIndex);
    setFCRs((prev: FileChangeRequest[]) => {
      return [
        ...prev.slice(0, fcrIndex),
        {
          ...prev[fcrIndex],
          snippet: {
            ...prev[fcrIndex].snippet,
            entireFile: newOldFile,
          },
        },
        ...prev.slice(fcrIndex + 1),
      ];
    });
  } catch (error) {
    console.error("Error in setOldFileForFCR: ", error);
  }
};

export const removeFileChangeRequest = (fcr: FileChangeRequest, fcrs: FileChangeRequest[], setFCRs: any) => {
  try {
    const fcrIndex = fcrs.findIndex(
      (fileChangeRequest: FileChangeRequest) =>
        fcrEqual(fileChangeRequest, fcr)
    );
    undefinedCheck(fcrIndex);
    setFCRs((prev: FileChangeRequest[]) => {
      return [...prev.slice(0, fcrIndex), ...prev.slice(fcrIndex! + 1)];
    });
  } catch (error) {
    console.error("Error in removeFileChangeRequest: ", error);
  }
};

export const setHideMergeAll = (newHideMerge: boolean, setFCRs: any) => {
  setFCRs((prev: FileChangeRequest[]) => {
    return prev.map((fileChangeRequest) => {
      return {
        ...fileChangeRequest,
        hideMerge: newHideMerge,
      };
    });
  });
};

// updates readOnlySnippets for a certain fcr then updates entire fileChangeRequests array
export const setReadOnlySnippetForFCR = (
  fcr: FileChangeRequest,
  readOnlySnippet: Snippet,
  fcrs: FileChangeRequest[],
  setFCRs: any
) => {
  try {
    const fcrIndex = fcrs.findIndex(
      (fileChangeRequest: FileChangeRequest) =>
        fcrEqual(fileChangeRequest, fcr),
    );
    undefinedCheck(fcrIndex);
    setFCRs((prev: FileChangeRequest[]) => {
      const updatedFcr = {
        ...prev[fcrIndex],
        readOnlySnippets: {
          ...prev[fcrIndex].readOnlySnippets,
          [readOnlySnippet.file]: readOnlySnippet,
        },
      };
      return [...prev.slice(0, fcrIndex), 
        updatedFcr,
        ...prev.slice(fcrIndex + 1)];
    });
  } catch (error) {
    console.error("Error in setReadOnlySnippetForFCR: ", error);
  }
};

export const removeReadOnlySnippetForFCR = (
  fcr: FileChangeRequest,
  snippetFile: string,
  fcrs: FileChangeRequest[],
  setFCRs: any
) => {
  try {
    const fcrIndex = fcrs.findIndex(
      (fileChangeRequest: FileChangeRequest) =>
        fcrEqual(fileChangeRequest, fcr),
    );
    undefinedCheck(fcrIndex);
    setFCRs((prev: FileChangeRequest[]) => {
      const { [snippetFile]: _, ...restOfSnippets } = prev[fcrIndex].readOnlySnippets;
      const updatedFCR = {
        ...prev[fcrIndex],
        readOnlySnippets: restOfSnippets
      }
      return [...prev.slice(0, fcrIndex), updatedFCR, ...prev.slice(fcrIndex + 1)];
    });
  } catch (error) {
    console.error("Error in removeReadOnlySnippetForFCR: ", error);
  }
};

export const setDiffForFCR = (newDiff: string, fcr: FileChangeRequest, fcrs: FileChangeRequest[], setFCRs: any) => {
  try {
    const fcrIndex = fcrs.findIndex(
      (fileChangeRequest: FileChangeRequest) =>
        fcrEqual(fileChangeRequest, fcr),
    );
    undefinedCheck(fcrIndex);
    setFCRs((prev: FileChangeRequest[]) => {
      return [
        ...prev.slice(0, fcrIndex),
        {
          ...prev[fcrIndex],
          diff: newDiff
        },
        ...prev.slice(fcrIndex + 1),
      ];
    });
  } catch (error) {
    console.error("Error in setDiffForFCR: ", error);
  }
}