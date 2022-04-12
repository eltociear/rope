"""
Functions to find importable names.

Can extract names from source code of a python file, .so object, or builtin module.
"""

import ast
import inspect
import pathlib
from importlib import import_module
from typing import List, Tuple

from .defs import Name, PackageType, Source
from .utils import (
    get_modname_from_path,
    get_package_name_from_path,
    get_package_source,
    submodules,
)


def get_names(
    modpath: pathlib.Path,
    modname: str,
    package_name: str,
    package_source: Source,
    underlined: bool = False,
) -> List[Name]:
    """Get all names in the `modname` module, located at modpath.

    `modname` is the name of a module.
    """
    if modpath.is_dir():
        names: List[Name]
        if (modpath / "__init__.py").exists():
            names = get_names_from_file(
                modpath / "__init__.py",
                modname,
                package_name,
                package_source,
                only_all=True,
            )
            if len(names) > 0:
                return names
        names = []
        for file in modpath.glob("*.py"):
            names.extend(
                get_names_from_file(
                    file,
                    modname + f".{file.stem}",
                    package_name,
                    package_source,
                    underlined=underlined,
                )
            )
        return names
    if modpath.suffix == ".py":
        return get_names_from_file(
            modpath, modname, package_name, package_source, underlined=underlined
        )
    return []


def parse_all(node: ast.Assign, modname: str, package: str, package_source: Source):
    """Parse the node which contains the value __all__ and return its contents."""
    # I assume that the __all__ value isn't assigned via tuple
    all_results: List[Name] = []
    assert isinstance(node.value, ast.List)
    for item in node.value.elts:
        assert isinstance(item, ast.Constant)
        all_results.append(
            (
                str(item.value),
                modname,
                package,
                package_source.value,
            )
        )
    return all_results


def get_names_from_file(
    module: pathlib.Path,
    modname: str,
    package: str,
    package_source: Source,
    only_all: bool = False,
    underlined: bool = False,
) -> List[Name]:
    """
    Get all the names from a given file using ast.

    Parameters
    __________
    only_all: bool
        only use __all__ to determine the module's contents
    """
    with open(module, mode="rb") as file:
        try:
            root_node = ast.parse(file.read())
        except SyntaxError as error:
            print(error)
            return []
    results: List[Name] = []
    for node in ast.iter_child_nodes(root_node):
        node_names: List[str] = []
        if isinstance(node, ast.Assign):
            for target in node.targets:
                try:
                    assert isinstance(target, ast.Name)
                    if target.id == "__all__":
                        return parse_all(node, modname, package, package_source)
                    node_names.append(target.id)
                except (AttributeError, AssertionError):
                    # TODO handle tuple assignment
                    pass
        elif isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            node_names = [node.name]
        for node_name in node_names:
            if underlined or not node_name.startswith("_"):
                results.append((node_name, modname, package, package_source.value))
    if only_all:
        return []
    return results


def find_all_names_in_package(
    package_path: pathlib.Path,
    recursive=True,
    package_source: Source = None,
    underlined: bool = False,
) -> List[Name]:
    """
    Find all names in a package.

    Parameters
    ----------
    package_path : pathlib.Path
        path to the package
    recursive : bool
        scan submodules in addition to the root directory
    underlined : bool
        include underlined directories
    """
    package_tuple = get_package_name_from_path(package_path)
    if package_tuple is None:
        return []
    package_name, package_type = package_tuple
    if package_source is None:
        package_source = get_package_source(package_path)
    modules: List[Tuple[pathlib.Path, str]] = []
    if package_type is PackageType.SINGLE_FILE:
        modules.append((package_path, package_name))
    elif package_type is PackageType.COMPILED:
        return []
    elif recursive:
        for sub in submodules(package_path):
            modname = get_modname_from_path(sub, package_path)
            if underlined or modname.__contains__("_"):
                continue  # Exclude private items
            modules.append((sub, modname))
    else:
        modules.append((package_path, package_name))
    result: List[Name] = []
    for module in modules:
        result.extend(
            get_names(module[0], module[1], package_name, package_source, underlined)
        )
    return result


def get_names_from_compiled(
    package: str,
    source: Source,
    underlined: bool = False,
) -> List[Name]:
    """
    Get the names from a compiled module.

    Instead of using ast, it imports the module.
    Parameters
    ----------
    package : str
        package to import. Must be in sys.path
    underlined : bool
        include underlined names
    """
    # builtins is banned because you never have to import it
    # python_crun is banned because it crashes python
    banned = ["builtins", "python_crun"]
    if package in banned or (package.startswith("_") and not underlined):
        return []  # Builtins is redundant since you don't have to import it.
    results: List[Name] = []
    try:
        module = import_module(str(package))
    except ImportError:
        # print(f"couldn't import {package}")
        return []
    if hasattr(module, "__all__"):
        for name in module.__all__:
            results.append((str(name), package, package, source.value))
    else:
        for name, value in inspect.getmembers(module):
            if underlined or not name.startswith("_"):
                if (
                    inspect.isclass(value)
                    or inspect.isfunction(value)
                    or inspect.isbuiltin(value)
                ):
                    results.append((str(name), package, package, source.value))
    return results
