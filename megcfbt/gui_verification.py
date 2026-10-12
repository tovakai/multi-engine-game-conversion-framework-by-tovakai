"""Explicit frozen-GUI acceptance runner for automatic conversion workflows.

This exercises the shipped widgets, drop handler and Convert command. It avoids
native modal dialogs so release checks can run on a desktop without focus access.
No runtime, detection, download or builder functions are replaced.
"""
from __future__ import annotations
import argparse
import contextlib
import io
import json
import sys
from pathlib import Path
import time
from types import SimpleNamespace
from megcfbt import gui, APP_NAME, __version__
from megcfbt.version import display_version, get_build_info


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--verify-gui-conversion',type=Path)
    mode.add_argument('--verify-gui-startup',action='store_true')
    parser.add_argument('--output-dir',type=Path)
    parser.add_argument('--receipt',type=Path,required=True)
    parser.add_argument('--timeout',type=int,default=900)
    parser.add_argument('--backend-runtime', type=Path,
                        help='Explicit runtime directory selected for this acceptance run')
    parser.add_argument('--fmod-sdk', type=Path,
                        help='Owner FMOD Linux SDK selected for Celeste acceptance')
    parser.add_argument('--approve-renpy-prerelease-migration',action='store_true',
                        help='Explicitly approve the experimental full-engine nightly migration for this acceptance run')
    args=parser.parse_args(argv)
    if args.verify_gui_startup:
        from megcfbt.cli import main as cli_main
        cli_output = io.StringIO()
        with contextlib.redirect_stdout(cli_output):
            try:
                cli_main(['--build-info'])
            except SystemExit as error:
                if error.code != 0:
                    raise
        if json.loads(cli_output.getvalue()) != get_build_info():
            raise RuntimeError('Frozen CLI and GUI build identities disagree')
        app=gui.ConverterApp()
        try:
            app.root.withdraw()
            app.root.update_idletasks()
            args.receipt.parent.mkdir(parents=True,exist_ok=True)
            args.receipt.write_text(json.dumps({'state':'complete','app_name':APP_NAME,
                'version':__version__, 'build_info':get_build_info(),
                'version_display':app.version_label.cget('text'),
                'cli_build_info':json.loads(cli_output.getvalue()),
                'frozen':bool(getattr(sys,'frozen',False))},indent=2)+'\n')
            if app.version_label.cget('text') != display_version():
                raise RuntimeError('GUI version disagrees with build metadata')
        finally:
            app.root.destroy()
        return 0
    if args.output_dir is None:
        parser.error('--output-dir is required for conversion verification.')
    source=args.verify_gui_conversion.expanduser().resolve()
    output=args.output_dir.expanduser().resolve()
    receipt=args.receipt.expanduser().resolve()
    if not source.exists() or not output.is_dir():
        parser.error('Source must exist and output-dir must be an existing directory.')
    if source==output or source in output.parents or output in source.parents:
        parser.error('Verification output must be separate from the source.')
    if source==receipt or (source.is_dir() and source in receipt.parents):
        parser.error('Verification receipt must be outside the source.')
    app=gui.ConverterApp()
    app.root.withdraw()
    app.output_dir=output
    state={'state':'inspecting','source':str(source),'output_dir':str(output),
           'frozen':bool(getattr(sys,'frozen',False)),
           'runtime_override':False,'download_progress':[]}
    started=time.monotonic()
    initiated=False
    done=False
    def write():
        state['elapsed_seconds']=round(time.monotonic()-started,1)
        state['log']=app.log_box.get('1.0','end').strip()
        receipt.parent.mkdir(parents=True,exist_ok=True)
        receipt.write_text(json.dumps(state,indent=2)+'\n',encoding='utf-8')
    def stop():
        nonlocal done
        if not done:
            done=True
            write()
            app.root.after_idle(app.root.destroy)
    old_info,old_error=gui.messagebox.showinfo,gui.messagebox.showerror
    old_choice=gui.messagebox.askyesnocancel
    if args.approve_renpy_prerelease_migration:
        def approve_nightly(title,message,*a,**kw):
            if app.inspection and app.inspection.renpy_prerelease_853_candidate and 'nightly' in message:
                state['prerelease_migration_approved']=True
                return True
            return old_choice(title,message,*a,**kw)
        gui.messagebox.askyesnocancel=approve_nightly
    def failed(title,message,*a,**kw):
        state.update(state='failed',error=str(message))
        stop()
    gui.messagebox.showinfo=lambda *a,**kw:None
    gui.messagebox.showerror=failed
    download_progress=app._download_progress
    def progress(received,total):
        state['download_progress'].append([received,total])
        download_progress(received,total)
    app._download_progress=progress
    def poll():
        nonlocal initiated
        if done:return
        if time.monotonic()-started>args.timeout:
            failed('Verification','GUI conversion timed out')
            return
        if app.inspection is not None and not initiated:
            if args.backend_runtime is not None:
                app.backend_runtime = args.backend_runtime.expanduser().resolve()
                state['runtime_override'] = True
            if args.fmod_sdk is not None and app.inspection.backend == 'celesteframe':
                app.celeste_sdk = args.fmod_sdk.expanduser().resolve()
            state['inspection']={'engine':app.inspection.engine,'version':app.inspection.engine_version,
                                 'runtime_kind':app.inspection.runtime_kind,'evidence':app.inspection.evidence}
            state['convert_enabled']=app.convert_btn.cget('state')=='normal'
            state['runtime_button']=app.runtime_button.cget('text')
            state['drop_status']=app.drop_label.cget('text')
            if not app._conversion_allowed() or not state['convert_enabled']:
                failed('Verification','Automatic GUI conversion is unavailable')
                return
            initiated=True
            state['state']='converting'
            # Invoke the same command bound to the actual shipped Convert button.
            app.convert_btn.invoke()
        if app.last_result is not None and not app._busy:
            result=app.last_result
            state.update(state='complete',package=str(result.archive_path),
                         output_path=str(result.output_path),warnings=result.warnings)
            stop()
            return
        write()
        app.root.after(500,poll)
    try:
        # Tk's own list encoding exactly matches the source drop callback contract.
        event=SimpleNamespace(data=app.root.tk.call('list',str(source)))
        app.root.after(100,lambda:app._on_drop(event))
        app.root.after(250,poll)
        app.run()
    finally:
        gui.messagebox.showinfo,gui.messagebox.showerror=old_info,old_error
        gui.messagebox.askyesnocancel=old_choice
    return 0 if state['state']=='complete' else 1
