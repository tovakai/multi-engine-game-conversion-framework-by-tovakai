extends RefCounted
# Experimental behavior prototype. Not installed into game packages.

func diff(before: Dictionary, after: Dictionary) -> Dictionary:
    var operations: Array = []
    _diff(before, after, "", operations)
    return {"p": operations}

func _same(a, b) -> bool:
    if typeof(a) != typeof(b):
        if typeof(a) in [TYPE_INT, TYPE_FLOAT] and typeof(b) in [TYPE_INT, TYPE_FLOAT]:
            return a == b
        return false
    return a == b

func _copy(value):
    return value.duplicate(true) if value is Array or value is Dictionary else value

func _escape(key: String) -> String:
    return key.replace("~", "~0").replace("/", "~1")

func _diff(before, after, path: String, operations: Array):
    if _same(before, after):
        return
    if before is Dictionary and after is Dictionary:
        var keys = before.keys()
        keys.sort()
        for key in keys:
            var child = path + "/" + _escape(str(key))
            if after.has(key):
                _diff(before[key], after[key], child, operations)
            else:
                operations.append({"op":"remove", "path":child})
        keys = after.keys()
        keys.sort()
        for key in keys:
            if not before.has(key):
                operations.append({"op":"add", "path":path + "/" + _escape(str(key)), "value":_copy(after[key])})
    elif before is Array and after is Array:
        var shared = mini(before.size(), after.size())
        for i in range(shared):
            _diff(before[i], after[i], path + "/" + str(i), operations)
        for i in range(before.size() - 1, shared - 1, -1):
            operations.append({"op":"remove", "path":path + "/" + str(i)})
        for i in range(shared, after.size()):
            operations.append({"op":"add", "path":path + "/-", "value":_copy(after[i])})
    else:
        operations.append({"op":"replace", "path":path, "value":_copy(after)})

# Invalid patches produce null, never a fabricated successful database.
# The caller must check this before persisting anything in a future integration.
func patch(before: Dictionary, delta: Dictionary):
    if not delta.has("p") or not delta.p is Array:
        return null
    var result = _copy(before)
    for operation in delta.p:
        if not operation is Dictionary or not operation.get("op") in ["add", "remove", "replace"]:
            return null
        if not operation.get("path") is String:
            return null
        var action: String = operation.op
        if action != "remove" and not operation.has("value"):
            return null
        if operation.path == "":
            result = null if action == "remove" else _copy(operation.value)
            continue
        if not operation.path.begins_with("/"):
            return null
        var tokens: Array = []
        for raw in operation.path.substr(1).split("/"):
            # Reject invalid escape sequences; decode ~1 before ~0.
            var stripped = raw.replace("~0", "").replace("~1", "")
            if "~" in stripped:
                return null
            tokens.append(raw.replace("~1", "/").replace("~0", "~"))
        var parent = result
        for i in range(tokens.size() - 1):
            var token: String = tokens[i]
            if parent is Dictionary and parent.has(token):
                parent = parent[token]
            elif parent is Array:
                var idx = _index(token, parent.size(), false)
                if idx < 0:
                    return null
                parent = parent[idx]
            else:
                return null
        var last: String = tokens[-1]
        if parent is Dictionary:
            if action != "add" and not parent.has(last):
                return null
            if action == "remove":
                parent.erase(last)
            else:
                parent[last] = _copy(operation.value)
        elif parent is Array:
            var idx = _index(last, parent.size(), action == "add")
            if idx < 0:
                return null
            if action == "add":
                parent.insert(idx, _copy(operation.value))
            elif action == "remove":
                parent.remove_at(idx)
            else:
                parent[idx] = _copy(operation.value)
        else:
            return null
    return result

func _index(token: String, size: int, adding: bool) -> int:
    if token == "-":
        return size if adding else -1
    if token.is_empty() or (token.length() > 1 and token.begins_with("0")):
        return -1
    for character in token:
        if character < "0" or character > "9":
            return -1
    if token.length() > 10:
        return -1
    var value = int(token)
    return value if value < size or (adding and value == size) else -1
