import subprocess
import modal

stub = modal.Stub()

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
    .pip_install("pre-commit", "pytest")
)


@stub.local_entrypoint()
def main():
    repo_name = "sweep"
    subprocess.run(
        [
            "git",
            "clone",
            f"https://github.com/sweepai/{repo_name}",
            f"./test_repos/{repo_name}",
        ]
    )
    # install_script = "yarn"
    # ci_script = "yarn lint && yarn run tsc"
    install_script = "pre-commit install"
    ci_script = "pre-commit run --all-files"
    sb = stub.app.spawn_sandbox(
        "bash",
        "-c",
        f"cd {repo_name} && {install_script} && {ci_script}",
        image=god_image,
        mounts=[modal.Mount.from_local_dir(f"./test_repos/{repo_name}")],
        timeout=10,
    )

    sb.wait()

    print(sb.stdout.read())
    if sb.returncode != 0:
        print(f"Tests failed with code {sb.returncode}")
        print(sb.stderr.read())
    else:
        print("Tests passed!")
