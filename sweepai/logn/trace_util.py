import linecache
import sys


def trace_lines(frame, event, arg):
    if event == "line":
        filename = frame.f_code.co_filename
        if "" in filename:
            lineno = frame.f_lineno
            line = linecache.getline(filename, lineno)
            print(f"Executing {filename}:line {lineno}:{line.rstrip()}")
    return trace_lines


sys.settrace(trace_lines)
