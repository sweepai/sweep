import importlib.util

import jedi

source = """
import numpy as np
from numpy import array

def foo():
    x = 1
    print("")
    return np.array([1, 2, 3])

foo()
"""

script = jedi.Script(source)
# script = jedi.Script(path="sweepai/core/sweep_bot.py")
for name in script.get_names():
    if name.type in ("class", "def"):
        print(name.name)
    # print(name.type)

quit()

script = jedi.Script(
    source,
)

line = 5
# line = 6
# line = 8
column = 4
# column = 15
# column = 0

data = script.goto(line=line, column=column)
print(data)
quit()
inference = script.infer(line=line, column=column)
is_external_import = False
# If the module is native to python its not present in
# site-packages but rather in the python/ folder
# so we are gating against all things python for now
# if one of our clients has a problem we fix it later
for inference_bits in inference:
    try:
        inference_type = importlib.util.find_spec(inference_bits.module_name)
        if inference_type is not None:
            is_external_import = True
    except Exception:
        continue
    print(type(inference_bits))
    print(inference_bits.module_name)
if data[0].module_path is not None and (
    "site-packages" in str(data[0].module_path) or "python" in str(data[0].module_path)
):
    is_external_import = True

fully_qualified_type = (data[0].full_name,)
attribute_type = (data[0].type,)
is_external_library_import = (is_external_import,)
module_path = (str(data[0].module_path),)

# print(fully_qualified_type)
# print(attribute_type)
# print(is_external_library_import)
# print(module_path)
