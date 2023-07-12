import typer

from sweepai.app.config import SweepChatConfig

epilog = "Sweep is a AI junior developer. Docs at https://docs.sweep.dev, install at https://github.com/apps/sweep-ai and support at https://discord.gg/sweep-ai."

typer_app = typer.Typer(epilog=epilog)


# @app.callback()
@typer_app.command()
def start():
    """
    Launch Sweep Chat in the browser
    """
    SweepChatConfig.load()
    from sweepai.app.ui import demo
    print("\033[93m⭐ Remember to star our repo at https://github.com/sweepai/sweep! \033[0m")
    demo.queue()
    demo.launch(inbrowser=True)


@typer_app.command()
def auth():
    """
    Reauthenticate with Github API for Sweep to work (for token expiry)
    """
    SweepChatConfig.load(recreate=True)
    print("Setup completed successfully!")
    print("\033[93m⭐ Remember to star our repo at https://github.com/sweepai/sweep! \033[0m")


def app():
    # hacky solution based on https://github.com/tiangolo/typer/issues/18#issuecomment-1577788949
    import sys
    commands = {'start', 'auth'}
    sys.argv.append('start') if sys.argv[-1] not in commands else None
    typer_app()


if __name__ == "__main__":
    app()
