def a_func():
    typer = None
    update_repo = lambda git, ref, repo_dir: None
    get_langserve_export = lambda pyproject_path: None
    package_dir = ""
    copy_repo = lambda git, ref, repo_dir: None
    installed_destination_paths = []
    installed_exports = []
    REPO_DIR = ""
    grouped = {}
    for (git, ref), group_deps in grouped.items():
        if len(group_deps) == 1:
            typer.echo(f"Adding {git}@{ref}...")
        else:
            typer.echo(f"Adding {len(group_deps)} templates from {git}@{ref}")
        source_repo_path = update_repo(git, ref, REPO_DIR)

        for dep in group_deps:
            source_path = (
                source_repo_path / dep["subdirectory"]
                if dep["subdirectory"]
                else source_repo_path
            )
            pyproject_path = source_path / "pyproject.toml"
            if not pyproject_path.exists():
                typer.echo(f"Could not find {pyproject_path}")
                continue
            langserve_export = get_langserve_export(pyproject_path)

            # default path to package_name
            inner_api_path = dep["api_path"] or langserve_export["package_name"]

            destination_path = package_dir / inner_api_path
            if destination_path.exists():
                typer.echo(
                    f"Folder {str(inner_api_path)} already exists. " "Skipping...",
                )
                continue
            copy_repo(source_path, destination_path)
            typer.echo(f" - Downloaded {dep['subdirectory']} to {inner_api_path}")
            installed_destination_paths.append(destination_path)
            installed_exports.append(langserve_export)
