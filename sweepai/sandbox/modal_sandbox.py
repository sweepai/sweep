from dataclasses import dataclass
import os
import re
import shutil
import subprocess
import git
from loguru import logger
import modal
from sweepai.core.chat import ChatGPT
from sweepai.core.entities import SweepContext

from sandbox.src.sandbox_utils import Sandbox
from sweepai.utils.diff import (
    format_contents,
    generate_new_file_from_patch,
    is_markdown,
)

stub = modal.Stub("api")

god_image = (
    modal.Image.debian_slim()
    .apt_install(
        # Basics
        "git",
        "curl",
    )
    .run_commands(
        # Install Node & npm
        "curl -fsSL https://deb.nodesource.com/setup_18.x | bash -",
        "apt install nodejs",
    )
    .run_commands("curl https://get.trunk.io -fsSL | bash -s -- -y")
    .run_commands(
        # Install yarn
        "curl -sS https://dl.yarnpkg.com/debian/pubkey.gpg | apt-key add -",
        (
            'echo "deb https://dl.yarnpkg.com/debian/ stable main" | tee'
            " /etc/apt/sources.list.d/yarn.list"
        ),
        "apt update",
        "apt install yarn",
    )
    .run_commands(
        # Install Trunk
        "curl https://get.trunk.io -fsSL | bash -s -- -y"
    )
    # .run_commands("curl -fsSL https://get.pnpm.io/install.sh | sh -")
    # .pip_install(["pre-commit", "pylint", "black"])
)


@dataclass
class SandboxError(Exception):
    stdout: str
    stderr: str


def run_sandbox(
    sandbox: Sandbox,
    file_path: str,
    bad_file_contents: str,
    timeout: int = 120,
    cpu: int = 4,
    memory: int = 8096,
):
    lint = "trunk init && trunk check {file}".format(file=file_path)
    print(lint)
    repo_dir = sandbox.repo.full_name.split("/")[-1]
    write_file_cmd = f"echo '{bad_file_contents}' > {file_path}"
    # cmd_string = f"cd repo && {write_file_cmd} && {cmd}"

    if not os.path.exists("repo"):
        subprocess.run(["git", "clone", sandbox.repo_url, "repo"])

    # cmd_string = f"cd {repo_dir} && pwd && ls && {write_file_cmd} && pwd && ls && cat {file_path} && {lint}"
    cmd_string = f"cd repo && cat {file_path} && trunk check {file_path}"
    sb = stub.app.spawn_sandbox(
        "bash",
        "-c",
        cmd_string,
        image=god_image.copy_mount(modal.Mount.from_local_dir("repo"))  # Copying repo
        .run_commands(
            f"cd repo && rm -rf .trunk && trunk init"
        )  # Re-initializing trunk
        .run_commands(f"cd repo && {write_file_cmd}"),  # Writing changed file
        timeout=timeout,
        cpu=cpu,
        memory=memory,
    )
    sb.wait()

    print("RETURN CODE: " + str(sb.returncode))
    stdout = sb.stdout.read()
    print("STDOUT:", sb.stdout.read())
    print("STDERR:", sb.stderr.read())

    err = sb.stderr.read()

    def clean_ansi_codes(raw_string: bytes) -> str:
        res = re.sub(r"\x1b\[.*?[@-~]", "", raw_string).strip()
        # delete all duplicate whitespaces
        res = re.sub(r"\s+", " ", res)
        return res

    stdout = "\n".join(stdout.split("\n")[-17:])  # truncate for trunk
    stdout = clean_ansi_codes(stdout)
    if sb.returncode != 0:  # If no error message, don't raise
        raise SandboxError(stdout, err)
    else:
        return stdout


def sandbox_code_repair_modify(
    proposed_file: str,
    filename: str,
    chunk_offset: int = 0,
    sandbox: Sandbox = None,
    chat_logger=None,
    sweep_context: SweepContext | None = {},
) -> tuple[str, str | None]:
    # Run formatter commands
    # formatted_file = run_format(sandbox, filename)
    # if formatted_file is not None:
    #     with open(f"repo/{filename}", "w") as f:
    #         f.write(formatted_file)
    #     proposed_file = formatted_file

    current_file = proposed_file
    final_sandbox_error = None

    print(chat_logger)

    def clean_logs(logs: str) -> str:
        return "\n".join(
            line for line in logs.split("\n") if not line.startswith("[warn]")
        ).strip()

    for i in range(5):
        logger.info(f"Checking with sandbox for the {i + 1}th time")
        try:
            logger.info(current_file)
            if sandbox:
                run_sandbox(sandbox, filename, current_file)
            logger.info("Sandbox linter success.")
            return current_file, None
        except SandboxError as sandbox_error:
            logger.warning("Sandbox linter failed.")
            logger.error(sandbox_error)

            final_sandbox_error = sandbox_error

            print(
                "Fixing linting errors...\n",
                sandbox_error.stdout + "\n\n" + sandbox_error.stderr,
            )
            code_repairer = ChatGPT.from_system_message_string(
                sandbox_code_repair_modify_system_prompt,
                chat_logger=chat_logger,
            )
            new_diffs = code_repairer.chat(
                sandbox_code_repair_modify_prompt.format(
                    filename=filename,
                    code=current_file,
                    stdout=clean_logs(sandbox_error.stdout),
                    stderr=clean_logs(sandbox_error.stderr),
                ),
                message_key=filename + "-validation",
            )
            print("Tried to fix them\n", new_diffs)

            next_file, _errors = generate_new_file_from_patch(
                new_diffs,
                current_file,
                chunk_offset=chunk_offset,
                sweep_context=sweep_context,
            )

            file_markdown = is_markdown(filename)
            next_file = format_contents(next_file, file_markdown)
            logger.info("Updated file based on logs")
            current_file = next_file
    return current_file, final_sandbox_error
