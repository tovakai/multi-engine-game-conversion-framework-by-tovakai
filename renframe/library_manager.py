"""GUI maintainer app for RenFrame's mod library."""
from __future__ import annotations
import json, subprocess, tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from renframe.mod_library import *

METHODS={"Copy RPA → game/":"copy_rpa_to_game","Merge packaged game/ → game/":"merge_game_directory","Archive contents → game/":"contents_to_game","Overlay archive → game root":"overlay_game_root","Custom operations":"custom"}
TYPES=["patch","walkthrough","utility","qol","translation","adult-patch","uncensor","visual-hd","bugfix","compatibility","content","transformation","accessibility"]
STATUSES=["Active","Maintained","Stale","Archived","Unknown"]

class App:
    def __init__(self):
        self.root=tk.Tk(); self.root.title("RenFrame Library Manager"); self.root.geometry("1180x760"); self.root.minsize(980,650)
        self.kind=tk.StringVar(value="Mods"); self.search=tk.StringVar(); self.current=None; self.package=None
        self.games=[]; self.mods=[]; self.vars={}; self._visible=[]
        top=ttk.Frame(self.root,padding=10); top.pack(fill="x")
        ttk.Label(top,text="RenFrame Library Manager",font=("TkDefaultFont",18,"bold")).pack(side="left")
        self.summary=ttk.Label(top); self.summary.pack(side="left",padx=20)
        ttk.Button(top,text="Validate library",command=self.validate_all).pack(side="right")
        ttk.Button(top,text="Git diff",command=self.git_diff).pack(side="right",padx=6)
        body=ttk.Panedwindow(self.root,orient="horizontal"); body.pack(fill="both",expand=True,padx=10,pady=(0,10))
        left=ttk.Frame(body,padding=8); right=ttk.Frame(body,padding=8); body.add(left,weight=1); body.add(right,weight=3); self.right=right
        sw=ttk.Frame(left); sw.pack(fill="x"); ttk.Radiobutton(sw,text="Mods",variable=self.kind,value="Mods",command=self.refresh).pack(side="left"); ttk.Radiobutton(sw,text="Games",variable=self.kind,value="Games",command=self.refresh).pack(side="left")
        e=ttk.Entry(left,textvariable=self.search); e.pack(fill="x",pady=6); e.bind("<KeyRelease>",lambda _e:self.refresh())
        self.tree=ttk.Treeview(left,show="tree",selectmode="browse"); self.tree.pack(fill="both",expand=True); self.tree.bind("<<TreeviewSelect>>",self.select)
        row=ttk.Frame(left); row.pack(fill="x",pady=(6,0)); ttk.Button(row,text="+ New",command=self.new).pack(side="left"); ttk.Button(row,text="Reload",command=self.reload).pack(side="left",padx=5); ttk.Button(row,text="Delete",command=self.delete).pack(side="right")
        self.status=tk.StringVar(value="Ready"); ttk.Label(self.root,textvariable=self.status,anchor="w").pack(fill="x",padx=12,pady=(0,8))
        self.reload()
    def clear(self):
        for w in self.right.winfo_children(): w.destroy()
        self.vars={}
    def field(self,parent,label,key,value="",width=60):
        ttk.Label(parent,text=label).pack(anchor="w",pady=(7,1)); v=tk.StringVar(value="" if value is None else value); ttk.Entry(parent,textvariable=v,width=width).pack(fill="x"); self.vars[key]=v; return v
    def combo(self,parent,label,key,values,value):
        ttk.Label(parent,text=label).pack(anchor="w",pady=(7,1)); v=tk.StringVar(value=value); ttk.Combobox(parent,textvariable=v,values=values,state="readonly").pack(fill="x"); self.vars[key]=v
    def text(self,parent,label,key,value="",height=5):
        ttk.Label(parent,text=label).pack(anchor="w",pady=(7,1)); t=tk.Text(parent,height=height,wrap="word"); t.pack(fill="x"); t.insert("1.0",value or ""); self.vars[key]=t
    def reload(self):
        try:self.games=load_games(); self.mods=load_mods(); self.summary.config(text=f"{len(self.games)} games · {len(self.mods)} mods"); self.refresh(); self.status.set("Library loaded")
        except Exception as e:messagebox.showerror("RenFrame",str(e))
    def refresh(self):
        self.tree.delete(*self.tree.get_children()); records=self.mods if self.kind.get()=="Mods" else self.games; needle=self.search.get().lower().strip(); names={g["id"]:g["name"] for g in self.games}
        self._visible=[r for r in records if not needle or needle in json.dumps(r,ensure_ascii=False).lower()]
        for i,r in enumerate(self._visible):
            if self.kind.get()=="Mods": sub="Universal" if r.get("scope")=="universal" else names.get(r.get("game_id"),r.get("game_id","?")); label=f"{r.get('name')}\n{sub} · {r.get('type','mod')}"
            else: label=f"{r.get('name')}\n{sum(m.get('game_id')==r.get('id') for m in self.mods)} mods"
            self.tree.insert("","end",iid=str(i),text=label,values=(i,))
        self.clear(); ttk.Label(self.right,text=f"Select or add a {self.kind.get()[:-1].lower()}.",font=("TkDefaultFont",14,"bold")).pack(anchor="w")
    def select(self,_e=None):
        sel=self.tree.selection();
        if not sel:return
        idx=int(sel[0])
        if idx>=len(self._visible):return
        self.current=self._visible[idx]; self.render(self.current)
    def new(self): self.current=None; self.package=None; self.render({})
    def render(self,r):
        self.clear(); title="Mod" if self.kind.get()=="Mods" else "Game"; ttk.Label(self.right,text=r.get("name") or f"New {title.lower()}",font=("TkDefaultFont",16,"bold")).pack(anchor="w")
        if title=="Game": self.render_game(r)
        else:self.render_mod(r)
    def render_game(self,r):
        self.field(self.right,"Game name","name",r.get("name","")); self.field(self.right,"Game ID","id",r.get("id","")); self.field(self.right,"Ren'Py version","renpy",r.get("renpy_version","")); self.text(self.right,"Aliases (comma/newline separated)","aliases","\n".join(r.get("aliases",[]) or []),3); self.text(self.right,"Fingerprint JSON","fingerprint",json.dumps(r.get("fingerprint",{}),indent=2),8); self.text(self.right,"Notes","notes",r.get("notes",""),4)
        row=ttk.Frame(self.right); row.pack(fill="x",pady=10); ttk.Button(row,text="Inspect clean game folder…",command=self.inspect_game).pack(side="left"); ttk.Button(row,text="Update game",command=self.save).pack(side="right")
    def render_mod(self,r):
        choices=["Universal Ren'Py"]+[f"{g['name']} [{g['id']}]" for g in self.games]; game="Universal Ren'Py" if r.get("scope")=="universal" else next((x for x in choices if x.endswith(f"[{r.get('game_id')}]") ),choices[0]); self.combo(self.right,"Game","game",choices,game)
        ttk.Button(self.right,text="+ Add new game",command=self.add_game_from_mod).pack(anchor="e",pady=(3,0))
        self.field(self.right,"Mod name","name",r.get("name","")); self.field(self.right,"Mod ID","id",r.get("id","")); self.field(self.right,"Version","version",r.get("version","")); self.combo(self.right,"Type","type",TYPES,r.get("type","patch") if r.get("type") in TYPES else "patch"); self.combo(self.right,"Status","status",STATUSES,r.get("maintenance_status","Unknown") if r.get("maintenance_status") in STATUSES else "Unknown")
        flags=ttk.Frame(self.right); flags.pack(fill="x",pady=5); self.vars["adult"]=tk.BooleanVar(value=bool(r.get("adult"))); self.vars["runtime"]=tk.BooleanVar(value=bool(r.get("runtime_sensitive"))); ttk.Checkbutton(flags,text="Adult / NSFW",variable=self.vars["adult"]).pack(side="left"); ttk.Checkbutton(flags,text="Runtime-sensitive",variable=self.vars["runtime"]).pack(side="left",padx=12)
        self.field(self.right,"Source/project page","source",(r.get("source") or {}).get("page_url","")); self.field(self.right,"Direct download/release URL","download",(r.get("artifact") or {}).get("download_url",""))
        pkg=ttk.Frame(self.right); pkg.pack(fill="x",pady=(8,0)); self.vars["package"]=tk.StringVar(); ttk.Entry(pkg,textvariable=self.vars["package"]).pack(side="left",fill="x",expand=True); ttk.Button(pkg,text="Browse package…",command=self.browse_package).pack(side="left",padx=5); ttk.Button(pkg,text="Inspect",command=self.inspect_local).pack(side="left")
        method=self.method_from(r); self.combo(self.right,"Install method","method",list(METHODS),next((k for k,v in METHODS.items() if v==method),"Custom operations")); self.text(self.right,"Install operations JSON","ops",json.dumps(r.get("install",[]),indent=2),7); self.field(self.right,"Conflicts (comma-separated)","conflicts",", ".join(r.get("conflicts",[]) or [])); self.text(self.right,"Notes","notes",r.get("notes",""),4)
        self.package_label=ttk.Label(self.right,text=""); self.package_label.pack(anchor="w",pady=4); ttk.Button(self.right,text="Update library",command=self.save).pack(anchor="e",pady=8)
    def method_from(self,r):
        ops=r.get("install") or []
        if len(ops)!=1:return "custom"
        o=ops[0]
        if o.get("op")=="copy_file" and str(o.get("destination","")).startswith("game/"):return "copy_rpa_to_game"
        if o.get("op")=="copy_tree" and o.get("source")=="game":return "merge_game_directory"
        if o.get("op")=="overlay_archive" and o.get("destination")=="game":return "contents_to_game"
        if o.get("op")=="overlay_archive" and o.get("destination")==".":return "overlay_game_root"
        return "custom"
    def add_game_from_mod(self):
        self.kind.set("Games"); self.refresh(); self.new()
    def browse_package(self):
        p=filedialog.askopenfilename(title="Choose mod package") or filedialog.askdirectory(title="Choose extracted mod folder")
        if p:self.vars["package"].set(p); self.inspect_local()
    def inspect_local(self):
        try:
            self.package=inspect_package(self.vars["package"].get())
            if self.package["unsafe_entries"]: raise LibraryError("Unsafe archive paths: " + ", ".join(self.package["unsafe_entries"][:5]))
            self.vars["runtime"].set(bool(self.package["runtime_sensitive"])); label=next((k for k,v in METHODS.items() if v==self.package["suggested_method"]),"Custom operations"); self.vars["method"].set(label); self.vars["ops"].delete("1.0","end"); self.vars["ops"].insert("1.0",json.dumps(self.package["suggested_operations"],indent=2)); self.package_label.config(text=f"{self.package['kind']} · {self.package['file_count']} files · SHA-256 {self.package.get('sha256') or 'n/a'}" + (f" · {len(self.package['executable_entries'])} executable/script entries" if self.package["executable_entries"] else ""))
        except Exception as e:messagebox.showerror("Inspect package",str(e))
    def inspect_game(self):
        p=filedialog.askdirectory(title="Select clean Ren'Py game")
        if not p:return
        try:
            x=fingerprint_game(p)
            if not self.vars["name"].get() and x.get("name"):self.vars["name"].set(x["name"])
            if not self.vars["renpy"].get() and x.get("renpy_version"):self.vars["renpy"].set(x["renpy_version"])
            t=self.vars["fingerprint"]; t.delete("1.0","end"); t.insert("1.0",json.dumps(x["fingerprint"],indent=2))
        except Exception as e:messagebox.showerror("Inspect game",str(e))
    def collect(self):
        if self.kind.get()=="Games":
            aliases=[x.strip() for line in self.vars["aliases"].get("1.0","end").splitlines() for x in line.split(",") if x.strip()]; fp=json.loads(self.vars["fingerprint"].get("1.0","end").strip() or "{}"); return {"schema_version":1,"id":self.vars["id"].get().strip() or slugify(self.vars["name"].get()),"name":self.vars["name"].get().strip(),"engine":"renpy","aliases":aliases,"renpy_version":self.vars["renpy"].get().strip() or None,"fingerprint":fp,"notes":self.vars["notes"].get("1.0","end").strip()}
        game=self.vars["game"].get(); scope="universal" if game=="Universal Ren'Py" else "game"; gid=None if scope=="universal" else game.rsplit("[",1)[1][:-1]; ops=json.loads(self.vars["ops"].get("1.0","end").strip() or "[]"); art={"download_url":self.vars["download"].get().strip() or None};
        if self.package and self.package.get("sha256"):art["sha256"]=self.package["sha256"]; art["observed_filename"]=Path(self.package["path"]).name
        return {"schema_version":1,"id":self.vars["id"].get().strip() or slugify(self.vars["name"].get()),"name":self.vars["name"].get().strip(),"scope":scope,"game_id":gid,"type":self.vars["type"].get(),"adult":bool(self.vars["adult"].get()),"version":self.vars["version"].get().strip() or None,"maintenance_status":self.vars["status"].get(),"runtime_sensitive":bool(self.vars["runtime"].get()),"source":{"page_url":self.vars["source"].get().strip() or None},"artifact":art,"install_method":METHODS[self.vars["method"].get()],"install":ops,"conflicts":[x.strip() for x in self.vars["conflicts"].get().split(",") if x.strip()],"notes":self.vars["notes"].get("1.0","end").strip()}
    def save(self):
        try:
            r=self.collect(); old=Path(self.current["_path"]) if self.current and self.current.get("_path") else None; p=save_game(r) if self.kind.get()=="Games" else save_mod(r)
            if old and old!=p:old.unlink(missing_ok=True)
            errs=validate_library()
            if errs:raise LibraryError("\n".join(errs))
            write_index(); self.reload(); self.status.set(f"Updated {p.relative_to(repo_root())}")
        except Exception as e:messagebox.showerror("Update library",str(e))
    def delete(self):
        if not self.current:return
        if self.kind.get()=="Games" and any(m.get("game_id")==self.current.get("id") for m in self.mods):messagebox.showerror("Delete","Mods still reference this game.");return
        if messagebox.askyesno("Delete",f"Delete {self.current.get('name')} from the library?"):delete_record(self.current); write_index(); self.current=None; self.reload()
    def validate_all(self):
        try:
            e=validate_library(); write_index()
            if e:messagebox.showerror("Validation","\n".join(e[:30]))
            else:messagebox.showinfo("Validation",f"Library valid.\n{len(self.games)} games · {len(self.mods)} mods")
        except Exception as x:messagebox.showerror("Validation",str(x))
    def git_diff(self):
        try:a=subprocess.run(["git","status","--short","--","mod_library"],cwd=repo_root(),text=True,capture_output=True).stdout; b=subprocess.run(["git","diff","--","mod_library"],cwd=repo_root(),text=True,capture_output=True).stdout; text=(a+"\n"+b).strip() or "No uncommitted mod_library changes."
        except Exception as e:text=str(e)
        w=tk.Toplevel(self.root); w.title("mod_library git diff"); w.geometry("900x620"); t=tk.Text(w,wrap="none"); t.pack(fill="both",expand=True); t.insert("1.0",text); t.config(state="disabled")
    def run(self):self.root.mainloop()

def main():App().run()
if __name__=="__main__":main()
