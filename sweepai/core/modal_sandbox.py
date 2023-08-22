import modal

stub = modal.Stub("sandbox")

god_image = (
    modal.Image.debian_slim()
    .apt_install(
        # Install npm
        "git",
        "npm",
        "nodejs",
        "curl",
    )
    .run_commands(
        # Install yarn
        "curl -sS https://dl.yarnpkg.com/debian/pubkey.gpg | apt-key add -",
        'echo "deb https://dl.yarnpkg.com/debian/ stable main" | tee /etc/apt/sources.list.d/yarn.list',
        "apt update",
        "apt install yarn",
    )
    .run_commands("curl -fsSL https://get.pnpm.io/install.sh | sh -")
    .pip_install("pre-commit")
)


def run_sandbox(
    install_script: str = "yarn",
    ci_script: str = "yarn lint && yarn tsc",
    timeout: int = 60,
):
    sb = stub.app.spawn_sandbox(
        "bash",
        "-c",
        f"cd repo && {install_script} && {ci_script}",
        image=god_image,
        mounts=[modal.Mount.from_local_dir("repo")],
        timeout=timeout,
    )

    sb.wait()

    if sb.returncode != 0:
        raise Exception(sb.stderror.read())
    else:
        return sb.stdout.read()
