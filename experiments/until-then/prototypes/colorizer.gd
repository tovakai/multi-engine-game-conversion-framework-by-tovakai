extends Node
# Experimental behavior prototype, tested against user-owned native library.
var gen_seed: int = 0
func set_gen_seed(value: int):
    # Original native member is signed int32.
    gen_seed = value & 0xffffffff
    if gen_seed >= 2147483648:
        gen_seed -= 4294967296
func get_gen_seed() -> int:
    return gen_seed
func _random_color(component: String, offset: int, saturation_max: float, value_min: float, value_max: float) -> Color:
    seed(gen_seed + component.hash() + offset * 23)
    var value = randf_range(value_min, value_max)
    var saturation = randf_range(0, saturation_max)
    var hue = randf_range(0, 1)
    return Color.from_hsv(hue, saturation, value, 1)
func manipulate(image: Image, component: String, gender: int) -> Image:
    if component == "skin" or (component == "hair" and gender == 0):
        return image
    var multiplier: Color
    if component == "hair" and gender == 1:
        seed(gen_seed + component.hash() + 23)
        if randf() < 0.1:
            multiplier = _random_color(component, 2, 0.4, 0.8, 1.0)
        else:
            multiplier = Color(0.25, 0.25, 0.25, 1)
    else:
        multiplier = _random_color(component, 0, 0.5, 0.4, 0.9)
    for y in range(image.get_height()):
        for x in range(image.get_width()):
            image.set_pixel(x, y, image.get_pixel(x, y) * multiplier)
    return image
func colorize(textures: Array, component: String, gender: int) -> Array:
    var images: Array = []
    for texture in textures:
        if not texture is Texture2D:
            push_error("Colorizer.colorize requires Texture2D inputs")
            return []
        images.append(manipulate(texture.get_image(), component, gender))
    return images
