from src.utils.diff import format_contents, fuse_files

# Test real one line change
old_file_content = """print("Hello World")"""
new_file_content = """print("Hello Sweep")"""

# Test middle cutoff
old_file_content_a = """\
print("Hello World")
print("Hello World")
print("Hello World")
print("Hello World")
"""
new_file_content_a = """\
print("Hello World")
# Rest of code
print("Hello World")
"""

# Test end cutoff
old_file_content_b = """\
print("Hello World")
print("Hello World")
print("Hello World")
print("Hello World")
"""
new_file_content_b = """\
print("Hello World")
# Rest of code
"""

# Test a real difference
old_file_content_c = """\
print("Hello World")
print("Hello World")
print("Hello World")
print("Hello World")
"""
new_file_content_c = """\
print("Hello World")print("Hello Sweep")
print("Hello World")
"""

# Test beginning cutoff
old_file_content_d = """\
print("Hello World")
print("Hello World")
print("Hello World")
print("Hello World")
"""
new_file_content_d = """\
# Rest of code
print("Hello World")
"""

# Test two changes
old_file_content_e = """\
def match(line):
    lowercase = line.lower().strip()
    semantic_match = "rest" in lowercase or "remaining" in lowercase or "..." in lowercase
    is_comment = lowercase.startswith("#") or lowercase.startswith("//")
    return semantic_match and is_comment
"""
new_file_content_e = """\
def match(line):
    semantic_match = "rest" in lowercase or "remaining" in lowercase or "..." in lowercase
    return semantic_match and is_comment
"""

# Test two changes
old_file_content_f = """\
def match(line):
    lowercase = line.lower().strip()
    semantic_match = "rest" in lowercase or "remaining" in lowercase or "..." in lowercase
    is_comment = lowercase.startswith("#") or lowercase.startswith("//")
    return semantic_match and is_comment
"""
new_file_content_f = """\
def match(line):
    semantic_match = "rest" in lowercase or "remaining" in lowercase or "..." in lowercase
    # ...
    return semantic_match and is_comment
"""
result_f = """\
def match(line):
    semantic_match = "rest" in lowercase or "remaining" in lowercase or "..." in lowercase
    is_comment = lowercase.startswith("#") or lowercase.startswith("//")
    return semantic_match and is_comment
"""

old_file_content_g = """\
def match(line):
    lowercase = line.lower().strip()
    semantic_match = "rest" in lowercase or "remaining" in lowercase or "..." in lowercase
    is_comment = lowercase.startswith("#") or lowercase.startswith("//")
    return semantic_match and is_comment
"""
new_file_content_g = """\
def match(line):
    semantic_match = "rest" in lowercase or "remaining" in lowercase or "..." in lowercase
    is_comment = lowercase.startswith("#") or lowercase.startswith("//")
"""

old_file_content_h = """\
def match(line):
    lowercase = line.lower().strip()
    semantic_match = "rest" in lowercase or "remaining" in lowercase or "..." in lowercase
    is_comment = lowercase.startswith("#") or lowercase.startswith("//")
    return semantic_match and is_comment
"""
new_file_content_h = """\
    semantic_match = "rest" in lowercase or "remaining" in lowercase or "..." in lowercase
    is_comment = lowercase.startswith("#") or lowercase.startswith("//")
    return semantic_match and is_comment
"""

old_file_content_i = """\
def match(line):
    lowercase = line.lower().strip()
    semantic_match = "rest" in lowercase or "remaining" in lowercase or "..." in lowercase
    is_comment = lowercase.startswith("#") or lowercase.startswith("//")
    return semantic_match and is_comment
"""
new_file_content_i = """\
# ...
    semantic_match = "rest" in lowercase or "remaining" in lowercase or "..." in lowercase
    is_comment = lowercase.startswith("#") or lowercase.startswith("//")
    return semantic_match and is_comment
"""

