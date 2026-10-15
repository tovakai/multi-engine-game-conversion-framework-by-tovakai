extends Camera3D
# Experimental API prototype; interpolation parity must be established first.
var interpolation_speed: float = 1.0
var interpolation_enabled: bool = false
var target_path: NodePath
var target_object: Node3D
var interpolation_mode: int = 1

func set_target_path(path: NodePath):
    target_path = path
    target_object = get_node_or_null(path) as Node3D if is_inside_tree() else null
func get_target_path() -> NodePath:
    return target_path
func set_target(object: Node3D):
    target_object = object
    target_path = get_path_to(object) if is_inside_tree() and object.is_inside_tree() else NodePath()
func set_speed(value: float):
    interpolation_speed = value
func get_speed() -> float:
    return interpolation_speed
func set_interpolation_enabled(value: bool):
    interpolation_enabled = value
func is_interpolation_enabled() -> bool:
    return interpolation_enabled
func _ready():
    if not target_path.is_empty():
        target_object = get_node_or_null(target_path) as Node3D
func _process(delta: float):
    if interpolation_mode == 1:
        _interpolate(delta)
func _physics_process(delta: float):
    if interpolation_mode == 0:
        _interpolate(delta)
func _interpolate(delta: float):
    if interpolation_enabled and is_instance_valid(target_object):
        global_transform = global_transform.interpolate_with(target_object.global_transform, interpolation_speed * delta)

        if target_object is Camera3D:
            var weight = interpolation_speed * delta
            if projection == target_object.projection:
                var interpolated_near = lerpf(near, target_object.near, weight)
                var interpolated_far = lerpf(far, target_object.far, weight)
                if projection == PROJECTION_PERSPECTIVE:
                    set_perspective(lerpf(fov, target_object.fov, weight), interpolated_near, interpolated_far)
                else:
                    set_orthogonal(lerpf(size, target_object.size, weight), interpolated_near, interpolated_far)
