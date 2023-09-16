import datetime
import json
import os
import threading
import datetime
import inspect
import traceback

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
    current_frame = inspect.currentframe()
    calling_frame = next(
        frame
        for frame in inspect.stack()
        if frame.filename != current_frame.f_code.co_filename
    )
    function_name = calling_frame.function
    line_number = calling_frame.lineno

    # module_name = inspect.getmodule(calling_frame).__name__
    module_name = calling_frame.filename.split("/")[-1].replace(".py", "")

    log_string = f"{timestamp} | {level:<8} | {module_name}:{function_name}:{line_number} - {message}"
    return log_string


logging_parsers = {
    print: LogParser(
        level=0, parse_args=lambda *args, **kwargs: " ".join([str(arg) for arg in args])
    ),
}

try:
    from loguru import logger as loguru_logger

    logging_parsers[loguru_logger.info] = LogParser(
        level=1, parse_args=lambda *args, **kwargs: print2(args[0], level="INFO")
    )
    logging_parsers[loguru_logger.error] = LogParser(
        level=2, parse_args=lambda *args, **kwargs: print2(args[0], level="ERROR")
    )
    logging_parsers[loguru_logger.warning] = LogParser(
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
    def __init__(
        self, logn_task_key, logn_parent_task=None, metadata=None, create_file=True
    ):
        if logn_task_key is None:
            logn_task_key = get_task_key()

        self.task_key = logn_task_key
        self.metadata = metadata
        self.parent_task = logn_parent_task
        if self.metadata is None:
            self.metadata = {}
        if "name" not in self.metadata:
            self.metadata["name"] = str(self.task_key.name.split(" ")[0])
        self.create_file = create_file
        self.name, self.log_path, self.meta_path = self.create_files()
        self.state = "Created"
        self.children = []
        self.function_name = None
        self.write_metadata(state="Created")

    @staticmethod
    def create(metadata, create_file=True):
        return _Task(
            logn_task_key=threading.current_thread(),
            metadata=metadata,
            create_file=create_file,
        )

    def write_metadata(
        self,
        state: str | None = None,
        child_task: str | None = None,
        function_name: str | None = None,
    ):
        if state is not None:
            self.state = state
        if child_task is not None:
            self.children.append(child_task)
        if function_name is not None:
            self.function_name = function_name
        if not self.create_file:
            return

        # Todo: keep track of state, and allow metadata updates
        # state: str | None
        # self.state = state
        with open(self.meta_path, "w") as f:
            f.write(
                json.dumps(
                    {
                        "task_key": self.name,
                        "logs": self.log_path,
                        "datetime": str(datetime.datetime.now()),
                        "metadata": self.metadata if self.metadata is not None else {},
                        # Todo: Write parent task in here
                        "function_name": self.function_name,
                        "parent_task": self.parent_task.meta_path
                        if self.parent_task is not None
                        else None,
                        "children": self.children,
                        "state": state,
                    }
                )
            )

    def create_files(self):
        name = self.metadata["name"]

        # Write logging file
        log_path = os.path.join(LOG_PATH, name + ".txt")
        if self.create_file:
            log_path = _find_available_path(os.path.join(LOG_PATH, name))
            os.makedirs(os.path.dirname(log_path), exist_ok=True)
            with open(log_path, "w") as f:
                pass

        # Write metadata file
        meta_path = os.path.join(META_PATH, name + ".json")
        if self.create_file:
            meta_path = _find_available_path(
                os.path.join(META_PATH, name), extension=".json"
            )
            os.makedirs(os.path.dirname(meta_path), exist_ok=True)
            with open(meta_path, "w") as f:
                pass

        return name, log_path, meta_path

    def write_log(self, logn_level, *args, **kwargs):
        if not self.create_file:
            return

        if self.log_path is None:
            raise ValueError("Task has no log path")

        with open(self.log_path, "a") as f:
            log = " ".join([str(arg) for arg in args])
            f.write(f"{log}{END_OF_LINE.format(level=logn_level)}")

    @staticmethod
    def get_task(
        task_key=None, create_if_not_exist=True, metadata=None, create_file=True
    ):
        if task_key is None:
            task_key = get_task_key()

        task = None
        if _task_dictionary.get(task_key) is not None:
            task = _task_dictionary[task_key]
        elif create_if_not_exist:
            task = _Task.create(metadata=metadata, create_file=create_file)
            _task_dictionary[task_key] = task

        return task

    @staticmethod
    def set_metadata(metadata, create_file):
        task = _Task.get_task(metadata=metadata, create_file=create_file)
        if task is None:
            return
        task.create_file = create_file
        task.metadata = metadata
        task.write_metadata()

    @staticmethod
    def update_task(task_key=None, task=None):
        if task_key is None:
            task_key = get_task_key()

        _task_dictionary[task_key] = task

    @staticmethod
    def create_child_task(name: str):
        # Todo: make child task metadata
        parent_task = _Task.get_task(create_if_not_exist=False)
        if parent_task is None:
            task_key = get_task_key()
            child_task = _Task(
                logn_task_key=None,
                logn_parent_task=parent_task,
                metadata={"name": name},
            )
        else:
            task_key = parent_task.task_key
            child_task = _Task(
                logn_task_key=parent_task.task_key,
                logn_parent_task=parent_task,
                metadata={
                    **parent_task.metadata,
                    "name": parent_task.metadata["name"] + "_" + name,
                },
            )
        _task_dictionary[task_key] = child_task
        return task_key, parent_task, child_task


class _Logger:
    def __init__(self, printfn):
        # Check if printfn is a _Logger instance
        if isinstance(printfn, _Logger):
            print("Warning: self-reference logger can result in infinite loop")
            self.printfn = print
            return

        self.printfn = printfn

    def __call__(self, *args, **kwargs):
        try:
            self._log(*args, **kwargs)
        except Exception as e:
            print(traceback.format_exc())
            print("Failed to write log")

    def _log(self, *args, **kwargs):
        task = _Task.get_task()

        parser = None
        level = 0
        if self.printfn in logging_parsers:
            parser = logging_parsers[self.printfn]
            log = parser.parse(*args, **kwargs)

            print(log)
            task.write_log(parser.level, log)
        else:
            self.printfn(*args, **kwargs)
            task.write_log(0, *args, **kwargs)

    def init(self, metadata, create_file):
        _Task.set_metadata(metadata=metadata, create_file=create_file)


class _LogN(_Logger):
    # Logging for N tasks
    def __init__(self, printfn=print):
        super().__init__(printfn=printfn)

    def __getitem__(self, printfn):
        return _Logger(printfn=printfn)

    def print(self, *args, **kwargs):
        self[print](*args, **kwargs)

    def info(self, *args, **kwargs):
        self[loguru_logger.info](*args, **kwargs)

    def error(self, *args, **kwargs):
        self[loguru_logger.error](*args, **kwargs)

    def warning(self, *args, **kwargs):
        self[loguru_logger.warning](*args, **kwargs)

    def debug(self, *args, **kwargs):
        # Todo: add debug level
        self[loguru_logger.info](*args, **kwargs)

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
            key, parent_task, child_task = _Task.create_child_task(name=func.__name__)
            parent_task.write_metadata(
                child_task=child_task.meta_path, function_name=func.__name__
            )

            # Todo: add call to parent task

            try:
                result = func(*args, **kwargs)
            except Exception as e:
                child_task.write_metadata(state="Errored")
                _Task.update_task(task_key=key, task=parent_task)
                raise e

            child_task.write_metadata(state="Done")
            _Task.update_task(task_key=key, task=parent_task)

            # print(self.name, f"Logging after calling {func.__name__}")
            return result

        return wrapper


class LogN:
    @staticmethod
    def print():
        pass


# Export logger
logn_logger = _LogN()

# Export method attribute
LogTask = _LogTask

logger = _LogN()
