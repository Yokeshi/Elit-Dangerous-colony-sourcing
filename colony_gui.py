#!/usr/bin/env python3
"""
colony_gui.py  -  Desktop app (EDMC-style grey window) for the colonisation
sourcing tool. Sliders for the parameters, English / Hungarian language switch,
and click-a-result to copy the system name (paste it into ED's route selector).

Must be in the SAME folder as colony_sourcing.py and i18n.py!

Run:
    python3 colony_gui.py

If it complains about missing 'tkinter':
    sudo apt install python3-tk
"""

import os
import re
import sys
import queue
import threading
import subprocess
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import colony_sourcing as cs
    import i18n
    from i18n import t, set_lang
except ImportError as e:
    print("ERROR / HIBA: colony_sourcing.py and/or i18n.py not found next to "
          "this file.")
    print(e)
    sys.exit(1)

try:
    import tkinter as tk
    from tkinter import scrolledtext
except ImportError:
    print("tkinter missing / hianyzik. Install:  sudo apt install python3-tk")
    sys.exit(1)


# --- colours (EDMC-like dark grey) -----------------------------------------
BG = "#2e2e2e"
PANEL = "#383838"
FG = "#e6e6e6"
MUTED = "#9aa0a6"
ACCENT = "#ff7f0e"
TROUGH = "#1f1f1f"
OUT_BG = "#1b1b1b"

LANG_NAMES = {"English": "en", "Magyar": "hu"}
LANG_NAMES_REV = {v: k for k, v in LANG_NAMES.items()}


class QueueWriter:
    def __init__(self, q):
        self.q = q

    def write(self, s):
        if s:
            self.q.put(s)

    def flush(self):
        pass


