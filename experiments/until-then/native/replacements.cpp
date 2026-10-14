#include <godot_cpp/godot.hpp>
#include <godot_cpp/core/class_db.hpp>
#include <godot_cpp/classes/ref_counted.hpp>
#include <godot_cpp/classes/camera3d.hpp>
#include <godot_cpp/classes/image.hpp>
#include <godot_cpp/classes/texture2d.hpp>
#include <godot_cpp/classes/json.hpp>
#include <godot_cpp/variant/utility_functions.hpp>
#include <nlohmann/json.hpp>
#include <cstdint>

using namespace godot;

class JsonUtils : public RefCounted {
    GDCLASS(JsonUtils, RefCounted);
protected:
    static void _bind_methods() {
        ClassDB::bind_method(D_METHOD("diff", "before", "after"), &JsonUtils::diff);
        ClassDB::bind_method(D_METHOD("patch", "before", "delta"), &JsonUtils::patch);
    }
public:
    Dictionary diff(const Dictionary &before, const Dictionary &after) {
        try {
            auto a = nlohmann::json::parse(JSON::stringify(before).utf8().get_data());
            auto b = nlohmann::json::parse(JSON::stringify(after).utf8().get_data());
            nlohmann::json result = {{"p", nlohmann::json::diff(a, b)}};
            return JSON::parse_string(String::utf8(result.dump().c_str()));
        } catch (const std::exception &error) {
            UtilityFunctions::push_error(String("JsonUtils diff failed: ") + error.what());
            return Dictionary(); // Missing p must block persistence in experimental integration.
        }
    }
    Variant patch(const Dictionary &before, const Dictionary &delta) {
        try {
            auto a = nlohmann::json::parse(JSON::stringify(before).utf8().get_data());
            auto d = nlohmann::json::parse(JSON::stringify(delta).utf8().get_data());
            auto result = a.patch(d.at("p"));
            return JSON::parse_string(String::utf8(result.dump().c_str()));
        } catch (const std::exception &error) {
            UtilityFunctions::push_error(String("JsonUtils patch failed: ") + error.what());
            return Variant();
        }
    }
};

class Colorizer : public Node {
    GDCLASS(Colorizer, Node);
    int32_t gen_seed = 0;
    Color random_color(const String &component, int offset, float saturation, float low, float high) {
        UtilityFunctions::seed(static_cast<uint64_t>(static_cast<int64_t>(gen_seed) + component.hash() + offset * 23));
        float value = static_cast<float>(UtilityFunctions::randf_range(low, high));
        float sat = static_cast<float>(UtilityFunctions::randf_range(0.0, saturation));
        float hue = static_cast<float>(UtilityFunctions::randf_range(0.0, 1.0));
        return Color::from_hsv(hue, sat, value, 1.0f);
    }
protected:
    static void _bind_methods() {
        ClassDB::bind_method(D_METHOD("set_gen_seed", "value"), &Colorizer::set_gen_seed);
        ClassDB::bind_method(D_METHOD("get_gen_seed"), &Colorizer::get_gen_seed);
        ClassDB::bind_method(D_METHOD("manipulate", "image", "component", "gender"), &Colorizer::manipulate);
        ClassDB::bind_method(D_METHOD("colorize", "textures", "component", "gender"), &Colorizer::colorize);
    }
public:
    void set_gen_seed(int64_t value) { gen_seed = static_cast<int32_t>(static_cast<uint32_t>(value)); }
    int64_t get_gen_seed() const { return gen_seed; }
    Ref<Image> manipulate(const Ref<Image> &image, const String &component, int gender) {
        if (image.is_null()) { UtilityFunctions::push_error("Colorizer requires an image"); return Ref<Image>(); }
        if (component == "skin" || (component == "hair" && gender == 0)) return image;
        Color multiplier;
        if (component == "hair" && gender == 1) {
            UtilityFunctions::seed(static_cast<uint64_t>(static_cast<int64_t>(gen_seed) + component.hash() + 23));
            multiplier = UtilityFunctions::randf() < 0.1 ? random_color(component, 2, 0.4f, 0.8f, 1.0f) : Color(0.25f,0.25f,0.25f,1.0f);
        } else multiplier = random_color(component, 0, 0.5f, 0.4f, 0.9f);
        for (int y = 0; y < image->get_height(); ++y)
            for (int x = 0; x < image->get_width(); ++x)
                image->set_pixel(x, y, image->get_pixel(x,y) * multiplier);
        return image;
    }
    Array colorize(const Array &textures, const String &component, int gender) {
        Array images;
        for (int64_t i = 0; i < textures.size(); ++i) {
            Ref<Texture2D> texture = textures[i];
            if (texture.is_null()) { UtilityFunctions::push_error("Colorizer requires Texture2D inputs"); return Array(); }
            images.append(manipulate(texture->get_image(), component, gender));
        }
        return images;
    }
};

