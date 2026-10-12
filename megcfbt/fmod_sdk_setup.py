"""One guided vendor download dialog for supported FMOD-dependent games."""
from pathlib import Path
import webbrowser
from megcfbt.fmod_sdk import FMOD_URL, remember_sdk

def requirement(backend):
    if backend == 'sts2':
        from megcfbt import sts2
        return dict(title='Slay the Spire 2', version='2.03.15', filename=sts2.FMOD_FILENAME,
            attribute='sts2_sdk', discover=sts2.find_sdk, validate=sts2.validate_sdk,
            save=sts2.save_sdk,
            purpose='This game needs FMOD for audio and its native extension.',
            workflow='Windows prepares the transfer package; installation finishes on the Frame.')
    if backend == 'celesteframe':
        from celesteframe import runtime
        return dict(title='Celeste', version='2.03.15', filename=runtime.FMOD_FILENAME,
            attribute='celeste_sdk', discover=runtime.find_fmod_sdk, validate=runtime.validate_fmod_sdk,
            save=None,
            purpose='This game needs FMOD for audio.',
            workflow='After selecting the SDK, press Convert to prepare the complete Frame package.')
    raise ValueError(f'No supported FMOD SDK requirement for {backend}')

class FmodSdkDialog:
    def __init__(self, app, backend):
        from megcfbt.gui import ctk
        self.app = app
        self.requirement = requirement(backend)
        profile = self.requirement
        self.window = ctk.CTkToplevel(app.root)
        self.window.title(profile['title']+': FMOD download')
        self.window.geometry('760x620')
        self.window.minsize(730, 600)
        self.window.transient(app.root)
        self.window.grab_set()
        ctk.CTkLabel(self.window, text='Get the FMOD Linux SDK',
            font=ctk.CTkFont(size=23, weight='bold')).pack(pady=(20, 10))
        text = (profile['purpose']+' FMOD is separately licensed vendor software; '
            'this converter does not include or distribute its SDK. Download it yourself '
            "under FMOD's terms.\n\nSign in at the download page and choose FMOD Engine / "
            'Studio API '+profile['version']+' for Linux (not Windows, and not the Studio editor).\n\n'
            'Keep the archive unextracted: '+profile['filename']+'\n\n'
            'Your Downloads folder is checked automatically. You can select the archive '
            'from another location below; that selection is remembered for other compatible games.')
        ctk.CTkLabel(self.window, text=text, wraplength=670, justify='left').pack(padx=24, pady=8)
        ctk.CTkButton(self.window, text='Open FMOD downloads',
            command=lambda: webbrowser.open(FMOD_URL)).pack(pady=6)
        ctk.CTkLabel(self.window, text=FMOD_URL, wraplength=670).pack(pady=2)
        self.status = ctk.CTkLabel(self.window, text=profile['workflow'], wraplength=670)
        self.status.pack(pady=8)
        row = ctk.CTkFrame(self.window)
        row.pack(pady=10)
        ctk.CTkButton(row, text='Choose downloaded SDK', command=self.choose).pack(side='left', padx=5)
        ctk.CTkButton(row, text='Check download folders', command=self.discover).pack(side='left', padx=5)

    def choose(self):
        from megcfbt.gui import filedialog
        selected = filedialog.askopenfilename(parent=self.window,
            title='Select FMOD Studio API '+self.requirement['version']+' Linux archive',
            filetypes=[('FMOD Linux SDK', '*.tar.gz'), ('All files', '*.*')])
        if selected:
            self.use(Path(selected))

    def discover(self):
        from megcfbt.gui import messagebox
        try:
            path = self.requirement['discover']()
            if path is None:
                self.status.configure(text='SDK not found yet. Download the required Linux archive or select its location.')
            else:
                self.use(path)
        except (OSError, ValueError, RuntimeError) as error:
            messagebox.showerror('FMOD SDK', str(error), parent=self.window)

    def use(self, path):
        from megcfbt.gui import messagebox
        try:
            selected = self.requirement['validate'](Path(path))
            if self.requirement['save'] is not None:
                self.requirement['save'](selected)
            remember_sdk(selected)
            setattr(self.app, self.requirement['attribute'], selected)
            self.app.runtime_button.configure(text='FMOD SDK SELECTED')
            self.app.convert_btn.configure(state='normal' if self.app._conversion_allowed() else 'disabled')
            self.window.destroy()
        except (OSError, ValueError, RuntimeError) as error:
            messagebox.showerror('FMOD SDK', str(error), parent=self.window)
