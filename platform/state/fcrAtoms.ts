import { FileChangeRequest } from "../lib/types";
import { atom } from "recoil";

export const FileChangeRequestsState = atom({
    key: "fileChangeRequests",
    default: [] as FileChangeRequest[],
})