r"""
codetool.py - extract, format and output values from a list.

    0000000000-UC01      ->  0000000000
    ABC123  Some Name    ->  ABC123

GUI
    Double-click the file, or run:  python codetool.py
    Tip: rename to codetool.pyw to open without a console window.
    Shortcuts: Ctrl+O open file, Ctrl+Enter copy output, Ctrl+S save output.
    Settings are remembered between sessions (~/.codetool.json). Input text is never saved.

COMMAND LINE (same engine)
    python codetool.py stus.txt                                 # 1st whitespace column, to screen
    python codetool.py stus.txt -d - --digits                   # 0000000000-UC01 -> 0000000000
    python codetool.py stus.txt -d middot -p 1                  # part after the middle dot
    python codetool.py stus.txt --preset sits --out clip        # A·|B·|C  -> clipboard
    python codetool.py stus.txt --preset sql -o codes.txt       # 'A',\n'B'  -> file
    python codetool.py stus.txt --preset sql-in                 # ('A', 'B', 'C')

EXTRACTION
    -d / --delimiter   default whitespace. Literal ("-", "|" - quote it in cmd), a name
                       (middot, pipe, tab, space, comma, semicolon, dash, underscore,
                       colon, slash, bullet, dot) or a code (U+00B7, \u00b7, 0xB7)
    -p / --part        0 = first piece (default), 1 = second, -1 = last
    --digits           keep digits only
    --regex            regex instead of delimiter/part; first capture group is used
    --unique / --sort  drop duplicates (keeps order) / sort A-Z

FORMATTING
    --prefix / --suffix / --quote    added to each value
    --join             text between values (default newline). Supports \n \t \uXXXX
    --trailing         also put the join text after the last value
    --wrap OPEN CLOSE  text around the whole result, e.g. "(" ")"
    --preset           lines | sits (A·|B) | sql ('A',\n'B') | sql-in (('A', 'B')) | csv (A,B)

OUTPUT
    --out screen|file|clip, -o FILE, --out-encoding cp1252 (default utf-8),
    --encoding to force the input encoding (utf-8, cp1252, utf-16)
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

try:
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox
except ImportError:  # CLI still works without tkinter
    tk = None

NAMED = {
    "pipe": "|", "dot": ".", "middot": "\u00b7", "bullet": "\u2022", "tab": "\t",
    "space": " ", "comma": ",", "semicolon": ";", "dash": "-", "underscore": "_",
    "colon": ":", "slash": "/",
}

DEFAULT_FMT = dict(prefix="", suffix="", quote="", join="\n", trailing=False, wrap=("", ""))
PRESETS = {
    "lines":  {},
    "sits":   dict(join="\u00b7|"),
    "sql":    dict(quote="'", join=",\n"),
    "sql-in": dict(quote="'", join=", ", wrap=("(", ")")),
    "csv":    dict(join=","),
}


# ======================================================================
# Engine
# ======================================================================

def preset_fmt(name):
    fmt = dict(DEFAULT_FMT)
    fmt.update(PRESETS.get(name, {}))
    return fmt


def unescape(text):
    """\\n, \\t, \\uXXXX -> real characters (leaves the middle dot etc. alone)."""
    if not text:
        return text or ""
    text = re.sub(r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m.group(1), 16)), text)
    return text.replace("\\n", "\n").replace("\\t", "\t")


def escape(text):
    """Real newlines/tabs -> \\n, \\t for display in an entry box."""
    return (text or "").replace("\n", "\\n").replace("\t", "\\t")


def parse_delimiter(text):
    if text is None or text.strip().lower() in ("", "ws", "whitespace"):
        return None  # None = split on any whitespace
    key = text.strip().lower()
    if key in NAMED:
        return NAMED[key]
    m = re.fullmatch(r"(?:u\+|\\u|0x)([0-9a-f]{2,6})", key)
    if m:
        return chr(int(m.group(1), 16))
    return unescape(text)


def read_text(path, encoding=None):
    """UTF-8 (with/without BOM), UTF-16, else Windows-1252 ('ANSI')."""
    with open(path, "rb") as f:
        data = f.read()
    if encoding:
        return data.decode(encoding)
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16")
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("cp1252")


def extract(lines, delimiter=None, part=0, digits=False, regex=None, unique=False, sort=False):
    pattern = re.compile(regex) if regex else None
    out = []
    for raw in lines:
        line = raw.strip()
        line = re.sub(r"^[-*\u2022]\s+", "", line)  # drop list bullets like "- "
        if not line:
            continue
        if pattern:
            m = pattern.search(line)
            value = (m.group(1) if m.groups() else m.group(0)) if m else ""
        else:
            pieces = line.split(delimiter) if delimiter is not None else line.split()
            value = pieces[part] if -len(pieces) <= part < len(pieces) else ""
        value = value.strip()
        if digits:
            value = re.sub(r"\D", "", value)
        if value:
            out.append(value)
    if unique:
        out = list(dict.fromkeys(out))
    if sort:
        out.sort()
    return out


def format_values(values, prefix="", suffix="", quote="", join="\n", trailing=False, wrap=("", "")):
    items = [f"{quote}{prefix}{v}{suffix}{quote}" for v in values]
    body = join.join(items) + (join if trailing and items else "")
    return f"{wrap[0]}{body}{wrap[1]}"


def copy_to_clipboard(text):
    if sys.platform.startswith("win"):
        subprocess.run(["clip.exe"], input=text.encode("utf-16"), check=True)
        return
    try:
        import pyperclip
        pyperclip.copy(text)
    except ImportError:
        r = tk.Tk()
        r.withdraw()
        r.clipboard_clear()
        r.clipboard_append(text)
        r.update()
        r.destroy()


# ======================================================================
# GUI
# ======================================================================

SETTINGS_FILE = Path.home() / ".codetool.json"
DELIM_CHOICES = ["whitespace", "-", "|", "\u00b7", "tab", ",", ";", "_", ":", "/", "space"]
FORMAT_FIELDS = ("quote", "prefix", "suffix", "join", "wrap_open", "wrap_close", "trailing")


class App:
    def __init__(self, root):
        self.root = root
        root.title("CodeTool")
        root.geometry("1180x660")
        root.minsize(960, 520)
        self._after = None
        self._applying_preset = False
        self._count = 0
        self._last_dir = ""

        S, B = tk.StringVar, tk.BooleanVar
        self.v = {
            "delimiter": S(value="whitespace"), "part": S(value="0"), "regex": S(),
            "digits": B(), "unique": B(), "sort": B(),
            "preset": S(value="lines"), "quote": S(), "prefix": S(), "suffix": S(),
            "join": S(value="\\n"), "wrap_open": S(), "wrap_close": S(), "trailing": B(),
            "encoding": S(value="utf-8"),
        }
        self.status = S(value="Paste or open a list to start.")
        self.counts = S(value="")

        self._build()
        self._load_settings()
        for name, var in self.v.items():
            var.trace_add("write", lambda *_, n=name: self._changed(n))

        self._shortcut("<Control-Return>", self.copy)
        self._shortcut("<Control-s>", self.save)
        self._shortcut("<Control-S>", self.save)
        self._shortcut("<Control-o>", self.open_file)
        self._shortcut("<Control-O>", self.open_file)
        for w in (self.inp, self.out):
            w.bind("<Control-a>", lambda e, w=w: self._select_all(w))
            w.bind("<Control-A>", lambda e, w=w: self._select_all(w))
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.inp.focus_set()
        self.refresh()

    # ---------- layout ----------
    def _build(self):
        r = self.root
        win = sys.platform.startswith("win")
        mono = ("Consolas", 10) if win else ("DejaVu Sans Mono", 10)
        bold = ("Segoe UI", 10, "bold") if win else ("TkDefaultFont", 10, "bold")

        r.columnconfigure(0, weight=1)
        r.columnconfigure(2, weight=1)
        r.rowconfigure(0, weight=1)

        # Input pane
        fin = ttk.Frame(r, padding=(10, 10, 5, 4))
        fin.grid(row=0, column=0, sticky="nsew")
        fin.columnconfigure(0, weight=1)
        fin.rowconfigure(1, weight=1)
        bar = ttk.Frame(fin)
        bar.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        ttk.Label(bar, text="Input", font=bold).pack(side="left")
        ttk.Button(bar, text="Clear", width=7, command=self.clear_input).pack(side="right")
        ttk.Button(bar, text="Paste", width=7, command=self.paste_input).pack(side="right", padx=4)
        ttk.Button(bar, text="Open file\u2026", command=self.open_file).pack(side="right")
        self.inp = self._text(fin, mono)
        self.inp.bind("<<Modified>>", self._on_input_modified)

        # Options pane
        opt = ttk.Frame(r, padding=(5, 10, 5, 4))
        opt.grid(row=0, column=1, sticky="ns")

        ex = ttk.LabelFrame(opt, text=" 1. Extract ", padding=8)
        ex.pack(fill="x")
        self._row(ex, 0, "Delimiter", ttk.Combobox(ex, textvariable=self.v["delimiter"],
                                                   values=DELIM_CHOICES, width=14))
        pf = ttk.Frame(ex)
        ttk.Spinbox(pf, from_=-20, to=50, textvariable=self.v["part"], width=5).pack(side="left")
        ttk.Label(pf, text="  0 = first, -1 = last", foreground="grey").pack(side="left")
        self._row(ex, 1, "Part", pf)
        self._row(ex, 2, "Regex", ttk.Entry(ex, textvariable=self.v["regex"], width=17))
        ttk.Label(ex, text="(overrides delimiter/part)", foreground="grey").grid(
            row=3, column=1, sticky="w")
        ck = ttk.Frame(ex)
        ck.grid(row=4, column=0, columnspan=2, sticky="w", pady=(6, 0))
        ttk.Checkbutton(ck, text="Digits only", variable=self.v["digits"]).pack(anchor="w")
        ttk.Checkbutton(ck, text="Remove duplicates", variable=self.v["unique"]).pack(anchor="w")
        ttk.Checkbutton(ck, text="Sort A\u2013Z", variable=self.v["sort"]).pack(anchor="w")

        fm = ttk.LabelFrame(opt, text=" 2. Format ", padding=8)
        fm.pack(fill="x", pady=8)
        pc = ttk.Combobox(fm, textvariable=self.v["preset"], state="readonly", width=14,
                          values=list(PRESETS) + ["custom"])
        pc.bind("<<ComboboxSelected>>", lambda e: self.apply_preset(self.v["preset"].get()))
        self._row(fm, 0, "Preset", pc)
        self._row(fm, 1, "Quote", ttk.Entry(fm, textvariable=self.v["quote"], width=17))
        self._row(fm, 2, "Prefix", ttk.Entry(fm, textvariable=self.v["prefix"], width=17))
        self._row(fm, 3, "Suffix", ttk.Entry(fm, textvariable=self.v["suffix"], width=17))
        jf = ttk.Frame(fm)
        join_entry = ttk.Entry(jf, textvariable=self.v["join"], width=13)
        join_entry.pack(side="left")

        def add_middot():
            join_entry.insert("insert", "\u00b7")
            join_entry.focus_set()

        ttk.Button(jf, text="\u00b7", width=3, command=add_middot).pack(side="left", padx=(4, 0))
        self._row(fm, 4, "Join", jf)
        ttk.Label(fm, text="\\n = new line, \\t = tab", foreground="grey").grid(
            row=5, column=1, sticky="w")
        wf = ttk.Frame(fm)
        ttk.Entry(wf, textvariable=self.v["wrap_open"], width=7).pack(side="left")
        ttk.Label(wf, text=" \u2026 ").pack(side="left")
        ttk.Entry(wf, textvariable=self.v["wrap_close"], width=7).pack(side="left")
        self._row(fm, 6, "Wrap", wf)
        ttk.Checkbutton(fm, text="Join after last value too", variable=self.v["trailing"]).grid(
            row=7, column=0, columnspan=2, sticky="w", pady=(6, 0))

        ou = ttk.LabelFrame(opt, text=" 3. Output ", padding=8)
        ou.pack(fill="x")
        ttk.Button(ou, text="Copy output   (Ctrl+Enter)", command=self.copy).grid(
            row=0, column=0, columnspan=2, sticky="ew", ipady=4)
        ttk.Button(ou, text="Save as\u2026   (Ctrl+S)", command=self.save).grid(
            row=1, column=0, columnspan=2, sticky="ew", pady=(4, 6))
        self._row(ou, 2, "File encoding", ttk.Combobox(
            ou, textvariable=self.v["encoding"], values=["utf-8", "cp1252"],
            state="readonly", width=9))

        # Output pane
        fout = ttk.Frame(r, padding=(5, 10, 10, 4))
        fout.grid(row=0, column=2, sticky="nsew")
        fout.columnconfigure(0, weight=1)
        fout.rowconfigure(1, weight=1)
        bar2 = ttk.Frame(fout)
        bar2.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        ttk.Label(bar2, text="Output", font=bold).pack(side="left")
        ttk.Label(bar2, textvariable=self.counts, foreground="grey").pack(side="right")
        self.out = self._text(fout, mono)

        # Status bar
        self.status_lbl = ttk.Label(r, textvariable=self.status, padding=(10, 2, 10, 6))
        self.status_lbl.grid(row=1, column=0, columnspan=3, sticky="ew")

    def _text(self, parent, font):
        f = ttk.Frame(parent)
        f.grid(row=1, column=0, sticky="nsew")
        f.columnconfigure(0, weight=1)
        f.rowconfigure(0, weight=1)
        t = tk.Text(f, wrap="none", undo=True, font=font, width=40, height=20,
                    relief="solid", borderwidth=1)
        ys = ttk.Scrollbar(f, orient="vertical", command=t.yview)
        xs = ttk.Scrollbar(f, orient="horizontal", command=t.xview)
        t.configure(yscrollcommand=ys.set, xscrollcommand=xs.set)
        t.grid(row=0, column=0, sticky="nsew")
        ys.grid(row=0, column=1, sticky="ns")
        xs.grid(row=1, column=0, sticky="ew")
        return t

    @staticmethod
    def _row(parent, row, label, widget):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=(0, 8), pady=2)
        widget.grid(row=row, column=1, sticky="w", pady=2)

    def _shortcut(self, seq, fn):
        handler = lambda e: (fn(), "break")[1]
        self.root.bind(seq, handler)
        for w in (self.inp, self.out):
            w.bind(seq, handler)  # stops the text box inserting a newline etc.

    @staticmethod
    def _select_all(w):
        w.tag_add("sel", "1.0", "end-1c")
        return "break"

    # ---------- behaviour ----------
    def _changed(self, name):
        if name in FORMAT_FIELDS and not self._applying_preset:
            if self.v["preset"].get() != "custom":
                self.v["preset"].set("custom")
        self._schedule()

    def _on_input_modified(self, _):
        if self.inp.edit_modified():
            self.inp.edit_modified(False)
            self._schedule()

    def _schedule(self):
        if self._after:
            self.root.after_cancel(self._after)
        self._after = self.root.after(150, self.refresh)

    def apply_preset(self, name):
        if name not in PRESETS:
            return
        f = preset_fmt(name)
        self._applying_preset = True
        try:
            for key in ("quote", "prefix", "suffix", "join"):
                self.v[key].set(escape(f[key]))
            self.v["wrap_open"].set(f["wrap"][0])
            self.v["wrap_close"].set(f["wrap"][1])
            self.v["trailing"].set(f["trailing"])
        finally:
            self._applying_preset = False
        self._schedule()

    def refresh(self):
        self._after = None
        g = lambda k: self.v[k].get()
        lines = self.inp.get("1.0", "end-1c").splitlines()
        try:
            part = int(g("part"))
        except ValueError:
            part = 0
        try:
            values = extract(lines, parse_delimiter(g("delimiter")), part, g("digits"),
                             g("regex") or None, g("unique"), g("sort"))
        except re.error as e:
            self._set_output("")
            self.counts.set("")
            self._msg(f"Regex error: {e}", error=True)
            return
        result = format_values(
            values, prefix=unescape(g("prefix")), suffix=unescape(g("suffix")),
            quote=unescape(g("quote")), join=unescape(g("join")), trailing=g("trailing"),
            wrap=(unescape(g("wrap_open")), unescape(g("wrap_close"))))
        self._set_output(result)
        self._count = len(values)
        n_in = sum(1 for l in lines if l.strip())
        self.counts.set(f"{n_in} lines in  \u2192  {len(values)} values out" if n_in else "")
        if self.status_lbl.cget("foreground") == "red":
            self._msg("")

    def _set_output(self, text):
        self.out.delete("1.0", "end")
        self.out.insert("1.0", text)

    def _msg(self, text, error=False):
        self.status.set(text)
        self.status_lbl.configure(foreground="red" if error else "")

    def _set_input(self, text):
        self.inp.delete("1.0", "end")
        self.inp.insert("1.0", text)
        self.inp.edit_modified(True)

    def copy(self):
        text = self.out.get("1.0", "end-1c")
        if not text:
            self._msg("Nothing to copy.", error=True)
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.root.update()
        self._msg(f"Copied {self._count} values to clipboard.")

    def save(self):
        text = self.out.get("1.0", "end-1c")
        if not text:
            self._msg("Nothing to save.", error=True)
            return
        path = filedialog.asksaveasfilename(
            parent=self.root, initialdir=self._last_dir or None, initialfile="output.txt",
            defaultextension=".txt",
            filetypes=[("Text", "*.txt"), ("SQL", "*.sql"), ("CSV", "*.csv"), ("All files", "*.*")])
        if not path:
            return
        enc = self.v["encoding"].get()
        try:
            with open(path, "w", encoding=enc) as f:
                f.write(text)
        except UnicodeEncodeError:
            messagebox.showerror("CodeTool", f"Some characters can't be saved as {enc}.\n"
                                             "Switch File encoding to utf-8.", parent=self.root)
            return
        except OSError as e:
            messagebox.showerror("CodeTool", str(e), parent=self.root)
            return
        self._last_dir = str(Path(path).parent)
        self._msg(f"Saved {self._count} values to {path} ({enc}).")

    def open_file(self):
        path = filedialog.askopenfilename(
            parent=self.root, initialdir=self._last_dir or None,
            filetypes=[("Text files", "*.txt *.csv *.sql *.dat"), ("All files", "*.*")])
        if not path:
            return
        try:
            text = read_text(path)
        except (OSError, UnicodeDecodeError) as e:
            messagebox.showerror("CodeTool", str(e), parent=self.root)
            return
        self._last_dir = str(Path(path).parent)
        self._set_input(text)
        self._msg(f"Loaded {Path(path).name}")

    def paste_input(self):
        try:
            text = self.root.clipboard_get()
        except tk.TclError:
            self._msg("Clipboard is empty.", error=True)
            return
        self._set_input(text)
        self._msg("Pasted from clipboard.")

    def clear_input(self):
        self._set_input("")
        self._msg("")

    # ---------- settings ----------
    def _load_settings(self):
        try:
            data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        for k, var in self.v.items():
            if k in data:
                try:
                    var.set(data[k])
                except tk.TclError:
                    pass
        self._last_dir = data.get("last_dir", "")
        if data.get("geometry"):
            try:
                self.root.geometry(data["geometry"])
            except tk.TclError:
                pass

    def on_close(self):
        data = {k: var.get() for k, var in self.v.items()}
        data["last_dir"] = self._last_dir
        data["geometry"] = self.root.geometry()
        try:
            SETTINGS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except OSError:
            pass
        self.root.destroy()


def run_gui():
    if tk is None:
        sys.exit("tkinter is not available - use the command-line options instead (-h).")
    try:  # sharp text on high-DPI Windows screens
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    root = tk.Tk()
    App(root)
    root.mainloop()


# ======================================================================
# Command line
# ======================================================================

def send(result, dest, count, out_encoding="utf-8"):
    if dest == "screen":
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(errors="replace")
        print(result)
    elif dest == "clip":
        copy_to_clipboard(result)
        print(f"{count} values copied to clipboard.")
    else:
        with open(dest, "w", encoding=out_encoding) as f:
            f.write(result)
        print(f"{count} values written to {dest}")


def cli():
    p = argparse.ArgumentParser(description="Extract, format and output values from a list.",
                                formatter_class=argparse.RawDescriptionHelpFormatter,
                                epilog=__doc__)
    p.add_argument("input", nargs="?", help="input file; omit to read from stdin")
    p.add_argument("--gui", action="store_true", help="open the GUI")
    p.add_argument("--encoding")
    p.add_argument("-d", "--delimiter", default=None)
    p.add_argument("-p", "--part", type=int, default=0)
    p.add_argument("--digits", action="store_true")
    p.add_argument("--regex")
    p.add_argument("--unique", action="store_true")
    p.add_argument("--sort", action="store_true")
    p.add_argument("--preset", choices=PRESETS)
    p.add_argument("--prefix")
    p.add_argument("--suffix")
    p.add_argument("--quote")
    p.add_argument("--join")
    p.add_argument("--trailing", action="store_true")
    p.add_argument("--wrap", nargs=2, metavar=("OPEN", "CLOSE"))
    p.add_argument("--out", choices=["screen", "file", "clip"])
    p.add_argument("-o", "--output")
    p.add_argument("--out-encoding", default="utf-8")
    a = p.parse_args()

    if a.gui:
        run_gui()
        return

    text = read_text(a.input, a.encoding) if a.input else sys.stdin.read()
    values = extract(text.splitlines(), parse_delimiter(a.delimiter), a.part,
                     a.digits, a.regex, a.unique, a.sort)

    fmt = preset_fmt(a.preset or "lines")  # preset first, explicit options override
    for key in ("prefix", "suffix", "quote", "join"):
        if getattr(a, key) is not None:
            fmt[key] = unescape(getattr(a, key))
    if a.wrap:
        fmt["wrap"] = tuple(unescape(w) for w in a.wrap)
    if a.trailing:
        fmt["trailing"] = True
    result = format_values(values, **fmt)

    if a.out == "clip":
        dest = "clip"
    elif a.output:
        dest = a.output
    elif a.out == "file":
        p.error("--out file needs -o FILENAME")
    else:
        dest = "screen"
    send(result, dest, len(values), a.out_encoding)


def main():
    if len(sys.argv) == 1:
        run_gui()
    else:
        cli()


if __name__ == "__main__":
    main()
