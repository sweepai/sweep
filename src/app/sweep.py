import typer
from rich import print

from src.app.config import Config

app = typer.Typer()

@app.command()
def start():
    from src.app.ui import demo
    demo.queue()
    demo.launch(enable_queue=True, inbrowser=True)

@app.command()
def setup(recreate: bool = False):
    if Config.is_initialized():
        print("[green]Setup already completed![/green]")
    else:
        Config.load(recreate=recreate)
        print("[green]Setup completed successfully![/green]")

if __name__ == "__main__":
    app()
