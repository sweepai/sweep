
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogHeader,
    DialogTitle,
    DialogTrigger,
  } from "@/components/ui/dialog"
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { Label } from "../ui/label";
  

const DashboardSettings = () => {
    return (
        <Dialog>
            <DialogTrigger>
                <Button className="mt-4 mr-4" variant="secondary">Settings</Button>
            </DialogTrigger>
            <DialogContent>
                <DialogHeader>
                <DialogTitle>Dialog title</DialogTitle>
                <DialogDescription>
                    Dialog description
                </DialogDescription>
                </DialogHeader>
                <div className="grid gap-4 py-4">
                    <div className="grid grid-cols-4 items-center gap-4">
                        <Label htmlFor="name" className="text-right">
                        Input 1
                        </Label>
                        <Input id="name" value="placeholder" className="col-span-3" />
                    </div>
                    <div className="grid grid-cols-4 items-center gap-4">
                        <Label htmlFor="username" className="text-right">
                        INput 2
                        </Label>
                        <Input id="username" value="second placeholder" className="col-span-3" />
                    </div>
                </div>
            </DialogContent>
        </Dialog>
    );
};

export default DashboardSettings;