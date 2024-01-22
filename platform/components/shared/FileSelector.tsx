import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import React from "react";

const FileSelector = () => {
    return (
        <Select>
            <SelectTrigger className="w-full">
            <SelectValue placeholder="File path" />
            </SelectTrigger>
            <SelectContent>
            <SelectItem value="light">Light</SelectItem>
            <SelectItem value="dark">Dark</SelectItem>
            <SelectItem value="system">System</SelectItem>
            </SelectContent>
        </Select>
    );
};

export default FileSelector;