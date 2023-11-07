import pytest
from sweepai.utils import jedi_utils

def test_new_function_1():
    assert jedi_utils.new_function_1('input1') == 'expected_output1'
    assert jedi_utils.new_function_1('input2') == 'expected_output2'
    assert jedi_utils.new_function_1('edge_case_input') == 'edge_case_output'

def test_new_function_2():
    assert jedi_utils.new_function_2('input1') == 'expected_output1'
    assert jedi_utils.new_function_2('input2') == 'expected_output2'
    assert jedi_utils.new_function_2('edge_case_input') == 'edge_case_output'

def test_overall_functionality():
    assert jedi_utils.overall_function('input1') == 'expected_output1'
    assert jedi_utils.overall_function('input2') == 'expected_output2'
    assert jedi_utils.overall_function('edge_case_input') == 'edge_case_output'
