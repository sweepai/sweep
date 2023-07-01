import typer
from rich import print

from src.app.config import SweepChatConfig

epilog = "Sweep is a AI junior developer. Docs at https://docs.sweep.dev, install at https://github.com/apps/sweep-ai and support at https://discord.gg/sweep-ai."

app = typer.Typer(epilog=epilog)

@app.command()
def start():
    """
    Launch Sweep Chat in the browser
    """
    SweepChatConfig.load()
    from src.app.ui import demo
    demo.queue()
    demo.launch(enable_queue=True, inbrowser=True)
    
@app.command()
def auth():
    """
    Reauthenticate with Github API for Sweep to work (for token expiry)
    """
    SweepChatConfig.load(recreate=True)
    print("[green]Setup completed successfully![/green]")


if __name__ == "__main__":
    app()
