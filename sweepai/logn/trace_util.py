import sys
import time
import inspect
from loguru import logger

def trace_function(func):
    def wrapper(*args, **kwargs):
        def trace_calls(frame, event, arg):
            if event != 'call':
                return None

            stack = inspect.stack()
            indent = ' ' * (len(stack) - 2)
            stack_info = ' -> '.join(frame.function for frame in stack[1:])

            start_time = time.time()

            def trace_returns(frame, event, arg):
                if event == 'return':
                    duration = time.time() - start_time
                    logger.info(f"{indent}Exiting function: {frame.f_code.co_name} (Stack: {stack_info}) (Duration: {duration:.4f} seconds)")

                return None

            logger.info(f"{indent}Entering function: {frame.f_code.co_name} (Stack: {stack_info})")

            return trace_returns

        sys.settrace(trace_calls)
        result = func(*args, **kwargs)
        sys.settrace(None)

        return result

    return wrapper

if __name__ == '__main__':
    @trace_function
    def main():
        result = foo(3, 4)
        print(f"Result: {result}")

    def foo(x, y):
        time.sleep(0.1)  # Simulating some work
        return bar(x) + bar(y)

    def bar(x):
        time.sleep(0.2)  # Simulating some work
        return x * 2

    main()
    print("Done tracing")
    # shouldn't print anything
    print(foo(5, 6))