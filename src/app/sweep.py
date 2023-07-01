import typer
from rich import print

from src.app.config import SweepChatConfig

app = typer.Typer()

@app.command()
def install():
    SweepChatConfig.load(recreate=True)
    print("[green]Setup completed successfully![/green]")

@app.command()
def start():
    SweepChatConfig.load()
    from src.app.ui import demo
    demo.queue()
    demo.launch(enable_queue=True, inbrowser=True)

if __name__ == "__main__":
    app()
