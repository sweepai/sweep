import subprocess
import modal

stub = modal.Stub()


@stub.local_entrypoint()
def main():
    subprocess.run(
        [
            "git",
            "clone",
            "https://github.com/sweepai/landing-page",
            "./test_repos/landing-page",
        ]
    )
    sb = stub.app.spawn_sandbox(
        "bash",
        "-c",
        "cd landing-page && yarn && yarn lint && yarn run tsc",
        image=modal.Image.debian_slim()
        .apt_install("git", "npm", "nodejs", "curl")
        .run_commands(
            "curl -sS https://dl.yarnpkg.com/debian/pubkey.gpg | apt-key add -",
            'echo "deb https://dl.yarnpkg.com/debian/ stable main" | tee /etc/apt/sources.list.d/yarn.list',
            "apt update",
            "apt install yarn",
        ),
        mounts=[modal.Mount.from_local_dir("./test_repos/landing-page")],
        timeout=10,
    )

    sb.wait()

    print(sb.stdout.read())
    if sb.returncode != 0:
        print(f"Tests failed with code {sb.returncode}")
        print(sb.stderr.read())
    else:
        print("Tests passed!")
