import datetime
import json
import os
import threading


LOG_PATH = "logn_logs/logs"
META_PATH = "logn_logs/meta"
END_OF_LINE = "󰀀\n"


def get_task_key():
    return threading.current_thread()


# Task only stores the thread and key
_task_dictionary = {}


def _find_available_path(path, extension=".logn"):
    index = 0
    available_path = f"{path}{extension}"
    while os.path.exists(available_path):
        available_path = f"{path}{index}{extension}"
        index += 1
    print(f"Found {available_path}")
    return available_path


class _Task:
    def __init__(self, task_key, **metadata):
        self.task_key = task_key
        self.metadata = {**metadata}
        self.log_path, self.meta_path = self.create_files()

    @staticmethod
    def default():
        return _Task(task_key=threading.current_thread())

    def create_files(self):
        name = str(self.metadata.get("name", str(self.task_key.name.split(" ")[0])))

        # Write logging file
        log_path = _find_available_path(os.path.join(LOG_PATH, name))
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        with open(log_path, "w") as f:
            pass

        # Write metadata file
        meta_path = _find_available_path(
            os.path.join(META_PATH, name), extension=".json"
        )
        os.makedirs(os.path.dirname(meta_path), exist_ok=True)
        with open(meta_path, "w") as f:
            f.write(
                json.dumps(
                    {
                        "task_key": name,
                        "logs": log_path,
                        "datetime": str(datetime.datetime.now()),
                        "metadata": self.metadata,
                    }
                )
            )

        return log_path, meta_path

    def write_log(self, *args, **kwargs):
        if self.log_path is None:
            raise ValueError("Task has no log path")

        with open(self.log_path, "a") as f:
            log = " ".join([str(arg) for arg in args])
            f.write(f"{log}{END_OF_LINE}")


class _Logger:
    def __init__(self, printfn):
        self.printfn = printfn

    def __call__(self, *args, **kwargs):
        self.log(*args, **kwargs)

    def log(self, *args, **kwargs):
        self.printfn(*args, **kwargs)

        # write to file
        # Todo: Make task_key customizable
        task_key = get_task_key()

        if task_key in _task_dictionary:
            task = _task_dictionary[task_key]
        else:
            task = _Task.default()
            _task_dictionary[task_key] = task

        task.write_log(*args, **kwargs)

    @staticmethod
    def set_task(task_key=None, **metadata):
        global _task_dictionary
        if task_key is None:
            task_key = get_task_key()

        new_task = _Task(task_key=task_key, **metadata)
        _task_dictionary[task_key] = new_task
        new_task.write_metadata()


class _LogN(_Logger):
    # Logging for N tasks
    def __init__(self, printfn=print):
        super().__init__(printfn=printfn)

    def __getitem__(self, printfn):
        return _Logger(printfn=printfn)


logn_logger = _LogN()
