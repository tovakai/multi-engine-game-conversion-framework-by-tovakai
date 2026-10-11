"""Guide users to obtain their own FMOD SDK for the two-stage STS2 workflow."""

from pathlib import Path
import webbrowser
from megcfbt import sts2


class Sts2SdkDialog:
    def __init__(self, app):
        from megcfbt.gui import ctk
        self.app = app
        self.window = ctk.CTkToplevel(app.root)
        self.window.title('Slay the Spire 2: FMOD download')
        self.window.geometry('760x620')
        self.window.minsize(730, 600)
        self.window.transient(app.root)
        self.window.grab_set()
        ctk.CTkLabel(self.window, text='Get the FMOD Linux SDK',
                     font=ctk.CTkFont(size=23, weight='bold')).pack(pady=(20, 10))
        text = ('STS2 needs FMOD for audio and for building its native extension. '
                'FMOD is separately licensed vendor software; this converter does not '
                'include or distribute its SDK. Download it yourself under FMOD\'s terms.\n\n'
                'Sign in at the download page and choose FMOD Engine / Studio API '
                '2.03.15 for Linux (not Windows, and not the Studio editor).\n\n'
                'Keep the archive unextracted and place ' + sts2.FMOD_FILENAME + ' here:\n'
                + str(sts2.sdk_directory()) + '\n\n'
                'Your Downloads folder is also checked automatically. '
                'You can select the archive from another location below.')
        ctk.CTkLabel(self.window, text=text, wraplength=670, justify='left').pack(padx=24, pady=8)
        ctk.CTkButton(self.window, text='Open FMOD downloads',
                      command=lambda: webbrowser.open(sts2.FMOD_URL)).pack(pady=6)
        ctk.CTkLabel(self.window, text=sts2.FMOD_URL, wraplength=670).pack(pady=2)
        self.status = ctk.CTkLabel(self.window, text='Windows prepares the transfer package; installation finishes on the Frame.', wraplength=670)
        self.status.pack(pady=8)
        row = ctk.CTkFrame(self.window)
        row.pack(pady=10)
        ctk.CTkButton(row, text='Choose downloaded SDK', command=self.choose).pack(side='left', padx=5)
        ctk.CTkButton(row, text='Check download folders', command=self.discover).pack(side='left', padx=5)

    def choose(self):
        from megcfbt.gui import filedialog
        selected = filedialog.askopenfilename(parent=self.window, title='Select FMOD Studio API 2.03.15 Linux archive',
            filetypes=[('FMOD Linux SDK', '*.tar.gz'), ('All files', '*.*')])
        if selected:
            self.use(Path(selected))

    def discover(self):
        path = sts2.find_sdk()
        if path is None:
            self.status.configure(text='SDK not found yet. Download the required Linux archive or select its location.')
        else:
            self.use(path)

    def use(self, path):
        from megcfbt.gui import messagebox
        try:
            if not path.is_file():
                raise ValueError('Select the downloaded SDK archive.')
            sts2.save_sdk(path)
            self.app.sts2_sdk = path
            self.app.runtime_button.configure(text='FMOD SDK SELECTED')
            self.app.convert_btn.configure(state='normal' if self.app._conversion_allowed() else 'disabled')
            self.window.destroy()
        except (OSError, ValueError) as error:
            messagebox.showerror('FMOD SDK', str(error), parent=self.window)
