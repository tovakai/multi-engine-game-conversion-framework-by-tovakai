extends SceneTree
func _initialize():
    GDExtensionManager.load_extension("res://jsonutils.gdextension")
    var original: RefCounted = ClassDB.instantiate("JsonUtils")
    var replacement = load("res://json_utils.gd").new()
    if replacement == null:
        quit(2)
        return
    var cases = JSON.parse_string(FileAccess.get_file_as_string("res://inputs.json"))
    var failures = []
    for i in range(cases.size()):
        var item = cases[i]
        var before_copy = item.before.duplicate(true)
        var expected = original.diff(item.before,item.after)
        var actual = replacement.diff(item.before,item.after)
        var native_roundtrip = original.patch(item.before, actual)
        var prototype_roundtrip = replacement.patch(item.before, expected)
        if JSON.stringify(expected) != JSON.stringify(actual) or native_roundtrip != item.after or prototype_roundtrip != item.after or item.before != before_copy:
            failures.append({"case":i,"input":item,"expected":expected,"actual":actual,"native_patch":native_roundtrip,"replacement_patch":prototype_roundtrip})
    var invalid = [{}, {"p":null}, {"p":[{"op":"remove","path":"/missing"}]}, {"p":[{"op":"add","path":"/a","value":1},{"op":"remove","path":"/missing"}]}, {"p":[{"op":"replace","path":"/a/00","value":1}]}, {"p":[{"op":"add","path":"invalid","value":1}]}, {"p":[{"op":"add","path":"/~2","value":1}]}]
    for delta in invalid:
        var original_input = {"a":[1,2]}
        if replacement.patch(original_input,delta) != null or original_input != {"a":[1,2]}:
            failures.append({"invalid_patch_accepted":delta})
    var report = {"cases":cases.size(),"invalid_cases":invalid.size(),"failures":failures}
    FileAccess.open("res://json-parity.json",FileAccess.WRITE).store_string(JSON.stringify(report))
    print("JSON_PARITY ",cases.size()," cases, ",failures.size()," failures")
    quit(0 if failures.is_empty() else 1)
