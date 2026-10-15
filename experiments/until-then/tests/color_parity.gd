extends SceneTree
func _initialize():
    GDExtensionManager.load_extension("res://internal.gdextension")
    var original = ClassDB.instantiate("Colorizer")
    var replacement = load("res://colorizer.gd").new()
    if replacement == null:
        quit(2)
        return
    var failures = []
    var count = 0
    for component in ["skin","bottom","top","hair","facemask"]:
        for gender in [0,1]:
            for gen_seed in range(256):
                var a = Image.create(6,1,false,Image.FORMAT_RGBA8)
                var pixels = [Color(0,0,0,1),Color(0.25,0.25,0.25,1),Color(0.5,0.5,0.5,1),Color(1,1,1,1),Color(1,0,0,1),Color(0.5,0.5,0.5,0)]
                for i in range(6): a.set_pixel(i,0,pixels[i])
                var b = Image.create_from_data(a.get_width(),a.get_height(),false,a.get_format(),a.get_data())
                seed(12345)
                original.set_gen_seed(gen_seed)
                original.manipulate(a,component,gender)
                var original_next = randi()
                seed(12345)
                replacement.set_gen_seed(gen_seed)
                replacement.manipulate(b,component,gender)
                var replacement_next = randi()
                count += 1
                if a.get_data() != b.get_data() or original_next != replacement_next:
                    failures.append({"component":component,"gender":gender,"seed":gen_seed,"expected":Array(a.get_data()),"actual":Array(b.get_data()),"native_next_random":original_next,"replacement_next_random":replacement_next})
    original.free()
    replacement.free()
    FileAccess.open("res://color-parity.json",FileAccess.WRITE).store_string(JSON.stringify({"cases":count,"failures":failures}))
    print("COLOR_PARITY ",count," cases, ",failures.size()," failures")
    quit(0 if failures.is_empty() else 1)
