import unittest

from sweepai.utils.function_call_utils import find_function_calls

test_code = """import React, { useState, useEffect } from 'react';

  useEffect(() => {
    // Initialize the Component here
    setPicker(new FilePicker(/* API parameters */));
  }, []);

  useEffect  (() => {
    // Initialize the Component here
    setPicker(new FilePicker(/* API parameters */));
  }, []);

  useEffect  (() => {
    // Initialize the Component here
    setPicker(new FilePicker(/* API parameters */));
  }, [];

  useEffect(
    a,
    b,
    c(d, e(), useEffect     ( ))
  )

export default Component;"""

extraction_term = "useEffect"


class TestFunctionCalls(unittest.TestCase):
    def test_find_function_call(self):
        self.assertEqual(
            find_function_calls(extraction_term, test_code),
            [(2, 6), (7, 11), (17, 22), (20, 21)],
        )
file_contents = """\
    call_this(
        x,
        y
    )
    dontcallthis
    call_this(inside())
"""

if __name__ == "__main__":
    keyword = "call_this"
    print(find_function_calls(keyword, file_contents))