class App:
    def __init__(self, root):
        self.root = root
        self.q = queue.Queue()
        self.worker = None
        self._i18n = []   # (widget, key) parok az ujraforditashoz

        set_lang(i18n.load_saved_lang())

        self._meta = {}          # var -> (lo, hi, default) az ervek olvasasahoz
        self._vint = root.register(lambda P: P == "" or P.isdigit())

        root.configure(bg=BG)
        root.geometry("900x700")
        root.minsize(720, 540)

        self._build_controls()
        self._build_output()
        self.retranslate()
        self.root.after(100, self._poll)

    # -- widget regisztracio forditashoz ------------------------------------
    def _reg(self, widget, key):
        self._i18n.append((widget, key))
        return widget

    def retranslate(self):
        self.root.title(t("app_title"))
        for w, key in self._i18n:
            try:
                w.config(text=t(key))
            except tk.TclError:
                pass
        self.status.config(text=t("click_hint"))

    # -- vezerlok -----------------------------------------------------------
    def _slider(self, parent, key, frm, to, default, res, row):
        lbl = tk.Label(parent, bg=PANEL, fg=FG, anchor="w")
        lbl.grid(row=row, column=0, sticky="w", padx=(10, 6), pady=2)
        self._reg(lbl, key)

        var = tk.IntVar(value=default)
        self._meta[id(var)] = (frm, to, default)

        cell = tk.Frame(parent, bg=PANEL)
        cell.grid(row=row, column=1, sticky="we", padx=(0, 10), pady=2)
        cell.columnconfigure(0, weight=1)

        # beirhato numerikus mezo (egesz szam) a csuszka felett
        sb = tk.Spinbox(cell, from_=frm, to=to, increment=res, textvariable=var,
                        width=8, justify="center", bg=OUT_BG, fg=FG,
                        insertbackground=FG, relief="flat",
                        buttonbackground=PANEL, highlightthickness=0,
                        validate="key", validatecommand=(self._vint, "%P"))
        sb.grid(row=0, column=0, sticky="w", pady=(0, 1))
        # ervenytelen/ures bevitel javitasa, amikor elhagyod a mezot vagy Entert utsz
        sb.bind("<FocusOut>", lambda e, v=var: self._fix_var(v))
        sb.bind("<Return>", lambda e, v=var: self._fix_var(v))

        s = tk.Scale(cell, from_=frm, to=to, resolution=1, orient="horizontal",
                     variable=var, length=220, bg=PANEL, fg=FG,
                     troughcolor=TROUGH, highlightthickness=0,
                     activebackground=ACCENT, sliderrelief="flat", showvalue=0)
        s.grid(row=1, column=0, sticky="we")
        return var

    def _fix_var(self, var):
        lo, hi, default = self._meta.get(id(var), (0, 0, 0))
        try:
            v = int(var.get())
        except (tk.TclError, ValueError):
            v = default
        var.set(max(lo, min(hi, v)))

    def _val(self, var):
        lo, hi, default = self._meta.get(id(var), (0, 0, 0))
        try:
            v = int(var.get())
        except (tk.TclError, ValueError):
            v = default
        return max(lo, min(hi, v))

    def _build_controls(self):
        panel = tk.Frame(self.root, bg=PANEL)
        panel.pack(fill="x", padx=10, pady=10)
        panel.columnconfigure(1, weight=1)

        left = tk.Frame(panel, bg=PANEL)
        left.grid(row=0, column=0, sticky="nw")
        left.columnconfigure(1, weight=1)
        self.v_dist = self._slider(left, "lbl_maxdist", 10, 500, 100, 10, 0)
        self.v_top = self._slider(left, "lbl_top", 1, 5, 3, 1, 1)
        self.v_days = self._slider(left, "lbl_maxdays", 1, 90, 30, 1, 2)

        right = tk.Frame(panel, bg=PANEL)
        right.grid(row=0, column=1, sticky="nw", padx=(20, 0))
        right.columnconfigure(1, weight=1)
        self.v_supply = self._slider(right, "lbl_minsupply", 0, 20000, 0, 100, 0)
        self.v_jdays = self._slider(right, "lbl_jdays", 0, 365, 120, 15, 1)

        bottom = tk.Frame(panel, bg=PANEL)
        bottom.grid(row=1, column=0, columnspan=2, sticky="we", pady=(8, 4))
        bottom.columnconfigure(1, weight=1)

        self.lbl_refsys = tk.Label(bottom, bg=PANEL, fg=FG)
        self.lbl_refsys.grid(row=0, column=0, sticky="w", padx=10)
        self._reg(self.lbl_refsys, "lbl_refsys")
        self.e_system = tk.Entry(bottom, bg=OUT_BG, fg=FG, insertbackground=FG,
                                 relief="flat")
        self.e_system.grid(row=0, column=1, sticky="we", padx=(0, 10))

        self.v_nocarrier = tk.BooleanVar(value=False)
        cb1 = tk.Checkbutton(bottom, variable=self.v_nocarrier, bg=PANEL, fg=FG,
                             selectcolor=TROUGH, activebackground=PANEL,
                             activeforeground=FG)
        cb1.grid(row=1, column=0, sticky="w", padx=10, pady=(4, 0))
        self._reg(cb1, "chk_nocarrier")

        self.v_plan = tk.BooleanVar(value=True)
        cb2 = tk.Checkbutton(bottom, variable=self.v_plan, bg=PANEL, fg=FG,
                             selectcolor=TROUGH, activebackground=PANEL,
                             activeforeground=FG)
        cb2.grid(row=2, column=0, sticky="w", padx=10, pady=(2, 0))
        self._reg(cb2, "chk_plan")

        btns = tk.Frame(panel, bg=PANEL)
        btns.grid(row=2, column=0, columnspan=2, sticky="w", padx=8, pady=(6, 8))
        self.btn_search = tk.Button(btns, command=self.on_search, bg=ACCENT,
                                    fg="#1b1b1b", relief="flat",
                                    activebackground="#ffa040", padx=18, pady=4,
                                    font=("Sans", 10, "bold"))
        self.btn_search.pack(side="left")
        self._reg(self.btn_search, "btn_search")
        self.btn_clear = tk.Button(btns, command=self.on_clear, bg=PANEL, fg=FG,
                                   relief="flat", activebackground=TROUGH,
                                   padx=12, pady=4)
        self.btn_clear.pack(side="left", padx=8)
        self._reg(self.btn_clear, "btn_clear")

        # nyelvvalaszto (jobbra, jol lathato helyen)
        self.lang_var = tk.StringVar(value=LANG_NAMES_REV.get(i18n.get_lang(),
                                                              "English"))
        om = tk.OptionMenu(btns, self.lang_var, *LANG_NAMES.keys(),
                           command=self._on_lang)
        om.config(bg=ACCENT, fg="#1b1b1b", activebackground="#ffa040",
                  relief="flat", highlightthickness=0, width=8,
                  font=("Sans", 10, "bold"))
        om["menu"].config(bg=PANEL, fg=FG)
        om.pack(side="right", padx=(0, 4))
        self.lbl_lang = tk.Label(btns, bg=PANEL, fg=FG)
        self.lbl_lang.pack(side="right", padx=(8, 6))
        self._reg(self.lbl_lang, "lbl_lang")

        self.status = tk.Label(self.root, bg=BG, fg=MUTED, anchor="w")
        self.status.pack(fill="x", padx=12)

    def _build_output(self):
        self.output = scrolledtext.ScrolledText(
            self.root, bg=OUT_BG, fg=FG, insertbackground=FG,
            font=("DejaVu Sans Mono", 10), relief="flat", wrap="word",
            cursor="hand2")
        self.output.pack(fill="both", expand=True, padx=10, pady=(4, 10))
        self.output.tag_config("local", foreground="#7fe07f")
        self.output.tag_config("head", foreground=ACCENT)
        self.output.tag_config("mat", foreground="#9ec7ff")
        self.output.tag_config("plan", foreground=ACCENT)
        self.output.tag_config("hub", foreground="#5ec8d8")
        self.output.tag_config("warn", foreground="#ff6b6b")
        # bal klikk = rendszer (utvonalhoz), jobb klikk = allomasnev
        self.output.bind("<Button-1>", self._on_click)
        self.output.bind("<Button-3>", self._on_right_click)

    # -- esemenyek ----------------------------------------------------------
    def _on_lang(self, _name):
        lang = LANG_NAMES.get(self.lang_var.get(), "en")
        set_lang(lang)
        i18n.save_lang(lang)
        self.retranslate()

    def _line_at(self, event):
        idx = self.output.index(f"@{event.x},{event.y}")
        line = idx.split(".")[0]
        text = self.output.get(f"{line}.0", f"{line}.end")
        s = text.strip()
        if not s or s[0] in "\u25b8\u26a0":
            return None
        if "MarketID" in s or "PLANNER" in s or "TERVEZ" in s:
            return None
        return text

    def _on_click(self, event):
        text = self._line_at(event)
        if text is None:
            return
        m = re.findall(r"\(([^()]+)\)", text)     # az ELSO zarojeles resz = rendszer
        if not m:
            return
        system = m[0].strip()
        if ":" in system:                          # pl. "(in cargo: 400 t)"
            return
        self._copy(system)

    def _on_right_click(self, event):
        text = self._line_at(event)
        if text is None:
            return
        # az allomasnev a sor elejen van, az elso "(" elott
        pre = text.split("(", 1)[0].strip()
        # vezeto jelek / sorszam levagasa: "✓ ", "1. " stb.
        pre = re.sub(r"^[\u2713\d\.\s]+", "", pre).strip()
        if not pre:
            return
        self._copy(pre)

    def _set_clipboard(self, text):
        # Linux: kulso eszkoz minden masolasnal UJ folyamatkent veszi at a
        # vagolapot -> a Proton/Wine (Elite) kenytelen ujraolvasni.
        if sys.platform.startswith("linux"):
            tools = []
            if os.environ.get("WAYLAND_DISPLAY"):
                tools.append(["wl-copy"])
            tools += [["xclip", "-selection", "clipboard"],
                      ["xsel", "--clipboard", "--input"]]
            for cmd in tools:
                try:
                    subprocess.run(cmd, input=text.encode("utf-8"),
                                   timeout=3, check=True)
                    return "tool"
                except (FileNotFoundError, OSError,
                        subprocess.SubprocessError):
                    continue
        # tartalek: Tkinter sajat vagolapja
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
            self.root.update()
            return "tk"
        except tk.TclError:
            return None

    def _copy(self, value):
        result = self._set_clipboard(value)
        if result is None:
            return
        self._flash_copied(value, fallback=(result == "tk"))

    def _flash_copied(self, system, fallback=False):
        warn = sys.platform.startswith("linux") and fallback
        msg = "✓ " + t("copied", name=system)
        if warn:
            msg += "  " + t("clip_fallback")
        self.status.config(text=msg,
                           fg=("#ffb454" if warn else "#7fe07f"),
                           font=("Sans", 10, "bold"))
        self.root.after(3500 if warn else 2000, lambda: self.status.config(
            text=t("click_hint"), fg=MUTED, font=("Sans", 9, "normal")))

    def on_clear(self):
        self.output.delete("1.0", tk.END)
        self.status.config(text=t("click_hint"))

    def on_search(self):
        if self.worker and self.worker.is_alive():
            return
        args = SimpleNamespace(
            dir=None,
            system=(self.e_system.get().strip() or None),
            days=self._val(self.v_jdays),
            max_distance=self._val(self.v_dist),
            max_days=self._val(self.v_days),
            min_supply=max(1, self._val(self.v_supply)),
            top=self._val(self.v_top),
            no_carriers=self.v_nocarrier.get(),
            plan=self.v_plan.get(),
            debug=False,
        )
        self.output.delete("1.0", tk.END)
        self.status.config(text=t("status_working"))
        self.btn_search.config(state="disabled")
        self.worker = threading.Thread(target=self._run, args=(args,),
                                       daemon=True)
        self.worker.start()

    def _run(self, args):
        old = sys.stdout
        sys.stdout = QueueWriter(self.q)
        try:
            jdir = cs.find_journal_dir(args.dir)
            if not jdir:
                print(t("no_journal_dir"))
                return
            print(t("journal_dir", jdir=jdir))
            files = cs.journal_files(jdir, args.days)
            if not files:
                print(t("no_journal_files"))
                return
            print(t("reading_journals", n=len(files)) + "\n")
            depots, cur, cargo, cap, coords = cs.parse_journal(files)
            markets = cs.load_local_markets(jdir)
            cs.run(depots, cur, cargo, cap, coords, markets, args)
        except Exception as e:  # noqa: BLE001
            print(f"\nERROR / HIBA: {e}")
        finally:
            sys.stdout = old
            self.q.put(("__DONE__",))

    def _poll(self):
        try:
            while True:
                item = self.q.get_nowait()
                if isinstance(item, tuple) and item and item[0] == "__DONE__":
                    self.status.config(text=t("status_done"))
                    self.btn_search.config(state="normal")
                else:
                    self._append(item)
        except queue.Empty:
            pass
        self.root.after(100, self._poll)

    def _append(self, text):
        tag = None
        s = text.lstrip()
        if s.startswith("✓"):
            tag = "local"
        elif s.startswith("▸"):
            tag = "mat"
        elif s.startswith("⚠"):
            tag = "warn"
        elif "PLANNER" in s or "TERVEZ" in s or s.startswith("─"):
            tag = "plan"
        elif s[:2].rstrip(".").isdigit() and "." in s[:4]:
            tag = "hub"
        elif s.startswith("==") or s.startswith("CONSTRUCTION") or s.startswith("EPITKEZES"):
            tag = "head"
        if tag:
            self.output.insert(tk.END, text, tag)
        else:
            self.output.insert(tk.END, text)
        self.output.see(tk.END)


