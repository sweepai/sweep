import datetime
import json
import os
import threading
import datetime
import inspect

LOG_PATH = "logn_logs/logs"
META_PATH = "logn_logs/meta"
END_OF_LINE = "󰀀{level}󰀀\n"


class LogParser:
    def __init__(self, level: int, parse_args):
        self.level = level
        self.parse_args = parse_args

    def parse(self, *args, **kwargs):
        return self.parse_args(*args, **kwargs)


def print2(message, level="INFO"):
    if level is None:
        return message

    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    module_name = globals().get("__name__", "__main__")
    current_frame = inspect.currentframe()
    calling_frame = next(
        frame
        for frame in inspect.stack()
        if frame.filename != current_frame.f_code.co_filename
    )
    function_name = calling_frame.function
            # No code here
logging_parsers = {
    print: LogParser(
        level=0, parse_args=lambda *args, **kwargs: " ".join([str(arg) for arg in args])
    ),
}

try:
    from loguru import logger

    logging_parsers[logger.info] = LogParser(
        level=1, parse_args=lambda *args, **kwargs: print2(args[0], level="INFO")
    )
    logging_parsers[logger.error] = LogParser(
        level=2, parse_args=lambda *args, **kwargs: print2(args[0], level="ERROR")
    )
    logging_parsers[logger.warning] = LogParser(
        level=3, parse_args=lambda *args, **kwargs: print2(args[0], level="WARNING")
    )
except:
    print("Failed to import loguru")


def get_task_key():
    return threading.current_thread()


# Task only stores the thread and key
_task_dictionary = {}


def _find_available_path(path, extension=".txt"):
    index = 0
    available_path = f"{path}{extension}"
    while os.path.exists(available_path):
        available_path = f"{path}{index}{extension}"
        index += 1
    return available_path


class _Task:
    def __init__(self, logn_task_key, logn_parent_task=None, **metadata):
        if logn_task_key is None:
            logn_task_key = get_task_key()

        self.task_key = logn_task_key
        self.metadata = {**metadata}
        self.parent_task = logn_parent_task
        if "name" not in self.metadata:
            self.metadata["name"] = str(self.task_key.name.split(" ")[0])
        self.name, self.log_path, self.meta_path = self.create_files()
        self.write_metadata(state="Created")

    @staticmethod
    def default():
        return _Task(logn_task_key=threading.current_thread())

    def write_metadata(self, state: str):
        with open(self.meta_path, "w") as f:
            f.write(
                json.dumps(
                    {
                        "task_key": self.name,
                        "logs": self.log_path,
                        "datetime": str(datetime.datetime.now()),
                        "metadata": self.metadata,
                        # Todo: Write parent task in here
                        "parent_task": self.parent_task.meta_path
                        if self.parent_task is not None
                        else None,
                        "state": state,
                    }
                )
            )

    def create_files(self):
        name = self.metadata["name"]

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
            pass

        return name, log_path, meta_path

    def write_log(self, logn_level, *args, **kwargs):
        if self.log_path is None:
            raise ValueError("Task has no log path")

        with open(self.log_path, "a") as f:
            log = " ".join([str(arg) for arg in args])
            f.write(f"{log}{END_OF_LINE.format(level=logn_level)}")

    @staticmethod
    def get_task(task_key=None, create_if_not_exist=True):
        if task_key is None:
            task_key = get_task_key()

        task = None
        if _task_dictionary.get(task_key) is not None:
            task = _task_dictionary[task_key]
        elif create_if_not_exist:
            task = _Task.default()
            _task_dictionary[task_key] = task

        return task

    @staticmethod
    def update_task(task_key=None, task=None):
        if task_key is None:
            task_key = get_task_key()

        _task_dictionary[task_key] = task

    @staticmethod
    def create_child_task(name: str, **metadata):
        parent_task = _Task.get_task(create_if_not_exist=False)
        if parent_task is None:
            task_key = get_task_key()
            child_task = _Task(
                logn_task_key=None,
                logn_parent_task=parent_task,
                **{**metadata, "name": name},
            )
        else:
            task_key = parent_task.task_key
            child_task = _Task(
                logn_task_key=parent_task.task_key,
                logn_parent_task=parent_task,
                **{
                    **parent_task.metadata,
                    **metadata,
                    "name": parent_task.metadata["name"] + "_" + name,
                },
            )
        _task_dictionary[task_key] = child_task
        return task_key, parent_task, child_task


class _Logger:
    def __init__(self, printfn):
        self.printfn = printfn

    def __call__(self, *args, **kwargs):
        self.log(*args, **kwargs)

    def log(self, *args, **kwargs):
        self.printfn(*args, **kwargs)

        level = 0
        if self.printfn in logging_parsers:
            level = logging_parsers[self.printfn].level

        # write to file
        # Todo: Make task_key customizable
        task = _Task.get_task()
        task.write_log(level, *args, **kwargs)


class _LogN(_Logger):
    # Logging for N tasks
    def __init__(self, printfn=print):
        super().__init__(printfn=printfn)

    def __getitem__(self, printfn):
        return _Logger(printfn=printfn)

    @staticmethod
    def close():
        task = _Task.get_task(create_if_not_exist=False)
        if task is not None:
            task.write_metadata(state="Done")


class _LogTask:
    def __init__(self):
        pass

    def __call__(self, func):
        def wrapper(*args, **kwargs):
            # No code here

            # No code here
            try:
                result = func(*args, **kwargs)
            import traceback
            
            except Exception as e:
                child_task.write_metadata(state="Errored")
                _Task.update_task(task_key=key, task=parent_task)
                traceback.print_exc()

            child_task.write_metadata(state="Done")
            _Task.update_task(task_key=key, task=parent_task)

            # No code here
            return result

        return wrapper


# Export logger
logn_logger = _LogN()

# Export method attribute
LogTask = _LogTask
