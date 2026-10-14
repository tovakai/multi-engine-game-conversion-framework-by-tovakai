from pathlib import Path
import subprocess
root=Path('/run/media/steamos/SD512/megcfbt-research/until-then-20261014')
try:
 result=subprocess.run([str(root/'launch.sh'),'--headless','--quit'],capture_output=True,timeout=35)
 output=result.stdout+result.stderr;print('STARTUP_EXIT',result.returncode,flush=True)
except subprocess.TimeoutExpired as error:
 output=(error.stdout or b'')+(error.stderr or b'');print('STARTUP_TIMEOUT_OWN_TEST_STOPPED',flush=True)
(root/'startup-headless.log').write_bytes(output)
text=output.decode(errors='replace')
print('\n'.join(text.splitlines()[:35]),flush=True)
