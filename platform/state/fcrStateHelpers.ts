import { FileChangeRequest } from "../lib/types";
import { FileChangeRequestsState } from "./fcrAtoms";
import { useRecoilState } from "recoil";

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

export const setIsLoading = (newIsLoading: boolean, fcr: FileChangeRequest) => {
  try {
    const [fileChangeRequests, setFileChangeRequests] = useRecoilState(FileChangeRequestsState);
    const fcrIndex = fileChangeRequests.findIndex((fileChangeRequest: FileChangeRequest) =>
      fcrEqual(fileChangeRequest, fcr)
    );
    undefinedCheck(fcrIndex);
    setFileChangeRequests((prev: FileChangeRequest[]) => {
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

export const setStatusForFCR = (newStatus: "queued" | "in-progress" | "done" | "error" | "idle", fcr: FileChangeRequest) => {
  try {
    const [fileChangeRequests, setFileChangeRequests] = useRecoilState(FileChangeRequestsState);
    const fcrIndex = fileChangeRequests.findIndex((fileChangeRequest: FileChangeRequest) =>
      fcrEqual(fileChangeRequest, fcr)
    );
    undefinedCheck(fcrIndex);
    setFileChangeRequests((prev: FileChangeRequest[]) => {
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

export const setStatusForAll = (newStatus: "queued" | "in-progress" | "done" | "error" | "idle") => {
  const [fileChangeRequests, setFileChangeRequests] = useRecoilState(FileChangeRequestsState);
  setFileChangeRequests((prev: FileChangeRequest[]) => {
    return prev.map((fileChangeRequest) => {
      return {
        ...fileChangeRequest,
        status: newStatus,
      };
    });
  });
}

export const setFileForFCR = (newFile: string, fcr: FileChangeRequest) => {
  try {
    const [fileChangeRequests, setFileChangeRequests] = useRecoilState(FileChangeRequestsState);
    const fcrIndex = fileChangeRequests.findIndex(
      (fileChangeRequest: FileChangeRequest) =>
        fcrEqual(fileChangeRequest, fcr)
    );
    undefinedCheck(fcrIndex);
    setFileChangeRequests((prev: FileChangeRequest[]) => {
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

export const setOldFileForFCR = (newOldFile: string, fcr: FileChangeRequest) => {
  try {
    const [fileChangeRequests, setFileChangeRequests] = useRecoilState(FileChangeRequestsState);
    const fcrIndex = fileChangeRequests.findIndex((fileChangeRequest: FileChangeRequest) =>
      fcrEqual(fileChangeRequest, fcr)
    );
    undefinedCheck(fcrIndex);
    setFileChangeRequests((prev: FileChangeRequest[]) => {
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

export const removeFileChangeRequest = (fcr: FileChangeRequest) => {
  try {
    const [fileChangeRequests, setFileChangeRequests] = useRecoilState(FileChangeRequestsState);
    const fcrIndex = fileChangeRequests.findIndex(
      (fileChangeRequest: FileChangeRequest) =>
        fcrEqual(fileChangeRequest, fcr)
    );
    undefinedCheck(fcrIndex);
    setFileChangeRequests((prev: FileChangeRequest[]) => {
      return [...prev.slice(0, fcrIndex), ...prev.slice(fcrIndex! + 1)];
    });
  } catch (error) {
    console.error("Error in removeFileChangeRequest: ", error);
  }
};

export const setHideMergeAll = (newHideMerge: boolean) => {
  const [fileChangeRequests, setFileChangeRequests] = useRecoilState(FileChangeRequestsState);
  setFileChangeRequests((newFileChangeRequests) => {
    return newFileChangeRequests.map((fileChangeRequest) => {
      return {
        ...fileChangeRequest,
        hideMerge: newHideMerge,
      };
    });
  });
};
