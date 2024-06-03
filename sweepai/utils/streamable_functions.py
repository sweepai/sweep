from typing import Callable, Generator, ParamSpec, TypeVar, Generic

InputType = ParamSpec('InputType')
YieldType = TypeVar('YieldType')
ReturnType = TypeVar('ReturnType')

class StreamableFunction(Generic[InputType, ReturnType, YieldType]):
    """
    The purpose of streamable function is to allow for the streaming of a function's intermediate results.
    This is great because you can call the function normally, and it will return the function's return value,
    or the last yielded value, if the function has no return.
    But you can also call .stream() on the function, and it will return a generator that yields the intermediate results.
    """
    def __init__(self, stream: Callable[InputType, Generator[YieldType, None, ReturnType]]):
        self.stream: Callable[InputType, Generator[YieldType, None, ReturnType]] = stream
    
    def __call__(self, *args: InputType.args, **kwargs: InputType.kwargs) -> YieldType | ReturnType:
        """
        Returns the last yield or return result of the stream
        """
        result: YieldType | ReturnType = None
        try:
            generator = self.stream(*args, **kwargs)
            while True:
                result = next(generator)
        except StopIteration as e:
            return e.value if e.value is not None else result

def streamable(stream: Callable[InputType, Generator[YieldType, None, ReturnType]]) -> StreamableFunction[InputType, ReturnType, YieldType]:
    return StreamableFunction(stream)

if __name__ == "__main__":
    @streamable
    def stream():
        for i in range(10):
            yield i
        return -1
    
    result = stream()
    print(result)

    for message in stream.stream():
        print(message)