# ---------------------------------------------------------------------------
# ASZTALI INDITO AUTOMATIKUS LETREHOZASA (csendben, hibaturo)
# ---------------------------------------------------------------------------

def _desktop_dirs():
    home = os.path.expanduser("~")
    dirs = []
    try:
        out = subprocess.run(["xdg-user-dir", "DESKTOP"], capture_output=True,
                             text=True, timeout=3)
        p = out.stdout.strip()
        if p and os.path.isdir(p):
            dirs.append(p)
    except Exception:  # noqa: BLE001
        pass
    for name in ("Desktop", "Asztal", "Schreibtisch", "Bureau", "Escritorio"):
        p = os.path.join(home, name)
        if os.path.isdir(p) and p not in dirs:
            dirs.append(p)
    return dirs


def _linux_launcher(script, folder, icon):
    py = sys.executable or "python3"
    icon_val = icon if os.path.isfile(icon) else "input-gaming"
    content = (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Version=1.0\n"
        "Name=Colony Sourcing\n"
        "Comment=ED colonisation sourcing helper\n"
        f"Exec={py} \"{script}\"\n"
        f"Path={folder}\n"
        f"Icon={icon_val}\n"
        "Terminal=false\n"
        "Categories=Game;Utility;\n"
    )

    def _write_if_changed(path):
        try:
            if os.path.isfile(path):
                with open(path, "r", encoding="utf-8") as fh:
                    if fh.read() == content:
                        return False
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(content)
            os.chmod(path, 0o755)
            return True
        except OSError:
            return False

    apps = os.path.join(os.path.expanduser("~"), ".local", "share",
                        "applications")
    try:
        os.makedirs(apps, exist_ok=True)
    except OSError:
        pass
    _write_if_changed(os.path.join(apps, "colony-sourcing.desktop"))

    for desk in _desktop_dirs():
        target = os.path.join(desk, "colony-sourcing.desktop")
        if _write_if_changed(target):
            try:
                subprocess.run(["gio", "set", target, "metadata::trusted",
                               "true"], capture_output=True, timeout=3)
            except Exception:  # noqa: BLE001
                pass
        break


