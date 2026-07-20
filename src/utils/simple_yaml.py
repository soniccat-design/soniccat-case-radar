from __future__ import annotations

import re
from typing import Any, List, Tuple


class SimpleYamlError(ValueError):
    pass


def load(text: str) -> Any:
    """Parse the restricted YAML shape used by this project.

    PyYAML is used in production when installed. This fallback keeps local tests
    independent from third-party packages and supports comments, dictionaries,
    lists, quoted strings, booleans, numbers, [] and {}.
    """
    lines = _tokenize(text)
    if not lines:
        return {}
    data, index = _parse_block(lines, 0, lines[0][0])
    if index != len(lines):
        raise SimpleYamlError("Unexpected trailing YAML content")
    return data


def _tokenize(text: str) -> List[Tuple[int, str]]:
    result: List[Tuple[int, str]] = []
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        without_comment = _strip_comment(raw.rstrip())
        if not without_comment.strip():
            continue
        indent = len(without_comment) - len(without_comment.lstrip(" "))
        if indent % 2 != 0:
            raise SimpleYamlError("Indentation must use multiples of two spaces")
        result.append((indent, without_comment.strip()))
    return result


def _strip_comment(line: str) -> str:
    in_single = False
    in_double = False
    previous = ""
    for index, char in enumerate(line):
        if char == "'" and not in_double:
            in_single = not in_single
        elif char == '"' and not in_single and previous != "\\":
            in_double = not in_double
        elif char == "#" and not in_single and not in_double:
            if index == 0 or line[index - 1].isspace():
                return line[:index].rstrip()
        previous = char
    return line


def _parse_block(lines: List[Tuple[int, str]], index: int, indent: int) -> Tuple[Any, int]:
    if index >= len(lines):
        return {}, index
    if lines[index][0] < indent:
        return {}, index
    if lines[index][1].startswith("- "):
        return _parse_list(lines, index, indent)
    return _parse_dict(lines, index, indent)


def _parse_list(lines: List[Tuple[int, str]], index: int, indent: int) -> Tuple[List[Any], int]:
    values: List[Any] = []
    while index < len(lines):
        current_indent, content = lines[index]
        if current_indent < indent:
            break
        if current_indent != indent or not content.startswith("- "):
            break
        rest = content[2:].strip()
        index += 1
        if not rest:
            child, index = _parse_block(lines, index, indent + 2)
            values.append(child)
        elif _looks_like_key_value(rest):
            key, value = _split_key_value(rest)
            item = {key: _parse_scalar(value)}
            if index < len(lines) and lines[index][0] > indent:
                child, index = _parse_block(lines, index, indent + 2)
                if isinstance(child, dict):
                    item.update(child)
                else:
                    raise SimpleYamlError("List mapping children must be key/value pairs")
            values.append(item)
        else:
            values.append(_parse_scalar(rest))
    return values, index


def _parse_dict(lines: List[Tuple[int, str]], index: int, indent: int) -> Tuple[dict, int]:
    values = {}
    while index < len(lines):
        current_indent, content = lines[index]
        if current_indent < indent:
            break
        if current_indent != indent or content.startswith("- "):
            break
        key, value = _split_key_value(content)
        index += 1
        if value == "":
            if index < len(lines) and lines[index][0] > indent:
                child, index = _parse_block(lines, index, indent + 2)
                values[key] = child
            else:
                values[key] = None
        else:
            values[key] = _parse_scalar(value)
    return values, index


def _looks_like_key_value(value: str) -> bool:
    return bool(re.match(r"^[A-Za-z0-9_\-\u4e00-\u9fff]+:\s*", value))


def _split_key_value(content: str) -> Tuple[str, str]:
    if ":" not in content:
        raise SimpleYamlError("Missing ':' in YAML mapping: %s" % content)
    key, value = content.split(":", 1)
    return key.strip(), value.strip()


def _parse_scalar(value: str) -> Any:
    if value == "":
        return ""
    if value in ("[]",):
        return []
    if value in ("{}",):
        return {}
    lowered = value.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if lowered in ("null", "none", "~"):
        return None
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return value[1:-1]
    if re.match(r"^-?\d+$", value):
        try:
            return int(value)
        except ValueError:
            return value
    if re.match(r"^-?\d+\.\d+$", value):
        try:
            return float(value)
        except ValueError:
            return value
    return value