old_file_content_j = """\
def match(line):
    lowercase = line.lower().strip()
    semantic_match = "rest" in lowercase or "remaining" in lowercase or "..." in lowercase
    is_comment = lowercase.startswith("#") or lowercase.startswith("//")
    return semantic_match and is_comment
"""
new_file_content_j = """\
def match(line):
    lowercase = line.lower().strip()
    semantic_match = "rest" in lowercase or "remaining" in lowercase or "..." in lowercase
    is_comment = lowercase.startswith("#") or lowercase.startswith("//")
# ...
"""
    
if __name__ == "__main__":
    # replaced_new_file_content = fuse_files(old_file_content, new_file_content)
    # assert replaced_new_file_content == new_file_content + "\n"
    # replaced_new_file_content = fuse_files(old_file_content_a, new_file_content_a)
    # assert replaced_new_file_content == old_file_content_a
    # replaced_new_file_content = fuse_files(old_file_content_b, new_file_content_b)
    # assert replaced_new_file_content == old_file_content_b
    # replaced_new_file_content = fuse_files(old_file_content_c, new_file_content_c)
    # assert replaced_new_file_content == new_file_content_c
    # replaced_new_file_content = fuse_files(old_file_content_d, new_file_content_d)
    # assert replaced_new_file_content == old_file_content_d
    # replaced_new_file_content = fuse_files(old_file_content_e, new_file_content_e)
    # assert replaced_new_file_content == new_file_content_e
    # replaced_new_file_content = fuse_files(old_file_content_f, new_file_content_f)
    # assert replaced_new_file_content == result_f
    # replaced_new_file_content = fuse_files(old_file_content_g, new_file_content_g)
    # assert replaced_new_file_content == new_file_content_g
    # replaced_new_file_content = fuse_files(old_file_content_h, new_file_content_h)
    # assert replaced_new_file_content == new_file_content_h
    # replaced_new_file_content = fuse_files(old_file_content_i, new_file_content_i)
    # assert replaced_new_file_content == old_file_content_i
    # replaced_new_file_content = fuse_files(old_file_content_j, new_file_content_j)
    # assert replaced_new_file_content == old_file_content_j

    test_file = """import torch
import torchvision
import torchvision.transforms as transforms

def load_data():
    # Load the training and testing data
    # This is just a placeholder and should be replaced with your actual data loading code
    pass

def init_model():
    # Initialize the model
    # This is just a placeholder and should be replaced with your actual model initialization code
    pass

def train_model():
    # Train the model
    # This is just a placeholder and should be replaced with your actual model training code
    pass

def main():
    # Load the data
    load_data()

    # Initialize the model
    init_model()

    # Train the model
    train_model()

if __name__ == "__main__":
    main()
```

    """
    print(format_contents(test_file))
    test_file = """```python
import torch
import torchvision
import torchvision.transforms as transforms

def load_data():
    # Load the training and testing data
    # This is just a placeholder and should be replaced with your actual data loading code
    pass

def init_model():
    # Initialize the model
    # This is just a placeholder and should be replaced with your actual model initialization code
    pass

def train_model():
    # Train the model
    # This is just a placeholder and should be replaced with your actual model training code
    pass

def main():
    # Load the data
    load_data()

    # Initialize the model
    init_model()

    # Train the model
    train_model()

if __name__ == "__main__":
    main()
```

    """
    print(format_contents(test_file))

    test_file = """```python
import torch
import torchvision
import torchvision.transforms as transforms

def load_data():
    # Load the training and testing data
    # This is just a placeholder and should be replaced with your actual data loading code
    pass

def init_model():
    # Initialize the model
    # This is just a placeholder and should be replaced with your actual model initialization code
    pass
    reg = ```abc```
def train_model():
    # Train the model
    # This is just a placeholder and should be replaced with your actual model training code
    pass

def main():
    # Load the data
    load_data()

    # Initialize the model
    init_model()

    # Train the model
    train_model()

if __name__ == "__main__":
    main()
```

    """
    print(format_contents(test_file))