def _windows_launcher(script, folder, icon):
    # best-effort .lnk a Desktopra, kulso fuggoseg nelkul (VBScript)
    try:
        desktop = os.path.join(os.path.expanduser("~"), "Desktop")
        if not os.path.isdir(desktop):
            return
        lnk = os.path.join(desktop, "Colony Sourcing.lnk")
        if os.path.isfile(lnk):
            return
        pyw = sys.executable.replace("python.exe", "pythonw.exe")
        vbs = (
            'Set s = CreateObject("WScript.Shell")\n'
            f'Set lnk = s.CreateShortcut("{lnk}")\n'
            f'lnk.TargetPath = "{pyw}"\n'
            f'lnk.Arguments = """{script}"""\n'
            f'lnk.WorkingDirectory = "{folder}"\n'
            'lnk.Save\n'
        )
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".vbs", delete=False) as f:
            f.write(vbs)
            tmp = f.name
        subprocess.run(["cscript", "//Nologo", tmp], capture_output=True,
                       timeout=10)
        os.unlink(tmp)
    except Exception:  # noqa: BLE001
        pass


def ensure_launcher():
    """Letrehozza/frissiti az asztali indito ikont. Sosem dob hibat."""
    try:
        script = os.path.abspath(__file__)
        folder = os.path.dirname(script)
        icon = os.path.join(folder, "icon.png")
        if sys.platform.startswith("linux"):
            _linux_launcher(script, folder, icon)
        elif sys.platform == "win32":
            _windows_launcher(script, folder, icon)
        # macOS: kihagyjuk (kezi parancsikon)
    except Exception:  # noqa: BLE001
        pass


def main():
    ensure_launcher()
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
