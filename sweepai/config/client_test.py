import pytest

from sweepai.config.client import (get_blocked_dirs, get_branch_name_config,
                                   get_documentation_dict, get_rules)


def test_get_branch_name_config():
    assert get_branch_name_config(".github/sweep.yaml") == True
    assert get_branch_name_config("sweep.yaml") == False
    with pytest.raises(SystemExit):
        get_branch_name_config("nonexistent.yaml")

def test_get_documentation_dict():
    assert get_documentation_dict(".github/sweep.yaml") == {"docs": {}}
    assert get_documentation_dict("sweep.yaml") == {}
    with pytest.raises(SystemExit):
        get_documentation_dict("nonexistent.yaml")

def test_get_blocked_dirs():
    assert get_blocked_dirs(".github/sweep.yaml") == ["blocked_dirs"]
    assert get_blocked_dirs("sweep.yaml") == []
    with pytest.raises(SystemExit):
        get_blocked_dirs("nonexistent.yaml")

def test_get_rules():
    assert get_rules(".github/sweep.yaml") == ["rules"]
    assert get_rules("sweep.yaml") == []
    with pytest.raises(SystemExit):
        get_rules("nonexistent.yaml")
