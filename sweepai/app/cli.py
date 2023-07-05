try:   # Python 3.11+
    from typing import Self
except ImportError:  # Python 3.10 or lower
    from typing import TypeVar
    Self = TypeVar("Self", bound="object")

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
    demo.queue()
    demo.launch(enable_queue=True, inbrowser=True)
    
@typer_app.command()
def auth():
    """
    Reauthenticate with Github API for Sweep to work (for token expiry)
    """
    SweepChatConfig.load(recreate=True)
    print("Setup completed successfully!")

def app():
    # hacky solution based on https://github.com/tiangolo/typer/issues/18#issuecomment-1577788949
    import sys
    commands = {'start', 'auth'}
    sys.argv.append('start') if sys.argv[-1] not in commands else None
    typer_app()

if __name__ == "__main__":
    app()

