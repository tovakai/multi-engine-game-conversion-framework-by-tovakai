"""Read-only story/binding smoke test; requires the private owner-supplied pack."""
from pathlib import Path
import subprocess,os,argparse
parser=argparse.ArgumentParser()
parser.add_argument('--package-root', type=Path, default=Path('/run/media/steamos/SD512/megcfbt-research/until-then-20261014'))
root=parser.parse_args().package_root.resolve()
if not root.is_relative_to(Path('/run/media/steamos/SD512/megcfbt-research')):raise ValueError('Research package required')
script=root/'story-binding-probe.gd'
script.write_text('''extends SceneTree
func _initialize():
    var file = FileAccess.open("res://assets/story/1/1a/_main.inkb", FileAccess.READ)
    if file == null:
        push_error("STORY_FILE_UNAVAILABLE")
        quit(1)
        return
    var story = InkStory.open(file)
    if story == null:
        push_error("STORY_BINDING_FAILED")
        quit(2)
        return
    var runner = InkRunner.from_ink_story(story, true)
    if runner == null:
        push_error("STORY_RUNNER_FAILED")
        quit(3)
        return
    print("STORY_FILE_AND_RUNNER_VERIFIED")
    quit(0)
''')
result=subprocess.run([str(root/'launch.sh'),'--headless','--script',str(script)],capture_output=True,timeout=40)
log=result.stdout+result.stderr
(root/'story-binding-probe.log').write_bytes(log)
print('STORY_PROBE_EXIT', result.returncode, flush=True)
print(log.decode(errors='replace')[:1200])
if result.returncode or b'STORY_FILE_AND_RUNNER_VERIFIED' not in log or b'Cannot find instance binding callbacks' in log:
    raise RuntimeError('Story binding/format regression failed')