class InterpolatedCamera3D : public Camera3D {
    GDCLASS(InterpolatedCamera3D, Camera3D);
    NodePath target;
    double speed = 1.0;
    bool enabled = false;
    int mode = 1;
    void interpolate(double delta) {
        if (!enabled || target.is_empty() || !is_inside_tree()) return;
        Node3D *object = Object::cast_to<Node3D>(get_node_or_null(target));
        if (!object) return;
        double weight = speed * delta;
        set_global_transform(get_global_transform().interpolate_with(object->get_global_transform(), weight));
        Camera3D *camera = Object::cast_to<Camera3D>(object);
        if (camera && get_projection() == camera->get_projection()) {
            double near_plane = Math::lerp(get_near(), camera->get_near(), weight);
            double far_plane = Math::lerp(get_far(), camera->get_far(), weight);
            if (get_projection() == PROJECTION_PERSPECTIVE)
                set_perspective(Math::lerp(get_fov(), camera->get_fov(), weight), near_plane, far_plane);
            else if (get_projection() == PROJECTION_ORTHOGONAL)
                set_orthogonal(Math::lerp(get_size(), camera->get_size(), weight), near_plane, far_plane);
        }
    }
protected:
    static void _bind_methods() {
        ClassDB::bind_method(D_METHOD("set_target_path", "path"), &InterpolatedCamera3D::set_target_path);
        ClassDB::bind_method(D_METHOD("get_target_path"), &InterpolatedCamera3D::get_target_path);
        ClassDB::bind_method(D_METHOD("set_target", "object"), &InterpolatedCamera3D::set_target);
        ClassDB::bind_method(D_METHOD("set_speed", "value"), &InterpolatedCamera3D::set_speed);
        ClassDB::bind_method(D_METHOD("get_speed"), &InterpolatedCamera3D::get_speed);
        ClassDB::bind_method(D_METHOD("set_interpolation_enabled", "value"), &InterpolatedCamera3D::set_enabled);
        ClassDB::bind_method(D_METHOD("is_interpolation_enabled"), &InterpolatedCamera3D::get_enabled);
        ClassDB::bind_method(D_METHOD("set_process_mode", "value"), &InterpolatedCamera3D::set_interpolation_mode);
        ClassDB::bind_method(D_METHOD("get_process_mode"), &InterpolatedCamera3D::get_interpolation_mode);
        ADD_PROPERTY(PropertyInfo(Variant::NODE_PATH,"target"),"set_target_path","get_target_path");
        ADD_PROPERTY(PropertyInfo(Variant::FLOAT,"speed"),"set_speed","get_speed");
        ADD_PROPERTY(PropertyInfo(Variant::BOOL,"enabled"),"set_interpolation_enabled","is_interpolation_enabled");
        ADD_PROPERTY(PropertyInfo(Variant::INT,"process_mode",PROPERTY_HINT_ENUM,"Physics,Idle"),"set_process_mode","get_process_mode");
        BIND_CONSTANT(INTERPOLATED_CAMERA_PROCESS_PHYSICS);
        BIND_CONSTANT(INTERPOLATED_CAMERA_PROCESS_IDLE);
    }
public:
    enum { INTERPOLATED_CAMERA_PROCESS_PHYSICS=0, INTERPOLATED_CAMERA_PROCESS_IDLE=1 };
    void _notification(int what) {
        if (what == NOTIFICATION_PROCESS && mode == 1) interpolate(get_process_delta_time());
        if (what == NOTIFICATION_PHYSICS_PROCESS && mode == 0) interpolate(get_physics_process_delta_time());
    }
    void set_target_path(const NodePath &path) { target = path; }
    NodePath get_target_path() const { return target; }
    bool set_target(Node *object) {
        if (!object || !is_inside_tree() || !object->is_inside_tree()) return false;
        target = get_path_to(object); return true;
    }
    void set_speed(double value) { speed = value; }
    double get_speed() const { return speed; }
    void set_enabled(bool value) { enabled=value; set_process(enabled && mode==1); set_physics_process(enabled && mode==0); }
    bool get_enabled() const { return enabled; }
    void set_interpolation_mode(int value) { if (value!=0 && value!=1) return; mode=value; set_enabled(enabled); }
    int get_interpolation_mode() const { return mode; }
};

