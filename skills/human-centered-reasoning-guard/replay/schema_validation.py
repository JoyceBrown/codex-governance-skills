"""Offline validation of the bundled HCR contracts using the standard library.

This is a deliberately restricted JSON Schema validator, not a general-purpose
implementation. Every schema keyword is checked before any instance is accepted;
unsupported keywords, formats, and references fail closed. References resolve
only to this package's schema files or their JSON Pointer fragments. No network,
external schema loader, or optional dependency is used.
"""

from __future__ import annotations

from datetime import datetime
import json
import math
from pathlib import Path
import re
from typing import Any
from urllib.parse import unquote


SCHEMA_ROOT = Path(__file__).resolve().parents[1] / "schemas"
MAX_REQUEST_BYTES = 2 * 1024 * 1024
MAX_INPUT_BYTES = MAX_REQUEST_BYTES
MAX_JSON_DEPTH = 32
MAX_JSON_VALUES = 100000
_DRAFT = "https://json-schema.org/draft/2020-12/schema"
_TYPES = {"object", "array", "string", "number", "integer", "boolean", "null"}
_KEYWORDS = {
    "$schema", "$id", "$ref", "$defs", "title", "description", "readOnly",
    "type", "required", "properties", "additionalProperties", "items", "enum",
    "const", "minimum", "maximum", "minLength", "maxLength", "pattern",
    "format", "minItems", "maxItems", "uniqueItems", "allOf", "anyOf", "if",
    "then", "else",
}


class SchemaValidationError(ValueError):
    """A malformed or unsupported contract, reference, or payload."""


def _error(path: str, message: str) -> SchemaValidationError:
    return SchemaValidationError(f"{path}: {message}")


def _finite_number(value: Any) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(value)
    except (OverflowError, TypeError):
        return False


def _json_equal(left: Any, right: Any) -> bool:
    # JSON booleans are distinct from numbers, unlike Python's True == 1.
    if isinstance(left, bool) or isinstance(right, bool):
        return type(left) is type(right) and left == right
    if isinstance(left, dict) and isinstance(right, dict):
        return left.keys() == right.keys() and all(_json_equal(left[key], right[key]) for key in left)
    if isinstance(left, list) and isinstance(right, list):
        return len(left) == len(right) and all(_json_equal(a, b) for a, b in zip(left, right))
    return left == right


def _json_key(value: Any) -> Any:
    """Hashable JSON equality key, keeping booleans separate from numbers."""
    if isinstance(value, dict):
        return ("object", tuple((key, _json_key(item)) for key, item in sorted(value.items())))
    if isinstance(value, list):
        return ("array", tuple(_json_key(item) for item in value))
    if isinstance(value, bool):
        return ("boolean", value)
    if isinstance(value, (int, float)):
        return ("number", value)
    return (type(value).__name__, value)


def _check_json(value: Any, path: str = "$", depth: int = 0, ancestors: frozenset[int] = frozenset(), budget: list[int] | None = None) -> None:
    if budget is None:
        budget = [MAX_JSON_VALUES]
    budget[0] -= 1
    if budget[0] < 0:
        raise _error(path, f"JSON value count exceeds {MAX_JSON_VALUES}")
    if depth > MAX_JSON_DEPTH:
        raise _error(path, f"JSON nesting exceeds {MAX_JSON_DEPTH}")
    if value is None or isinstance(value, (bool, str)):
        return
    if isinstance(value, (int, float)):
        if not _finite_number(value):
            raise _error(path, "numbers must be finite and representable")
        return
    if not isinstance(value, (dict, list)):
        raise _error(path, "expected JSON-compatible object, array, or scalar")
    if id(value) in ancestors:
        raise _error(path, "cyclic JSON value")
    ancestors = ancestors | {id(value)}
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise _error(path, "object keys must be strings")
            _check_json(item, f"{path}.{key}", depth + 1, ancestors, budget)
    else:
        for index, item in enumerate(value):
            _check_json(item, f"{path}[{index}]", depth + 1, ancestors, budget)


def _no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate schema property {key!r}")
        result[key] = value
    return result


def _reject_constant(value: str) -> Any:
    raise ValueError(f"non-finite JSON constant {value!r}")


