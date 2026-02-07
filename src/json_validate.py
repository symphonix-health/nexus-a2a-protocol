"""Simple schema validation for dicts.

Schema shape:
- types: mapping key -> "str" | "int" | "bool"
- required: list of required keys
Extra keys in obj are ignored.
"""

from typing import Dict, Any


def validate_simple_schema(obj: Dict[str, Any], schema: Dict[str, Any]) -> None:
    types_map = schema.get("types", {}) or {}
    required = schema.get("required", []) or []

    # Check required keys present
    for key in required:
        if key not in obj:
            raise ValueError(f"missing required key: {key}")

    def check_type(key: str, val: Any, type_str: str) -> bool:
        if type_str == "str":
            return isinstance(val, str)
        if type_str == "int":
            return isinstance(val, int) and not isinstance(val, bool)
        if type_str == "bool":
            return isinstance(val, bool)
        # Unknown type strings are considered invalid
        return False

    for key, type_str in types_map.items():
        if key in obj and not check_type(key, obj[key], type_str):
            raise ValueError(f"key {key} has invalid type; expected {type_str}")