void initialize(ModuleInitializationLevel level) {
    if (level != MODULE_INITIALIZATION_LEVEL_SCENE) return;
    ClassDB::register_class<JsonUtils>();
    ClassDB::register_class<Colorizer>();
    ClassDB::register_class<InterpolatedCamera3D>();
}
void terminate(ModuleInitializationLevel) {}
extern "C" GDExtensionBool GDE_EXPORT megcfbt_untilthen_init(GDExtensionInterfaceGetProcAddress get_proc_address,
    GDExtensionClassLibraryPtr library, GDExtensionInitialization *initialization) {
    GDExtensionBinding::InitObject init(get_proc_address, library, initialization);
    init.register_initializer(initialize);
    init.register_terminator(terminate);
    init.set_minimum_library_initialization_level(MODULE_INITIALIZATION_LEVEL_SCENE);
    return init.init();
}

// Separate resource entry points retain the original pack's extension descriptors.
// Copy the owned replacement library to each descriptor's Linux path so each
// GDExtension has its own binding state and class registration ownership.
void initialize_internal(ModuleInitializationLevel level) {
    if (level != MODULE_INITIALIZATION_LEVEL_SCENE) return;
    ClassDB::register_class<Colorizer>();
    ClassDB::register_class<InterpolatedCamera3D>();
}
void initialize_json(ModuleInitializationLevel level) {
    if (level == MODULE_INITIALIZATION_LEVEL_SCENE) ClassDB::register_class<JsonUtils>();
}
extern "C" GDExtensionBool GDE_EXPORT internal_library_init(GDExtensionInterfaceGetProcAddress get_proc_address,
    GDExtensionClassLibraryPtr library, GDExtensionInitialization *initialization) {
    GDExtensionBinding::InitObject init(get_proc_address, library, initialization);
    init.register_initializer(initialize_internal);
    init.register_terminator(terminate);
    init.set_minimum_library_initialization_level(MODULE_INITIALIZATION_LEVEL_SCENE);
    return init.init();
}
extern "C" GDExtensionBool GDE_EXPORT jsonutils_library_init(GDExtensionInterfaceGetProcAddress get_proc_address,
    GDExtensionClassLibraryPtr library, GDExtensionInitialization *initialization) {
    GDExtensionBinding::InitObject init(get_proc_address, library, initialization);
    init.register_initializer(initialize_json);
    init.register_terminator(terminate);
    init.set_minimum_library_initialization_level(MODULE_INITIALIZATION_LEVEL_SCENE);
    return init.init();
}