def _load() -> tuple[dict[str, Any], dict[str, str]]:
    schemas: dict[str, Any] = {}
    ids: dict[str, str] = {}
    try:
        paths = sorted(SCHEMA_ROOT.glob("*.schema.json"))
        if not paths:
            raise ValueError("no bundled HCR schemas found")
        for path in paths:
            if path.resolve().parent != SCHEMA_ROOT.resolve():
                raise ValueError(f"schema {path.name!r} resolves outside bundled directory")
            schema = json.loads(path.read_text(encoding="utf-8"), parse_constant=_reject_constant, object_pairs_hook=_no_duplicates)
            if not isinstance(schema, dict):
                raise ValueError(f"schema {path.name!r} must be an object")
            identifier = schema.get("$id")
            if not isinstance(identifier, str) or not identifier or "#" in identifier:
                raise ValueError(f"schema {path.name!r} requires a unique fragment-free $id")
            if identifier in ids:
                raise ValueError(f"duplicate schema $id {identifier!r}")
            schemas[path.name] = schema
            ids[identifier] = path.name
    except (OSError, UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValueError(f"cannot load bundled HCR schemas: {exc}") from exc
    return schemas, ids


def _resolve(ref: str, current: str, schemas: dict[str, Any], ids: dict[str, str]) -> tuple[Any, str, str]:
    base, separator, fragment = ref.partition("#")
    if not base:
        name = current
    elif base in schemas:
        name = base
    elif base in ids:
        name = ids[base]
    else:
        raise ValueError(f"schema reference is not bundled: {ref!r}")
    target = schemas[name]
    pointer = unquote(fragment) if separator else ""
    if pointer:
        if not pointer.startswith("/"):
            raise ValueError(f"only JSON Pointer schema fragments are supported: {ref!r}")
        for token in pointer[1:].split("/"):
            if re.search(r"~(?![01])", token):
                raise ValueError(f"invalid JSON Pointer escape: {ref!r}")
            token = token.replace("~1", "/").replace("~0", "~")
            if not isinstance(target, dict) or token not in target:
                raise ValueError(f"unresolved bundled schema reference: {ref!r}")
            target = target[token]
    if not isinstance(target, (dict, bool)):
        raise ValueError(f"reference does not address a schema: {ref!r}")
    return target, name, f"{name}#{pointer}"


def _check_schema(schema: Any, name: str, schemas: dict[str, Any], ids: dict[str, str], path: str, seen: set[tuple[str, int]]) -> None:
    if isinstance(schema, bool):
        return
    if not isinstance(schema, dict):
        raise _error(path, "schema must be an object or boolean")
    identity = (name, id(schema))
    if identity in seen:
        return
    seen.add(identity)
    unknown = set(schema) - _KEYWORDS
    if unknown:
        raise _error(path, f"unsupported schema keywords: {', '.join(sorted(unknown))}")
    for keyword in ("$schema", "$id", "$ref", "title", "description", "format", "pattern"):
        if keyword in schema and not isinstance(schema[keyword], str):
            raise _error(path, f"{keyword} must be a string")
    if "$schema" in schema and schema["$schema"] != _DRAFT:
        raise _error(path, "unsupported schema dialect")
    if "$id" in schema and schema is not schemas[name]:
        raise _error(path, "nested $id is unsupported")
    if "format" in schema and schema["format"] != "date-time":
        raise _error(path, "unsupported schema format")
    if "pattern" in schema:
        try:
            re.compile(schema["pattern"])
        except re.error as exc:
            raise _error(path, "invalid schema pattern") from exc
    for keyword in ("readOnly", "uniqueItems"):
        if keyword in schema and not isinstance(schema[keyword], bool):
            raise _error(path, f"{keyword} must be boolean")
    if "type" in schema:
        types = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        if not types or any(not isinstance(item, str) or item not in _TYPES for item in types) or len(set(types)) != len(types):
            raise _error(path, "invalid schema type")
    for keyword in ("minimum", "maximum"):
        if keyword in schema and not _finite_number(schema[keyword]):
            raise _error(path, f"{keyword} must be finite")
    for keyword in ("minLength", "maxLength", "minItems", "maxItems"):
        if keyword in schema and (type(schema[keyword]) is not int or schema[keyword] < 0):
            raise _error(path, f"{keyword} must be a nonnegative integer")
    if "required" in schema:
        required = schema["required"]
        if not isinstance(required, list) or any(not isinstance(item, str) for item in required) or len(set(required)) != len(required):
            raise _error(path, "required must be a list of unique strings")
    if "enum" in schema:
        if not isinstance(schema["enum"], list) or not schema["enum"]:
            raise _error(path, "enum must be a nonempty array")
        _check_json(schema["enum"], path + ".enum")
        for index, item in enumerate(schema["enum"]):
            if any(_json_equal(item, previous) for previous in schema["enum"][:index]):
                raise _error(path, "enum must contain unique values")
    if "const" in schema:
        _check_json(schema["const"], path + ".const")
    for keyword in ("properties", "$defs"):
        if keyword in schema:
            if not isinstance(schema[keyword], dict):
                raise _error(path, f"{keyword} must be an object")
            for key, child in schema[keyword].items():
                _check_schema(child, name, schemas, ids, f"{path}.{keyword}.{key}", seen)
    for keyword in ("items", "additionalProperties", "if", "then", "else"):
        if keyword in schema:
            _check_schema(schema[keyword], name, schemas, ids, f"{path}.{keyword}", seen)
    for keyword in ("then", "else"):
        if keyword in schema and "if" not in schema:
            raise _error(path, f"{keyword} requires if")
    for keyword in ("allOf", "anyOf"):
        if keyword in schema:
            if not isinstance(schema[keyword], list) or not schema[keyword]:
                raise _error(path, f"{keyword} must be a nonempty array of schemas")
            for index, child in enumerate(schema[keyword]):
                _check_schema(child, name, schemas, ids, f"{path}.{keyword}[{index}]", seen)
    if "$ref" in schema:
        target, target_name, target_path = _resolve(schema["$ref"], name, schemas, ids)
        _check_schema(target, target_name, schemas, ids, target_path, seen)


def _schema_set() -> tuple[dict[str, Any], dict[str, str]]:
    schemas, ids = _load()
    seen: set[tuple[str, int]] = set()
    for name, schema in schemas.items():
        _check_schema(schema, name, schemas, ids, name, seen)
    return schemas, ids


def validate_schema_set() -> tuple[str, ...]:
    """Check every bundled contract and reference; return the checked filenames."""
    try:
        schemas, _ = _schema_set()
    except (ValueError, RecursionError) as exc:
        raise SchemaValidationError(str(exc)) from exc
    return tuple(sorted(schemas))


def _type_matches(value: Any, expected: str) -> bool:
    return {
        "object": lambda: isinstance(value, dict),
        "array": lambda: isinstance(value, list),
        "string": lambda: isinstance(value, str),
        "number": lambda: _finite_number(value),
        "integer": lambda: type(value) is int and _finite_number(value),
        "boolean": lambda: isinstance(value, bool),
        "null": lambda: value is None,
    }[expected]()


def _date_time(value: str) -> bool:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}[Tt]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:[Zz]|[+-]\d{2}:\d{2})", value):
        return False
    if value[-1] not in "Zz" and (int(value[-5:-3]) > 23 or int(value[-2:]) > 59):
        return False
    try:
        return datetime.fromisoformat(value.upper().replace("Z", "+00:00")).tzinfo is not None
    except ValueError:
        return False


