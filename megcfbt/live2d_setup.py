"""Guide the user through the separately licensed Cubism SDK download."""
from pathlib import Path
import webbrowser
import zipfile
from renframe import live2d


class Live2DSdkDialog:
    def __init__(self, app):
        from megcfbt.gui import ctk
        self.app = app
        self.window = ctk.CTkToplevel(app.root)
        self.window.title('Live2D runtime required')
        self.window.geometry('710x400')
        self.window.transient(app.root)
        self.window.grab_set()
        ctk.CTkLabel(self.window, text='Get the Live2D Cubism SDK', font=ctk.CTkFont(size=23, weight='bold')).pack(pady=20)
        ctk.CTkLabel(self.window, wraplength=640, justify='left', text=(
            'This game needs a Linux ARM64 Live2D library that is not included in the standard Ren’Py runtime.\n\n'
            'Open the vendor download page, read and accept its terms yourself, and download the current stable Cubism SDK for Native ZIP. Keep it unextracted in Downloads or select it below.\n\n'
            'The converter validates the ARM64 library, caches it and includes it in your converted copy. It does not redistribute the SDK or accept vendor terms for you.')).pack(padx=20)
        ctk.CTkButton(self.window, text='Open Live2D downloads', command=lambda:webbrowser.open(live2d.DOWNLOAD_URL)).pack(pady=12)
        ctk.CTkButton(self.window, text='Choose downloaded SDK', command=self.choose).pack(pady=8)

    def choose(self):
        from megcfbt.gui import filedialog, messagebox
        selected = filedialog.askopenfilename(parent=self.window, title='Choose Cubism SDK for Native ZIP', filetypes=[('SDK ZIP','*.zip')])
        if not selected:return
        try:
            live2d.import_sdk(Path(selected))
            self.app._log('Validated and cached user-supplied Linux ARM64 Live2D Core. Click Convert to continue.')
            self.window.destroy()
        except (OSError,ValueError,zipfile.BadZipFile) as error:
            messagebox.showerror('Live2D SDK',str(error),parent=self.window)
