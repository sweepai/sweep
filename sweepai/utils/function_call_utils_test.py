import unittest

from sweepai.utils.function_call_utils import find_function_calls

file_contents = """
    call_this(
        x,
        y
    )
    dontcallthis
    call_this(inside())
"""

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

another_code_file = """
def download_models():
    from sentence_transformers import (  # pylint: disable=import-error
        SentenceTransformer,
    )
"""


class TestFunctionCalls(unittest.TestCase):
    def test_find_function_call(self):
        self.assertEqual(
            find_function_calls(extraction_term, test_code),
            [(2, 6), (7, 11), (17, 22), (20, 21)],
        )

    def test_find_function_call_file_contents(self):
        keyword = "call_this"
        self.assertEqual(
            find_function_calls(keyword, file_contents),
            [(1, 5), (6, 7)],
        )

    def test_find_function_call_another_code_file(self):
        keyword = "import"
        self.assertEqual(find_function_calls(keyword, another_code_file), [(2, 5)])


if __name__ == "__main__":
    unittest.main()