def _validate(value: Any, schema: Any, name: str, schemas: dict[str, Any], ids: dict[str, str], path: str, active: frozenset[tuple[str, int, str]] = frozenset()) -> None:
    if schema is True:
        return
    if schema is False:
        raise _error(path, "value is not allowed")
    identity = (name, id(schema), path)
    if identity in active:
        raise _error(path, "non-progressing schema reference cycle")
    active = active | {identity}
    if "$ref" in schema:
        target, target_name, _ = _resolve(schema["$ref"], name, schemas, ids)
        _validate(value, target, target_name, schemas, ids, path, active)
    if "type" in schema:
        expected = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        if not any(_type_matches(value, item) for item in expected):
            raise _error(path, f"expected {' or '.join(expected)}")
    if "enum" in schema and not any(_json_equal(value, item) for item in schema["enum"]):
        raise _error(path, "value is outside the allowed enum")
    if "const" in schema and not _json_equal(value, schema["const"]):
        raise _error(path, f"expected constant {schema['const']!r}")
    if _finite_number(value):
        if "minimum" in schema and value < schema["minimum"]:
            raise _error(path, f"must be >= {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            raise _error(path, f"must be <= {schema['maximum']}")
    if isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            raise _error(path, "string is too short")
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            raise _error(path, "string is too long")
        if "pattern" in schema and re.search(schema["pattern"], value) is None:
            raise _error(path, "string does not match the required pattern")
        if schema.get("format") == "date-time" and not _date_time(value):
            raise _error(path, "expected an RFC 3339 date-time with explicit timezone")
    if isinstance(value, dict):
        missing = set(schema.get("required", [])) - set(value)
        if missing:
            raise _error(path, f"missing required properties: {', '.join(sorted(missing))}")
        properties = schema.get("properties", {})
        extra = schema.get("additionalProperties", True)
        for key, item in value.items():
            if key in properties:
                _validate(item, properties[key], name, schemas, ids, f"{path}.{key}", active)
            elif extra is False:
                raise _error(path, f"unknown property {key!r}")
            elif extra is not True:
                _validate(item, extra, name, schemas, ids, f"{path}.{key}", active)
    if isinstance(value, list):
        if "minItems" in schema and len(value) < schema["minItems"]:
            raise _error(path, "array has too few items")
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            raise _error(path, "array exceeds its item budget")
        if schema.get("uniqueItems"):
            seen = set()
            for item in value:
                key = _json_key(item)
                if key in seen:
                    raise _error(path, "array items must be unique")
                seen.add(key)
        if "items" in schema:
            for index, item in enumerate(value):
                _validate(item, schema["items"], name, schemas, ids, f"{path}[{index}]", active)
    for child in schema.get("allOf", []):
        _validate(value, child, name, schemas, ids, path, active)
    if "anyOf" in schema:
        for child in schema["anyOf"]:
            try:
                _validate(value, child, name, schemas, ids, path, active)
                break
            except ValueError:
                continue
        else:
            raise _error(path, "no allowed schema alternative matched")
    if "if" in schema:
        try:
            _validate(value, schema["if"], name, schemas, ids, path, active)
        except ValueError:
            branch = schema.get("else", True)
        else:
            branch = schema.get("then", True)
        _validate(value, branch, name, schemas, ids, path, active)


def validate(instance: Any, schema_name: str) -> None:
    """Validate against a bundled filename or exact bundled $id; raise ValueError.

    JSON types are strict: numeric strings and booleans are never numbers, cost
    counters require integer values, and non-finite numbers are rejected even in
    explicitly opaque state summaries. The replay request is limited to 2 MiB.
    """
    try:
        schemas, ids = _schema_set()
        if not isinstance(schema_name, str):
            raise ValueError("schema_name must be a bundled filename or exact $id")
        if schema_name in ids:
            schema_name = ids[schema_name]
        if schema_name not in schemas:
            raise ValueError(f"schema is not bundled: {schema_name!r}")
        _check_json(instance)
        if schema_name == "hcr-replay-request.schema.json":
            encoded = json.dumps(instance, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")
            if len(encoded) > MAX_REQUEST_BYTES:
                raise ValueError(f"replay request exceeds {MAX_REQUEST_BYTES} bytes")
        _validate(instance, schemas[schema_name], schema_name, schemas, ids, "$")
    except SchemaValidationError:
        raise
    except (ValueError, RecursionError, OverflowError, UnicodeError) as exc:
        raise SchemaValidationError(f"invalid or over-budget HCR data: {exc}") from exc


def load_json(path: str | Path) -> Any:
    """Read bounded UTF-8 JSON, rejecting duplicate keys and non-JSON numbers."""
    try:
        with Path(path).open("rb") as stream:
            raw = stream.read(MAX_INPUT_BYTES + 1)
        if len(raw) > MAX_INPUT_BYTES:
            raise SchemaValidationError(f"JSON input exceeds {MAX_INPUT_BYTES} bytes")
        value = json.loads(raw.decode("utf-8"), parse_constant=_reject_constant, object_pairs_hook=_no_duplicates)
        _check_json(value)
        return value
    except SchemaValidationError:
        raise
    except (OSError, ValueError, RecursionError, OverflowError, UnicodeError) as exc:
        raise SchemaValidationError(f"invalid HCR JSON input: {exc}") from exc


# Descriptive aliases used by host integrations; the short API remains public.
validate_payload = validate
validate_bundle = validate_schema_set
