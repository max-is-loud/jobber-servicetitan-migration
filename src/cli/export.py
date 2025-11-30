"""Export commands for TightBeam CLI."""

from pathlib import Path
from typing import Annotated, List, Optional

import typer
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, MofNCompleteColumn

from src.constants import ERROR_EMOJI, INFO_EMOJI, SUCCESS_EMOJI
from src.exporters import CsvExporter, XlsxExporter

from .services import ServiceFactory

# Get shared console instance
console = ServiceFactory.get_console()

# Create export subcommand group
export_app = typer.Typer(
    name="export",
    help="Export database to XLSX or CSV formats",
    add_completion=False,
)


@export_app.command("xlsx")
def export_xlsx(
    output: Annotated[
        Optional[Path],
        typer.Option(
            "--output",
            "-o",
            help="Output file path (default: tightbeam_export.xlsx)",
        ),
    ] = None,
    db: Annotated[
        Optional[Path],
        typer.Option(help="SQLite database path (default: tightbeam.sqlite)"),
    ] = None,
    tables: Annotated[
        Optional[str],
        typer.Option(
            help="Comma-separated list of tables to export (default: all tables)"
        ),
    ] = None,
    no_metadata: Annotated[
        bool,
        typer.Option(
            "--no-metadata", help="Skip metadata sheet with table relationships"
        ),
    ] = False,
) -> None:
    """
    Export database to XLSX (Excel) format.

    Creates a single Excel workbook with each table as a separate sheet.
    Includes a metadata sheet documenting table relationships.
    """
    # Set defaults
    db_path = db or Path("tightbeam.sqlite")
    output_path = output or Path("tightbeam_export.xlsx")

    # Validate database exists
    if not db_path.exists():
        console.print(f"\n[red]{ERROR_EMOJI} Database not found: {db_path}[/red]")
        console.print(f"[yellow]{INFO_EMOJI} Run migration first or specify database path with --db[/yellow]")
        raise typer.Exit(1)

    # Parse table list if provided
    table_list: Optional[List[str]] = None
    if tables:
        table_list = [t.strip() for t in tables.split(",")]

    try:
        console.print(f"\n[cyan]{INFO_EMOJI} Exporting database to XLSX...[/cyan]")
        console.print(f"Database: {db_path}")
        console.print(f"Output: {output_path}")

        if table_list:
            console.print(f"Tables: {', '.join(table_list)}")
        else:
            console.print("Tables: All")

        # Create exporter
        exporter = XlsxExporter(db_path, output_path)

        # Get table count for progress bar
        if table_list:
            total_tables = len(table_list)
        else:
            total_tables = len(exporter.get_table_list())

        # Export with progress bar
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("Exporting tables...", total=total_tables)

            def progress_callback(table_name: str, current: int, total: int) -> None:
                progress.update(task, description=f"Exporting {table_name}", completed=current)

            result_path = exporter.export(
                tables=table_list,
                include_metadata=not no_metadata,
                progress_callback=progress_callback,
            )

        console.print(
            f"\n[green]{SUCCESS_EMOJI} Export complete![/green]"
        )
        console.print(f"File: {result_path}")

        # Get table count
        exported_count = len(table_list) if table_list else len(exporter.get_table_list())
        console.print(f"Exported {exported_count} table(s)")

    except FileNotFoundError as e:
        console.print(f"\n[red]{ERROR_EMOJI} {e}[/red]")
        raise typer.Exit(1)
    except ValueError as e:
        console.print(f"\n[red]{ERROR_EMOJI} {e}[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"\n[red]{ERROR_EMOJI} Export failed: {e}[/red]")
        raise typer.Exit(1)


@export_app.command("csv")
def export_csv(
    output: Annotated[
        Optional[Path],
        typer.Option(
            "--output",
            "-o",
            help="Output directory path (default: tightbeam_export/)",
        ),
    ] = None,
    db: Annotated[
        Optional[Path],
        typer.Option(help="SQLite database path (default: tightbeam.sqlite)"),
    ] = None,
    tables: Annotated[
        Optional[str],
        typer.Option(
            help="Comma-separated list of tables to export (default: all tables)"
        ),
    ] = None,
    no_metadata: Annotated[
        bool,
        typer.Option(
            "--no-metadata", help="Skip README.txt with table relationships"
        ),
    ] = False,
) -> None:
    """
    Export database to CSV format.

    Creates a directory with separate CSV files for each table.
    Includes a README.txt documenting table relationships.
    """
    # Set defaults
    db_path = db or Path("tightbeam.sqlite")
    output_path = output or Path("tightbeam_export")

    # Validate database exists
    if not db_path.exists():
        console.print(f"\n[red]{ERROR_EMOJI} Database not found: {db_path}[/red]")
        console.print(f"[yellow]{INFO_EMOJI} Run migration first or specify database path with --db[/yellow]")
        raise typer.Exit(1)

    # Parse table list if provided
    table_list: Optional[List[str]] = None
    if tables:
        table_list = [t.strip() for t in tables.split(",")]

    try:
        console.print(f"\n[cyan]{INFO_EMOJI} Exporting database to CSV...[/cyan]")
        console.print(f"Database: {db_path}")
        console.print(f"Output: {output_path}")

        if table_list:
            console.print(f"Tables: {', '.join(table_list)}")
        else:
            console.print("Tables: All")

        # Create exporter
        exporter = CsvExporter(db_path, output_path)

        # Get table count for progress bar
        if table_list:
            total_tables = len(table_list)
        else:
            total_tables = len(exporter.get_table_list())

        # Export with progress bar
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("Exporting tables...", total=total_tables)

            def progress_callback(table_name: str, current: int, total: int) -> None:
                progress.update(task, description=f"Exporting {table_name}", completed=current)

            result_path = exporter.export(
                tables=table_list,
                include_metadata=not no_metadata,
                progress_callback=progress_callback,
            )

        console.print(
            f"\n[green]{SUCCESS_EMOJI} Export complete![/green]"
        )
        console.print(f"Directory: {result_path}")

        # Get table count
        exported_count = len(table_list) if table_list else len(exporter.get_table_list())
        console.print(f"Exported {exported_count} table(s)")

        # List files
        csv_files = sorted(result_path.glob("*.csv"))
        console.print(f"\nCreated {len(csv_files)} CSV file(s):")
        for csv_file in csv_files[:5]:  # Show first 5
            console.print(f"  • {csv_file.name}")
        if len(csv_files) > 5:
            console.print(f"  ... and {len(csv_files) - 5} more")

    except FileNotFoundError as e:
        console.print(f"\n[red]{ERROR_EMOJI} {e}[/red]")
        raise typer.Exit(1)
    except ValueError as e:
        console.print(f"\n[red]{ERROR_EMOJI} {e}[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"\n[red]{ERROR_EMOJI} Export failed: {e}[/red]")
        raise typer.Exit(1)


@export_app.command("all")
def export_all(
    output: Annotated[
        Optional[Path],
        typer.Option(
            "--output",
            "-o",
            help="Base output path (default: tightbeam_export)",
        ),
    ] = None,
    db: Annotated[
        Optional[Path],
        typer.Option(help="SQLite database path (default: tightbeam.sqlite)"),
    ] = None,
    tables: Annotated[
        Optional[str],
        typer.Option(
            help="Comma-separated list of tables to export (default: all tables)"
        ),
    ] = None,
    no_metadata: Annotated[
        bool,
        typer.Option(
            "--no-metadata", help="Skip metadata/README in exports"
        ),
    ] = False,
) -> None:
    """
    Export database to both XLSX and CSV formats.

    Creates both an Excel workbook and a directory of CSV files.
    """
    # Set defaults
    db_path = db or Path("tightbeam.sqlite")
    base_output = output or Path("tightbeam_export")

    # Validate database exists
    if not db_path.exists():
        console.print(f"\n[red]{ERROR_EMOJI} Database not found: {db_path}[/red]")
        console.print(f"[yellow]{INFO_EMOJI} Run migration first or specify database path with --db[/yellow]")
        raise typer.Exit(1)

    # Parse table list if provided
    table_list: Optional[List[str]] = None
    if tables:
        table_list = [t.strip() for t in tables.split(",")]

    try:
        console.print(f"\n[cyan]{INFO_EMOJI} Exporting database to XLSX and CSV...[/cyan]")
        console.print(f"Database: {db_path}")

        # Export XLSX
        console.print(f"\n[bold]1. Exporting to XLSX...[/bold]")
        xlsx_path = base_output.with_suffix(".xlsx")
        xlsx_exporter = XlsxExporter(db_path, xlsx_path)
        xlsx_result = xlsx_exporter.export(
            tables=table_list,
            include_metadata=not no_metadata,
        )
        console.print(f"   [green]{SUCCESS_EMOJI} XLSX: {xlsx_result}[/green]")

        # Export CSV
        console.print(f"\n[bold]2. Exporting to CSV...[/bold]")
        csv_path = base_output if not base_output.suffix else base_output.with_suffix("")
        csv_exporter = CsvExporter(db_path, csv_path)
        csv_result = csv_exporter.export(
            tables=table_list,
            include_metadata=not no_metadata,
        )
        console.print(f"   [green]{SUCCESS_EMOJI} CSV: {csv_result}[/green]")

        # Summary
        console.print(f"\n[green]{SUCCESS_EMOJI} All exports complete![/green]")
        exported_count = len(table_list) if table_list else len(xlsx_exporter.get_table_list())
        console.print(f"Exported {exported_count} table(s) in both formats")

    except FileNotFoundError as e:
        console.print(f"\n[red]{ERROR_EMOJI} {e}[/red]")
        raise typer.Exit(1)
    except ValueError as e:
        console.print(f"\n[red]{ERROR_EMOJI} {e}[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"\n[red]{ERROR_EMOJI} Export failed: {e}[/red]")
        raise typer.Exit(1)
