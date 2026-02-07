"""Implement flatten_json(obj, sep): flatten nested dictionaries and lists.

Write keys joined by `sep`. Lists should use integer indices in the path.
"""

from collections.abc import Mapping


def flatten_json(obj: dict, sep: str = ".") -> dict:
    if not isinstance(obj, Mapping):
        raise TypeError("obj must be a dictionary-like mapping")

    flattened: dict[str, object] = {}

    def walk(value: object, path: str) -> None:
        if isinstance(value, Mapping):
            for key, child in value.items():
                child_path = f"{path}{sep}{key}" if path else str(key)
                walk(child, child_path)
            return

        if isinstance(value, list):
            for index, child in enumerate(value):
                child_path = f"{path}{sep}{index}" if path else str(index)
                walk(child, child_path)
            return

        flattened[path] = value

    for root_key, root_value in obj.items():
        walk(root_value, str(root_key))

    return flattened
