import datetime
import inspect
import json
import logging
import os
import threading
import traceback

LOG_PATH = "logn_logs/logs"
META_PATH = "logn_logs/meta"
END_OF_LINE = "󰀀{level}󰀀\n"


# Add logtail support
try:
    from logtail import LogtailHandler

    from sweepai.config.server import LOGTAIL_SOURCE_KEY

    handler = LogtailHandler(source_token=LOGTAIL_SOURCE_KEY)

    def get_logtail_logger(logger_name):
        try:
            logger = logging.getLogger(logger_name)
            logger.setLevel(logging.INFO)
            logger.handlers = []
            logger.addHandler(handler)
            return logger
        except SystemExit:
            raise SystemExit
        except Exception:
            return None

except Exception as e:
    print("Failed to import logtail")
    print(e)

    def get_logtail_logger(logger_name):
        return None


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
        self,
        logn_task_key,
        logn_parent_task=None,
        metadata=None,
        create_file=True,
        function_name=None,
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
        self.function_name = function_name
        self.exception = None
        # self.write_metadata(state="Created")

        self.logtail_logger = get_logtail_logger(
            self.log_path.split("/")[-1].replace(".txt", "")
        )

    def get_logtail_metadata(self):
        return {
            "metadata": self.metadata,
            "function_name": self.function_name,
            "state": self.state,
            "children": self.children,
            "exception": self.exception,
        }

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
        exception: str | None = None,
    ):
        if state is not None:
            self.state = state
        if child_task is not None:
            self.children.append(child_task)
        if function_name is not None:
            self.function_name = function_name
        if exception is not None:
            self.exception = exception
        if not self.create_file:
            return

        # Todo: keep track of state, and allow metadata updates
        # state: str | None
        # self.state = state
        # with open(self.meta_path, "w") as f:
        #     f.write(
        #         json.dumps(
        #             {
        #                 "task_key": self.name,
        #                 "logs": self.log_path,
        #                 "datetime": str(datetime.datetime.now()),
        #                 "metadata": self.metadata if self.metadata is not None else {},
        #                 # Todo: Write parent task in here
        #                 "function_name": self.function_name,
        #                 "parent_task": self.parent_task.meta_path
        #                 if self.parent_task is not None
        #                 else None,
        #                 "children": self.children,
        #                 "exception": self.exception,
        #                 "state": state,
        #             }
        #         )
        #     )

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
        return
        # if not self.create_file:
        #     return

        # if self.log_path is None:
        #     raise ValueError("Task has no log path")

        # with open(self.log_path, "a") as f:
        #     log = " ".join([str(arg) for arg in args])
        #     f.write(f"{log}{END_OF_LINE.format(level=logn_level)}")

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
        # task.write_metadata()
        return task

    @staticmethod
    def update_task(task_key=None, task=None):
        if task_key is None:
            task_key = get_task_key()

        _task_dictionary[task_key] = task

    @staticmethod
    def create_child_task(name: str, function_name: str = None):
        # Todo: make child task metadata
        parent_task = _Task.get_task(create_if_not_exist=False)
        if parent_task is None:
            task_key = get_task_key()
            child_task = _Task(
                logn_task_key=None,
                logn_parent_task=parent_task,
                metadata={"name": name},
                function_name=function_name,
            )
        else:
            task_key = parent_task.task_key
            child_task = _Task(
                logn_task_key=parent_task.task_key,
                logn_parent_task=parent_task,
                metadata={
                    **parent_task.metadata,
                    "name": parent_task.metadata.get("name", "NO_NAME") + "_" + name,
                },
                function_name=function_name,
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
        except SystemExit:
            raise SystemExit
        except Exception:
            print(traceback.format_exc())
            print("Failed to write log")

    def _log(self, *args, **kwargs):
        task = _Task.get_task()

        if self.printfn in logging_parsers:
            parser = logging_parsers[self.printfn]
            log = parser.parse(*args, **kwargs)

            if task.logtail_logger is not None:
                try:
                    # switch case
                    match parser.level:
                        case 0:
                            task.logtail_logger.info(
                                log, extra=task.get_logtail_metadata()
                            )
                        case 1:
                            task.logtail_logger.info(
                                log, extra=task.get_logtail_metadata()
                            )
                        case 2:
                            task.logtail_logger.error(
                                log, extra=task.get_logtail_metadata()
                            )
                        case 3:
                            task.logtail_logger.warning(
                                log, extra=task.get_logtail_metadata()
                            )
                except SystemExit:
                    raise SystemExit
                except Exception:
                    pass

            print(log)
            task.write_log(parser.level, log)
        else:
            print(
                "Warning: no parser found for printfn:",
                self.printfn.__module__,
                self.printfn.__name__,
            )
            self.printfn(*args, **kwargs)
            task.write_log(0, *args, **kwargs)

    def init(self, metadata, create_file):
        task = _Task.set_metadata(metadata=metadata, create_file=create_file)
        return self


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
    def close(state="Done", exception=None):
        task = _Task.get_task(create_if_not_exist=False)
        if task is not None:
            task.write_metadata(state=state, exception=exception)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit will close the logger after leaving the with statement."""
        # Check if it errored
        if exc_type is not None:
            if type(exc_type) == SystemExit:
                self.close(state="Exited", exception=type(exc_type).__name__)
            else:
                self.close(state="Errored", exception=type(exc_type).__name__)
        else:
            self.close()


class LogN:
    @staticmethod
    def print():
        pass


logger = _LogN()
