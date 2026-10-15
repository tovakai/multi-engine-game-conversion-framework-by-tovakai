"""Portable explicit per-shortcut Steam Input setup; never changes global layouts."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import time

try:
    from .steam_cdp import evaluate, SteamClientError
except ImportError:  # Copied beside steam_cdp.py in converted packages.
    from steam_cdp import evaluate, SteamClientError


def steam_root():
    for root in (Path.home() / ".steam/steam", Path.home() / ".local/share/Steam"):
        if (root / "controller_base").is_dir():
            return root.resolve()
    raise ValueError("Steam's controller template directory was not found.")


def inspect(evaluate_fn=evaluate):
    return evaluate_fn("""(() => ({
      apps: appStore.allApps.filter(a=>a.app_type===1073741824)
        .map(a=>({appid:a.appid,name:a.display_name||a.name||String(a.appid)})),
      controllers: ControllerStore.m_controllerList.map(c=>({index:c.nControllerIndex,
        name:c.strName,type:c.eControllerType}))
    }))()""")


def publish(directory: Path, kind: str, root: Path):
    manifest = json.loads((directory / "profile.json").read_text(encoding="utf-8"))
    entry = manifest["controllers"].get(kind)
    if not entry:
        raise ValueError("This profile does not include that controller type.")
    name = entry["file"]
    if Path(name).name != name or not name.startswith("megcfbt-controller-pointer-v1-"):
        raise ValueError("Unsafe controller profile filename.")
    source = directory / name
    if source.is_symlink():
        raise ValueError("Controller profile must not be a symbolic link.")
    data = source.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest != entry["sha256"]:
        raise ValueError("Controller profile checksum failed; regenerate the package.")
    # Content-addressed filenames avoid overwriting Steam or personal templates.
    name = source.stem + "-" + digest[:16] + ".vdf"
    destination = root / "controller_base/templates" / name
    if destination.is_symlink() or (destination.exists() and destination.read_bytes() != data):
        raise ValueError("An unrelated controller template already uses this filename.")
    if not destination.exists():
        with destination.open("xb") as stream:
            stream.write(data)
    return "template://" + name


def _routing_guard(appid, parent):
    return f"""if (appStore.allApps.some(a=>a.appid==={appid} ||
      (a.app_type===1073741824 && a.appid!=={parent} && (a.appid & 0xFFFFFF)==={appid})))
      throw new Error('Routing ID belongs to another Steam entry');"""


def selection(appid, index, evaluate_fn=evaluate, *, shortcut_id=None):
    if type(appid) is not int or not 0 < appid <= 0xFFFFFFFF or type(index) is not int or not 0 <= index < 64:
        raise ValueError("Choose a valid shortcut AppID and controller index.")
    parent = appid if shortcut_id is None else shortcut_id
    if shortcut_id is not None:
        if type(parent) is not int or not 0 < parent <= 0xFFFFFFFF or appid != (parent & 0xFFFFFF) or appid == parent or appid < 1000:
            raise ValueError("Invalid Frame routing ID for this shortcut.")
    collision_check = _routing_guard(appid, parent) if shortcut_id is not None else ""
    result = evaluate_fn(f"""(async()=>{{
      {collision_check}
      if (!appStore.allApps.some(a=>a.appid==={parent}&&a.app_type===1073741824))
        throw new Error('Non-Steam entry is missing; refresh the list');
      if (!ControllerStore.m_controllerList.some(c=>c.nControllerIndex==={index}))
        throw new Error('Wake the controller and open the Steam dashboard');
      return await SteamClient.Input.GetConfigForAppAndController({appid},{index});
    }})()""")
    if not isinstance(result, dict):
        raise ValueError("Steam did not return controller selection information.")
    return result


def validate_preview(appid, index, url, evaluate_fn=evaluate, *, shortcut_id=None):
    selection(appid, index, evaluate_fn, shortcut_id=shortcut_id)
    result = evaluate_fn(f"""(async()=>{{
      const data=await SteamClient.Input.PreviewConfigForAppAndController({appid},{index},{json.dumps(url)});
      return {{bytes:data&&(data.byteLength||data.length)||0}};
    }})()""")
    if not isinstance(result, dict) or not result.get("bytes"):
        raise ValueError("Steam could not parse this controller profile. No selection was changed.")
    return result


def _write_receipt(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation keeps two concurrent setup invocations from replacing
    # each other's original selection. Flush the backup before changing Steam.
    with path.open("x", encoding="utf-8") as stream:
        try:
            json.dump(payload, stream, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        except BaseException:
            path.unlink(missing_ok=True)
            raise


def set_selection(appid, index, expected_url, replacement_url, evaluate_fn=evaluate, *, shortcut_id=None):
    # Compare again in Steam immediately before writing; another UI edit wins.
    # Default URLs describe a fallback, not an importable template. Restoring
    # one requires clearing our explicit selection through Steam's API.
    operation = (f"SteamClient.Input.ClearSelectedConfigForApp({appid},{index},0);"
                 if replacement_url.startswith("default://") else
                 f"SteamClient.Input.SetSelectedConfigForApp({appid},{index},{json.dumps(replacement_url)},false,0);")
    routing_guard = _routing_guard(appid, shortcut_id) if shortcut_id is not None else ""
    evaluate_fn(f"""(async()=>{{
      {routing_guard}
      const current=await SteamClient.Input.GetConfigForAppAndController({appid},{index});
      if ((current.URL||null)!=={json.dumps(expected_url)}) throw new Error('Controller selection changed');
      if (!current.bConfigurationEnabled) throw new Error('Enable Steam Input for this entry first');
      {operation}
      return true;
    }})()""")
    # Steam may take several seconds to reload a running game's configuration.
    for _ in range(100):
        current = selection(appid, index, evaluate_fn, shortcut_id=shortcut_id)
        if current.get("URL") == replacement_url:
            return
        time.sleep(0.1)
    raise ValueError("Steam has not confirmed the layout. Backup retained; inspect before retrying.")


def apply(appid, index, url, receipt: Path, evaluate_fn=evaluate, *, shortcut_id=None):
    if receipt.exists():
        raise ValueError("A selection backup already exists. Restore it before applying again.")
    before = selection(appid, index, evaluate_fn, shortcut_id=shortcut_id)
    if not before.get("bConfigurationEnabled") or not isinstance(before.get("URL"), str):
        raise ValueError("Enable Steam Input for this non-Steam entry in Steam first.")
    if before.get("eSelectionType", 0) != 0:
        raise ValueError("This Steam selection type is not supported by the experimental setup.")
    validate_preview(appid, index, url, evaluate_fn, shortcut_id=shortcut_id)
    _write_receipt(receipt, {"appid": appid, "controller_index": index,
                           "before_url": before["URL"], "applied_url": url, "shortcut_id": shortcut_id,
                           "controller_type": before.get("nControllerType")})
    set_selection(appid, index, before["URL"], url, evaluate_fn, shortcut_id=shortcut_id)


def restore(receipt: Path, evaluate_fn=evaluate):
    data = json.loads(receipt.read_text(encoding="utf-8"))
    current = selection(data["appid"], data["controller_index"], evaluate_fn, shortcut_id=data.get("shortcut_id"))
    if data.get("controller_type") is not None and current.get("nControllerType") != data["controller_type"]:
        raise ValueError("The controller at this index changed. Reconnect the original controller before restoring.")
    if current.get("URL") != data["applied_url"]:
        raise ValueError("The controller layout changed after setup; refusing to replace the newer selection.")
    set_selection(data["appid"], data["controller_index"], data["applied_url"], data["before_url"], evaluate_fn, shortcut_id=data.get("shortcut_id"))
    receipt.rename(receipt.with_name(receipt.stem + f".restored-{time.time_ns()}.json"))


def main(argv=None):
    parser = argparse.ArgumentParser(description="Opt-in controller directions and R3 pointer toggle")
    parser.add_argument("--appid", type=int, help="existing non-Steam shortcut's AppID (see --list)")
    parser.add_argument("--controller-index", type=int, default=0)
    parser.add_argument("--controller-type", default="controller_steamframe_pair")
    parser.add_argument("--frame-routing", action="store_true",
                        help="configure the Frame's shortened active input ID instead; separate backup/restore")
    parser.add_argument("--list", action="store_true", help="list existing shortcuts and connected controllers")
    parser.add_argument("--apply", action="store_true", help="explicitly select this layout for this entry")
    parser.add_argument("--restore", action="store_true", help="restore the backed-up selection")
    args = parser.parse_args(argv)
    directory = Path(__file__).resolve().parent
    parent = args.appid if args.frame_routing else None
    target = (args.appid & 0xFFFFFF) if args.frame_routing and args.appid is not None else args.appid
    prefix = "selection-frame-routing" if args.frame_routing else "selection"
    receipt = directory / f"{prefix}-{args.appid}-{args.controller_index}.json"
    try:
        if args.list:
            print(json.dumps(inspect(), indent=2))
            return 0
        if args.appid is None or (args.apply and args.restore):
            parser.error("choose --appid and at most one of --apply/--restore")
        if args.restore:
            restore(receipt)
            print("Previous per-game controller layout restored.")
        else:
            selection(target, args.controller_index, shortcut_id=parent)
            url = publish(directory, args.controller_type, steam_root())
            if args.apply:
                apply(target, args.controller_index, url, receipt, shortcut_id=parent)
                print("Applied. R3 toggles pointer mode; RT clicks/drags and LT right-clicks in pointer mode.")
            else:
                print(json.dumps({"template": url, "preview": validate_preview(target, args.controller_index, url, shortcut_id=parent),
                                  "applied": False}, indent=2))
        return 0
    except (OSError, ValueError, KeyError, SteamClientError) as exc:
        print("Controller setup: " + str(exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
