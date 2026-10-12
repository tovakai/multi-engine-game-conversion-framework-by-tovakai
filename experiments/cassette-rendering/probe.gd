extends SceneTree

func _initialize():
    var renderer = VisualServer.get_video_adapter_name()
    var vendor = VisualServer.get_video_adapter_vendor()
    var enabled = ProjectSettings.get_setting("rendering/quality/depth_prepass/enable")
    var excluded = ProjectSettings.get_setting("rendering/quality/depth_prepass/disable_for_vendors")
    var matches = []
    for token in str(excluded).split(","):
        token = token.strip_edges()
        if token != "" and renderer.to_lower().find(token.to_lower()) != -1:
            matches.append(token)
    print("CASSETTE_RENDER_PROBE ", JSON.print({
        "vendor": vendor, "renderer": renderer,
        "driver": OS.get_video_driver_name(OS.get_current_video_driver()),
        "prepass_setting": enabled, "excluded_renderers": excluded,
        "matched_exclusions": matches,
        "prepass_expected_from_source": enabled and matches.empty(),
        "override_path": ProjectSettings.get_setting("application/config/project_settings_override"),
        "window_size": str(OS.window_size)
    }))
    quit()
