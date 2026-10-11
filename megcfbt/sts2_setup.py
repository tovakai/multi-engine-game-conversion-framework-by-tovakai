"""STS2-specific guided connection/dependency setup; no transport logic in GUI."""

from pathlib import Path
import threading
from megcfbt.sts2_remote import FrameSettings, FrameTransport, RemoteBuild


class FrameSetupDialog:
    def __init__(self,app):
        from megcfbt.gui import ctk,tk,filedialog,messagebox
        self.app=app;self.settings=app.frame_settings;self.entries={};self.probed=False
        self.window=ctk.CTkToplevel(app.root);self.window.title('STS2 • Frame setup (experimental)')
        self.window.geometry('720x660');self.window.transient(app.root)
        ctk.CTkLabel(self.window,text='One-time Steam Frame setup',font=ctk.CTkFont(size=23,weight='bold')).pack(pady=(18,5))
        ctk.CTkLabel(self.window,text='Connect securely, select required dependencies, and choose Frame storage.\nYour original game and Steam settings remain unchanged.',wraplength=650).pack(pady=8)
        fields=(('host','Frame address'),('user','Frame account'),('key_file','Existing connection key (optional)'),
                ('remote_root','Build / deployment folder on Frame'),('sdk_file','FMOD Linux SDK archive on this computer'),
                ('remote_sdk','Or use the verified SDK found on the Frame'))
        for key,label in fields:
            row=ctk.CTkFrame(self.window);row.pack(fill='x',padx=22,pady=5)
            ctk.CTkLabel(row,text=label,width=290,anchor='w').pack(side='left',padx=8)
            entry=ctk.CTkEntry(row);entry.pack(side='left',fill='x',expand=True,padx=6,pady=6)
            entry.insert(0,getattr(self.settings,key));self.entries[key]=entry
            if key in ('sdk_file','key_file'):
                def browse(field=key):
                    path=filedialog.askopenfilename(parent=self.window,title='Choose FMOD SDK archive' if field=='sdk_file' else 'Choose existing private connection key')
                    if path: self.entries[field].delete(0,'end');self.entries[field].insert(0,path)
                ctk.CTkButton(row,text='Browse',width=65,command=browse).pack(side='right',padx=5)
        self.download=tk.BooleanVar(value=self.settings.download_archive)
        ctk.CTkCheckBox(self.window,text='Also download a verified transfer archive to my output folder',variable=self.download).pack(padx=24,pady=4)
        self.status=ctk.CTkLabel(self.window,text='Existing keys and trusted host identities are used automatically.',wraplength=660)
        self.status.pack(pady=12)
        buttons=ctk.CTkFrame(self.window);buttons.pack(fill='x',padx=24,pady=12)
        self.probe_button=ctk.CTkButton(buttons,text='Check connection & requirements',command=self.probe);self.probe_button.pack(side='left',padx=4)
        ctk.CTkButton(buttons,text='Verify new host identity',command=self.trust).pack(side='left',padx=4)
        self.save_button=ctk.CTkButton(buttons,text='Save setup',command=self.save,state='disabled');self.save_button.pack(side='right',padx=4)

    def values(self):
        s=FrameSettings(**{key:entry.get().strip() for key,entry in self.entries.items()})
        s.download_archive=self.download.get();s.validate();return s

    def probe(self):
        from megcfbt.gui import messagebox
        try: settings=self.values()
        except Exception as e: messagebox.showerror('Frame setup',str(e),parent=self.window);return
        self.probe_button.configure(state='disabled');self.status.configure(text='Checking secure connection, storage, compiler and Valve runtimes…')
        def work():
            try:
                result=RemoteBuild(settings).probe()
                def success():
                    if result['sdk_candidates'] and not settings.sdk_file:
                        self.entries['remote_sdk'].delete(0,'end');self.entries['remote_sdk'].insert(0,result['sdk_candidates'][0])
                    self.probed=True;self.save_button.configure(state='normal');self.probe_button.configure(state='normal')
                    self.status.configure(text=f"Frame ready: {result['architecture']} • {result['free_bytes']//1024**3} GiB free • compiler and Valve runtimes verified")
                self.app._dispatch(success)
            except Exception as error:
                text=str(error)
                self.app._dispatch(lambda:self.status.configure(text=text))
                self.app._dispatch(lambda:self.probe_button.configure(state='normal'))
        threading.Thread(target=work,daemon=True).start()

    def trust(self):
        from megcfbt.gui import messagebox
        try: settings=self.values()
        except Exception as e: messagebox.showerror('Frame setup',str(e),parent=self.window);return
        self.status.configure(text='Reading host identity…')
        def work():
            try:
                transport=FrameTransport(settings);fingerprint,line=transport.host_fingerprint()
                def confirm():
                    if messagebox.askyesno('Verify Frame identity',f'Host: {settings.host}\n\n{fingerprint}\n\nConfirm this fingerprint through a trusted source before continuing. Trust this new host?',parent=self.window):
                        try:transport.trust_new_host(line);self.status.configure(text='New host identity saved. Now check the connection.')
                        except Exception as e: self.status.configure(text=str(e))
                self.app._dispatch(confirm)
            except Exception as e:
                text=str(e);self.app._dispatch(lambda:self.status.configure(text=text))
        threading.Thread(target=work,daemon=True).start()

    def save(self):
        from megcfbt.gui import messagebox
        try:
            settings=self.values()
            if not settings.sdk_file and not settings.remote_sdk: raise ValueError('Select the FMOD 2.03.15 Linux SDK archive.')
            settings.save();self.app.frame_settings=settings
            self.app.convert_btn.configure(state='normal' if self.app._conversion_allowed() else 'disabled')
            self.app.runtime_button.configure(text='FRAME SETUP • READY (EXPERIMENTAL)')
            self.window.destroy()
        except Exception as e: messagebox.showerror('Frame setup',str(e),parent=self.window)
