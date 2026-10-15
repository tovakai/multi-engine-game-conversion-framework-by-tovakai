extends SceneTree
func _initialize():
    call_deferred("_run")
func _run():
    GDExtensionManager.load_extension("res://internal.gdextension")
    var failures = []
    var count = 0
    for mode in [0,1]:
        for projection in [Camera3D.PROJECTION_PERSPECTIVE,Camera3D.PROJECTION_ORTHOGONAL]:
            var original = ClassDB.instantiate("InterpolatedCamera3D")
            var replacement = load("res://interpolated_camera.gd").new()
            if replacement == null:
                quit(2)
                return
            var target = Camera3D.new()
            root.add_child(target)
            root.add_child(original)
            root.add_child(replacement)
            target.position = Vector3(10,2,-3)
            target.rotation = Vector3(0.1,0.2,-0.3)
            target.projection = projection
            target.fov = 50
            target.size = 4
            target.near = 0.2
            target.far = 150
            original.projection = projection
            replacement.projection = projection
            original.set_target(target)
            replacement.set_target(target)
            original.set_speed(1.5)
            replacement.set_speed(1.5)
            original.set_process_mode(mode)
            replacement.interpolation_mode = mode
            original.set_interpolation_enabled(true)
            replacement.set_interpolation_enabled(true)
            for i in range(8):
                if mode == 0:
                    await physics_frame
                else:
                    await process_frame
                count += 1
                if not original.global_transform.is_equal_approx(replacement.global_transform) or abs(original.fov - replacement.fov) > 0.0001 or abs(original.size - replacement.size) > 0.0001 or abs(original.near - replacement.near) > 0.0001 or abs(original.far - replacement.far) > 0.0001:
                    failures.append({"mode":mode,"projection":projection,"frame":i,"native_origin":str(original.global_position),"prototype_origin":str(replacement.global_position),"native_fov":original.fov,"prototype_fov":replacement.fov,"native_size":original.size,"prototype_size":replacement.size})
            original.set_interpolation_enabled(false)
            replacement.set_interpolation_enabled(false)
            var previous = original.global_transform
            var prototype_previous = replacement.global_transform
            target.position = Vector3(-10,4,6)
            await process_frame
            count += 1
            if original.global_transform != previous or replacement.global_transform != prototype_previous:
                failures.append({"disabled_camera_moved":true,"mode":mode})
            original.free()
            replacement.free()
            target.free()
    FileAccess.open("res://camera-parity.json",FileAccess.WRITE).store_string(JSON.stringify({"cases":count,"failures":failures}))
    print("CAMERA_PARITY ",count," checks, ",failures.size()," failures")
    quit(0 if failures.is_empty() else 1)
