from sandbox.modal_sandbox import stub, run_sandbox
from sandbox.sandbox import Sandbox

sandbox = Sandbox(
    install_command="pip install pylint",
    format_command="black",
    linter_command="echo {file}",
)

with stub.run():
    print(run_sandbox(sandbox, "tests/test.py"))
