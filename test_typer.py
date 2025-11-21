import typer
from typing_extensions import Annotated

app = typer.Typer()


@app.callback()
def callback(
    verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False,
):
    pass


if __name__ == "__main__":
    app()
