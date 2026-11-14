#!/usr/bin/env python3
"""reufs-gui.py -- a file manager for GordonOS's REU filesystem.

Two panes: the host on the left, the image on the right. `Put` copies a host
file in, `Get` writes an image file out and `Delete` tombstones one -- the same
things `save`, `del` and `dir` do on the machine, done from the host, so a file
can leave the emulator and arrive in it.

Runs on Windows, Linux and macOS with nothing but the standard library
(tkinter). The editing rules, and the reason a change is refused while the
emulator runs, are in tools/reufs.py -- this file is the interface to it.

    python tools/reufs-gui.py [IMAGE]
    python tools/reufs-gui.py -h
"""

import argparse
import os
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import reufs                                    # noqa: E402  (after sys.path)


def fmt_size(nbytes):
    if nbytes < 1024:
        return "%d B" % nbytes
    if nbytes < 1024 * 1024:
        return "%.1f KB" % (nbytes / 1024.0)
    return "%.1f MB" % (nbytes / (1024.0 * 1024.0))


class App:
    def __init__(self, root, image_path):
        self.root = root
        self.fs = None
        self.image_path = image_path
        self.host_dir = os.getcwd()
        self.vice = []

        root.title("GordonOS REU filesystem")
        root.geometry("1100x660")
        root.minsize(820, 480)
        self._build()
        self.reload_image()

    # -- construction ------------------------------------------------------
    def _build(self):
        style = ttk.Style()
        try:
            style.configure("Treeview", rowheight=20)
        except tk.TclError:
            pass

        top = ttk.Frame(self.root, padding=(8, 8, 8, 4))
        top.pack(fill="x")
        ttk.Label(top, text="Image").pack(side="left")
        self.image_var = tk.StringVar()
        entry = ttk.Entry(top, textvariable=self.image_var)
        entry.pack(side="left", fill="x", expand=True, padx=6)
        entry.bind("<Return>", lambda _e: self.reload_image())
        ttk.Button(top, text="Browse...", command=self.browse_image).pack(side="left")
        ttk.Button(top, text="Reload", command=self.reload_image).pack(side="left", padx=(6, 0))

        self.banner_label = tk.Label(self.root, anchor="w", justify="left",
                                     padx=8, pady=4, bg="#7a2b2b", fg="white")
        self._banner_visible = False

        body = ttk.PanedWindow(self.root, orient="horizontal")
        body.pack(fill="both", expand=True, padx=8, pady=4)

        # --- host pane ----------------------------------------------------
        left = ttk.Frame(body)
        body.add(left, weight=1)
        head = ttk.Frame(left)
        head.pack(fill="x")
        ttk.Label(head, text="Host", font=("TkDefaultFont", 9, "bold")).pack(side="left")
        ttk.Button(head, text="Up", width=4, command=self.host_up).pack(side="right")
        self.host_path = ttk.Label(left, text="", anchor="w", foreground="#444")
        self.host_path.pack(fill="x")
        self.host_tree = self._tree(left, ("name", "size"),
                                    ("Name", "Size"), (300, 90))
        self.host_tree.bind("<Double-1>", self.host_double)

        # --- the buttons between the panes ---------------------------------
        mid = ttk.Frame(body, padding=(8, 0))
        body.add(mid, weight=0)
        ttk.Style().configure("Put.TButton", font=("TkDefaultFont", 10, "bold"))
        self.put_btn = ttk.Button(mid, text="Put into image  \u2192", width=18,
                                  style="Put.TButton", command=self.put)
        self.put_btn.pack(pady=(60, 4))
        self.get_btn = ttk.Button(mid, text="\u2190  Get from image", width=18,
                                  style="Put.TButton", command=self.get)
        self.get_btn.pack(pady=4)
        self.del_btn = ttk.Button(mid, text="Delete in image", width=18,
                                  command=self.delete)
        self.del_btn.pack(pady=4)
        ttk.Separator(mid, orient="horizontal").pack(fill="x", pady=10)
        self.exp_btn = ttk.Button(mid, text="Export all...", width=18,
                                  command=self.export_all)
        self.exp_btn.pack(pady=4)
        self.imp_btn = ttk.Button(mid, text="Import all...", width=18,
                                  command=self.import_all)
        self.imp_btn.pack(pady=4)
        ttk.Separator(mid, orient="horizontal").pack(fill="x", pady=10)
        self.force_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(mid, text="Allow changes\nwhile VICE runs",
                        variable=self.force_var).pack(pady=2)

        # --- image pane ---------------------------------------------------
        right = ttk.Frame(body)
        body.add(right, weight=1)
        head2 = ttk.Frame(right)
        head2.pack(fill="x")
        ttk.Label(head2, text="REU filesystem",
                  font=("TkDefaultFont", 9, "bold")).pack(side="left")
        self.info = ttk.Label(head2, text="", anchor="e", foreground="#444")
        self.info.pack(side="right")
        self.fs_tree = self._tree(right, ("name", "size", "offset"),
                                  ("Name", "Size", "Offset"), (300, 90, 90))
        self.fs_tree.bind("<Double-1>", lambda _e: self.get())

        # --- log ----------------------------------------------------------
        logf = ttk.Frame(self.root, padding=(8, 0, 8, 8))
        logf.pack(fill="both")
        self.log_text = tk.Text(logf, height=6, wrap="none", state="disabled",
                                font="TkFixedFont", background="#101418",
                                foreground="#d8e0e8")
        bar = ttk.Scrollbar(logf, orient="vertical", command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=bar.set)
        self.log_text.pack(side="left", fill="both", expand=True)
        bar.pack(side="right", fill="y")

    def _tree(self, parent, columns, headings, widths):
        frame = ttk.Frame(parent)
        frame.pack(fill="both", expand=True, pady=(4, 0))
        tree = ttk.Treeview(frame, columns=columns, show="headings",
                            selectmode="extended")
        for col, text, width in zip(columns, headings, widths):
            tree.heading(col, text=text)
            tree.column(col, width=width, anchor="w" if col == "name" else "e",
                        stretch=(col == "name"))
        bar = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=bar.set)
        tree.pack(side="left", fill="both", expand=True)
        bar.pack(side="right", fill="y")
        return tree

    # -- messages ----------------------------------------------------------
    def log(self, text):
        self.log_text.configure(state="normal")
        self.log_text.insert("end", text + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def banner(self, text=None):
        if text:
            self.banner_label.configure(text=text)
            if not self._banner_visible:
                self.banner_label.pack(
                    fill="x", after=self.banner_label.master.winfo_children()[0])
                self._banner_visible = True
        elif self._banner_visible:
            self.banner_label.pack_forget()
            self._banner_visible = False

    def _set_editable(self, enabled):
        state = "normal" if enabled else "disabled"
        for button in (self.put_btn, self.del_btn, self.exp_btn, self.imp_btn):
            button.configure(state=state)

    # -- the image ---------------------------------------------------------
    def browse_image(self):
        path = filedialog.askopenfilename(
            title="Choose a REU image",
            initialdir=os.path.dirname(self.image_path) or ".",
            filetypes=[("REU image", "*.bin"), ("All files", "*.*")])
        if path:
            self.reload_image(path)

    def reload_image(self, path=None):
        path = path or self.image_var.get() or self.image_path
        self.image_path = path
        self.image_var.set(path)
        self.banner()
        try:
            self.fs = reufs.ReuImage(path)
        except reufs.FsError as exc:
            self.fs = None
            self.banner("Cannot open the image: %s" % exc)
            self.log("error: %s" % exc)
            for tree in (self.fs_tree,):
                tree.delete(*tree.get_children())
            self.info.configure(text="")
            self._set_editable(False)
            self.refresh_host()
            return

        self.vice = reufs.running_vice()
        if self.vice:
            names = ", ".join(sorted({p[1] for p in self.vice}))
            self.banner(
                "VICE is running (%s) and holds this image mapped. You can "
                "browse and Get, but a change now would leave the emulator on "
                "the old copy -- close VICE, or tick the box below." % names)
            self._set_editable(False)
        else:
            self._set_editable(True)
        self.log("opened %s" % path)
        self.refresh_fs()
        self.refresh_host()

    def refresh_fs(self):
        tree = self.fs_tree
        tree.delete(*tree.get_children())
        if not self.fs:
            self.info.configure(text="")
            return
        entries = sorted(self.fs.entries(), key=lambda e: e.name.lower())
        for e in entries:
            tree.insert("", "end", iid=str(e.slot),
                        values=(e.name, fmt_size(e.size), e.offset))
        self.info.configure(
            text="%d file(s) -- %s of %s used, %s free"
                 % (len(entries), fmt_size(self.fs.next_free),
                    fmt_size(self.fs.capacity), fmt_size(self.fs.free)))

    def save(self):
        force = self.force_var.get()
        self.fs.save(force=force)
        self.log("image written%s" % (" (forced while VICE runs)" if force else ""))

    def _run(self, action):
        """Run an edit, reporting every refusal in the log and the banner.

        A refusal reloads the image. The library holds changes in memory until a
        save, so a batch that failed part way through -- Import all, where the
        fifth file does not fit -- would otherwise leave the first four staged,
        and the next successful action would write them out."""
        if not self.fs:
            return
        try:
            action()
        except reufs.FsError as exc:
            self.log("refused: %s" % exc)
            self.reload_image()
            messagebox.showwarning("Not done", str(exc), parent=self.root)
            return
        except OSError as exc:
            self.log("error: %s" % exc)
            self.reload_image()
            messagebox.showerror("Error", str(exc), parent=self.root)
            return
        self.refresh_fs()

    # -- the host ----------------------------------------------------------
    def refresh_host(self):
        tree = self.host_tree
        tree.delete(*tree.get_children())
        self.host_path.configure(text=self.host_dir)
        try:
            names = sorted(os.listdir(self.host_dir),
                           key=lambda n: (not os.path.isdir(
                               os.path.join(self.host_dir, n)), n.lower()))
        except OSError as exc:
            self.log("cannot list %s: %s" % (self.host_dir, exc))
            return
        parent = os.path.dirname(self.host_dir)
        if parent and parent != self.host_dir:
            tree.insert("", "end", iid="..", values=("..", ""))
        for name in names:
            full = os.path.join(self.host_dir, name)
            if os.path.isdir(full):
                tree.insert("", "end", iid=full, values=(name + "/", ""))
            else:
                try:
                    size = os.path.getsize(full)
                except OSError:
                    size = 0
                tree.insert("", "end", iid=full, values=(name, fmt_size(size)))

    def host_up(self):
        parent = os.path.dirname(self.host_dir)
        if parent and parent != self.host_dir:
            self.host_dir = parent
            self.refresh_host()

    def host_double(self, _event):
        for iid in self.host_tree.selection():
            if iid == "..":
                self.host_up()
                return
            if os.path.isdir(iid):
                self.host_dir = iid
                self.refresh_host()
                return

    def host_files(self):
        """The selected host files; a selected directory is refused, because
        the filesystem has no directories."""
        files = []
        for iid in self.host_tree.selection():
            if iid == "..":
                continue
            if os.path.isdir(iid):
                self.log("skipped %s: the filesystem has no directories"
                         % os.path.basename(iid))
                continue
            files.append(iid)
        if not files and self.host_tree.selection():
            self.log("nothing to put: select a file, not a directory")
        return files

    # -- the transfers -----------------------------------------------------
    def put(self):
        if not self.fs:
            return
        files = self.host_files()
        if not files:
            messagebox.showinfo("Put", "Select one or more host files first.",
                                parent=self.root)
            return

        def action():
            put = 0
            for path in files:
                name = os.path.basename(path)
                with open(path, "rb") as fh:
                    blob = fh.read()
                existing = self.fs.find(name)
                if existing is not None and not messagebox.askyesno(
                        "Replace?",
                        "'%s' is already in the image (slot %d, %s).\n\n"
                        "Replace it? The old bytes stay as a hole until "
                        "`compact` runs on the machine."
                        % (name, existing.slot, fmt_size(existing.size)),
                        parent=self.root):
                    self.log("skipped %s: kept the copy in the image" % name)
                    continue
                slot = self.fs.put(name, blob, overwrite=True)
                self.log("put %-14s %8s -> slot %d" % (name, fmt_size(len(blob)), slot))
                put += 1
            if put:
                self.save()

        self._run(action)

    def get(self):
        if not self.fs:
            return
        slots = self.fs_tree.selection()
        if not slots:
            messagebox.showinfo("Get", "Select one or more image files first.",
                                parent=self.root)
            return

        def action():
            got = 0
            for iid in slots:
                entry = self.fs.raw_entry(int(iid))
                target = os.path.join(self.host_dir, entry.name)
                if os.path.exists(target) and not messagebox.askyesno(
                        "Overwrite?",
                        "%s already exists on the host.\n\nOverwrite it?"
                        % target, parent=self.root):
                    self.log("skipped %s: kept the host copy" % entry.name)
                    continue
                blob = self.fs.get(entry.name)
                with open(target, "wb") as fh:
                    fh.write(blob)
                self.log("got %-14s %8s -> %s" % (entry.name, fmt_size(len(blob)), target))
                got += 1
            if got:
                self.refresh_host()

        self._run(action)

    def delete(self):
        if not self.fs:
            return
        slots = self.fs_tree.selection()
        if not slots:
            messagebox.showinfo("Delete", "Select one or more image files first.",
                                parent=self.root)
            return
        names = [self.fs.raw_entry(int(i)).name for i in slots]
        if not messagebox.askyesno(
                "Delete",
                "Delete %d file(s) from the image?\n\n%s\n\n"
                "The space returns when `compact` runs on the machine."
                % (len(names), "\n".join(names)), parent=self.root):
            return

        def action():
            for name in names:
                e = self.fs.delete(name)
                self.log("deleted %-14s (slot %d)" % (e.name, e.slot))
            self.save()

        self._run(action)

    def export_all(self):
        if not self.fs:
            return
        directory = filedialog.askdirectory(
            title="Export every image file into...", initialdir=self.host_dir)
        if not directory:
            return

        def action():
            done = self.fs.export_to(directory, overwrite=True)
            self.log("exported %d file(s) to %s" % (len(done), directory))
            self.refresh_host()

        self._run(action)

    def import_all(self):
        if not self.fs:
            return
        directory = filedialog.askdirectory(
            title="Import every file in...", initialdir=self.host_dir)
        if not directory:
            return

        def action():
            added = self.fs.import_from(directory, overwrite=True)
            for name, size in added:
                self.log("put %-14s %8s" % (name, fmt_size(size)))
            if added:
                self.save()

        self._run(action)


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="File manager for GordonOS's REU filesystem.")
    ap.add_argument("image", nargs="?", default=None,
                    help="the REU image (default: this repo's reu/REU.bin)")
    args = ap.parse_args(argv)

    image = args.image or reufs.default_image()
    root = tk.Tk()
    app = App(root, image)
    if not os.path.exists(image):
        app.log("no image at %s -- use Browse... to pick one" % image)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
