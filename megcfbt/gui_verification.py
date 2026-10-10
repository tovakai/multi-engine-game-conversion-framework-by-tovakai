"""Explicit frozen-GUI acceptance runner for automatic conversion workflows.

This exercises the shipped widgets, drop handler and Convert command. It avoids
native modal dialogs so release checks can run on a desktop without focus access.
No runtime, detection, download or builder functions are replaced.
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
import time
from types import SimpleNamespace
from megcfbt import gui


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify-gui-conversion',type=Path,required=True)
    parser.add_argument('--output-dir',type=Path,required=True)
    parser.add_argument('--receipt',type=Path,required=True)
    parser.add_argument('--timeout',type=int,default=900)
    args=parser.parse_args(argv)
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
    return 0 if state['state']=='complete' else 1
