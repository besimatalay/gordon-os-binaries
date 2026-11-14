#!/usr/bin/env python3
"""reufs.py -- read and write GordonOS's REU filesystem inside a REU image.

Why this exists: a file a task SAVES lives only in the REU image, and until now
nothing on the host could add one to an EXISTING image -- tools/build-reu.ps1
formats a fresh one, and tools/check-reu-fs.ps1 can pull a single file out. This
is the other half, and the library behind tools/reufs-gui.py.

The layout, taken from src/libs/filesys.asm and tools/build-reu.ps1 (both read
for this, not recalled -- Rule 9):

    bank 5, $9000   512 x 32-byte directory entries; slot 0 is the header
    bank 5, $D000   file data, addressed by a 24-bit offset RELATIVE to it:
                    image byte = offset + $5D000, so a bank wrap happens at
                    offsets ending $3000, not $0000

    entry  +0      flags; bit 7 = deleted
           +1..+16 name, space padded, SCREEN CODES, at most 11 used
           +17..  data offset, 24-bit
           +20..  size, 16-bit (so 65,535 bytes is the most one file can hold)
           +22..  untouched by the OS; zeroed here so the bytes are deterministic

    slot 0 +1      $A5 signature -- no signature means "not a filesystem"
           +17..  nextFreeOffset, 24-bit: data is appended here
           +20..  capacity, 24-bit

A name is stored in screen codes, not ASCII: `a`-`z` are $01-$1A and every other
character is its own byte (`0`-`9`, `.`, `_` and `A`-`Z` are unchanged). That is
exactly what `.encoding "screencode_mixed"` emits, so a name reads the same on
both sides -- and it is why `musedit.tsk` is stored as
`0d 15 13 05 04 09 14 2e 14 13 0b`.

What this mirrors from the OS (fsxSave and fsxDelete), so a host-side change
leaves an image the machine would have produced itself:

  * a name is 1-11 characters; empty or longer is refused
  * a live duplicate is refused -- delete the old one first, as `save` does
  * a zero-length file cannot exist: the OS reads size == 0 as an EMPTY SLOT,
    and its own save refuses size 0
  * the first slot whose two size bytes are both 0 is used. A TOMBSTONE is NOT
    reused: delete sets bit 7 and blanks the name but keeps the extent, so the
    space comes back only through `compact` on the machine
  * data is appended at nextFreeOffset, which then advances by the size
  * the space check is nextFreeOffset + size <= capacity, exact fit allowed

Writes are atomic: the image is read, changed in memory, written to a sibling
temp file and renamed over the original, so a crash cannot leave a half-written
directory behind.

Cross-platform note, and the reason for the process scan below: Windows REFUSES
a write to an image the emulator has memory-mapped, but Linux and macOS let it
through -- the emulator then keeps the old inode and the two diverge silently,
which is worse than an error. So this refuses to CHANGE an image while a VICE
process is running, on every platform, unless forced. Reading is always allowed:
the image is mapped read-write, which is how a file is recovered from a wedged
run (docs/bugs.md records pulling `<base>.wrk` out of one).

Usage:
    python tools/reufs.py ls
    python tools/reufs.py get musedit.tsk out.tsk
    python tools/reufs.py put build/gordon-os.prg --name test.prg
    python tools/reufs.py rm test.prg
    python tools/reufs.py export backup/
    python tools/reufs.py import backup/
    python tools/reufs.py selftest

`-i/--image` selects another image (the default is this repo's reu/REU.bin);
`--force` allows a change while VICE runs, for the case where the user knows
the emulator is idle.
"""

import argparse
import os
import subprocess
import sys
import tempfile

# --- the layout (bytes and offsets, all verified against the OS source) ------
REU_BANK = 5
REU_BANK_SIZE = 65536
DIR_BASE = REU_BANK * REU_BANK_SIZE + 0x9000     # 5 * 65536 + $9000 = 393216
DATA_BASE = REU_BANK * REU_BANK_SIZE + 0xD000    # 5 * 65536 + $D000 = 380928
ENTRY_SIZE = 32
SLOT_COUNT = 512                                 # slot 0 is the header
NAME_MAX = 11
NAME_FIELD = 16
SIGNATURE = 0xA5

E_FLAGS = 0
E_NAME = 1
E_OFFSET = 17
E_SIZE = 20
H_OFFSET = 17
H_CAPACITY = 20

MAX_FILE = 0xFFFF

# VICE's executable names, matched exactly after stripping a directory and .exe
VICE_PROGRAMS = {
    "x64", "x64sc", "x64dtv", "x64scpu", "x128", "xvic", "xplus4",
    "xcbm2", "xcbm5x0", "vsid", "vice",
}


class FsError(Exception):
    """A refused operation. `code` matches the kernel's kReuSave errors where
    one exists: 0 duplicate, 1 no space, 2 directory full, 3 name too long,
    4 empty name."""

    def __init__(self, message, code=None):
        super().__init__(message)
        self.code = code


# --- names ------------------------------------------------------------------
def encode_name(name):
    """The bytes the directory stores for `name` (screen codes, unterminated)."""
    out = bytearray()
    for ch in name:
        o = ord(ch)
        if not 0x20 <= o <= 0x7E:
            raise FsError("a name cannot hold %r -- the filesystem stores "
                          "screen codes, so use printable ASCII" % ch, 3)
        out.append(o - 96 if 0x61 <= o <= 0x7A else o)
    return bytes(out)


def decode_name(raw):
    """Inverse of encode_name over a 16-byte field (space padding skipped)."""
    out = []
    for b in raw:
        if b in (0, 0x20):
            continue
        out.append(chr(96 + b) if 1 <= b <= 26 else chr(b))
    return "".join(out)


def check_name(name):
    if not name:
        raise FsError("an empty name cannot be stored", 4)
    if len(name) > NAME_MAX:
        raise FsError("'%s' is %d characters; the filesystem holds %d, "
                      "extension included" % (name, len(name), NAME_MAX), 3)
    encode_name(name)          # raises for a character it cannot store


# --- the emulator guard -----------------------------------------------------
def running_vice():
    """[(pid, name)] for any VICE emulator process visible to this host.

    A process scan rather than a file lock, because the emulator does not take
    one: the image is memory-mapped, which is also why the write is refused
    rather than trusted to fail on its own (see the module docstring)."""
    found = []
    try:
        if os.name == "nt":
            out = subprocess.run(["tasklist", "/FO", "CSV", "/NH"],
                                 capture_output=True, text=True, timeout=20)
            for line in out.stdout.splitlines():
                parts = [p.strip('"') for p in line.split('","')]
                if len(parts) < 2:
                    continue
                name = parts[0].lower()
                if name.endswith(".exe"):
                    name = name[:-4]
                if name in VICE_PROGRAMS:
                    found.append((parts[1], parts[0]))
        else:
            out = subprocess.run(["ps", "-A", "-o", "pid=,comm="],
                                 capture_output=True, text=True, timeout=20)
            for line in out.stdout.splitlines():
                fields = line.split(None, 1)
                if len(fields) != 2:
                    continue
                name = os.path.basename(fields[1].strip()).lower()
                if name in VICE_PROGRAMS:
                    found.append((fields[0], fields[1].strip()))
    except (OSError, subprocess.SubprocessError):
        return []
    return found


def default_image():
    """The image to work on when none was given.

    Two layouts have to work: this repo, where the script is in tools/ and the
    image is in reu/, and the published package, where the scripts and the
    images sit side by side and there is no reu/ directory."""
    here = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(here, os.pardir, "reu", "REU.bin"),   # this repo
        os.path.join(here, "REU.bin"),                     # published, flat
        os.path.join(here, os.pardir, "REU.bin"),          # published, in tools/
        os.path.join(os.getcwd(), "reu", "REU.bin"),
        os.path.join(os.getcwd(), "REU.bin"),
    ]
    for path in candidates:
        if os.path.isfile(path):
            return os.path.normpath(path)
    return os.path.normpath(candidates[0])                 # the path to complain about


# --- the image --------------------------------------------------------------
class Entry:
    __slots__ = ("slot", "name", "offset", "size", "deleted")

    def __init__(self, slot, name, offset, size, deleted):
        self.slot = slot
        self.name = name
        self.offset = offset
        self.size = size
        self.deleted = deleted

    def __repr__(self):
        return "Entry(%d, %r, %d, %d%s)" % (
            self.slot, self.name, self.offset, self.size,
            ", deleted" if self.deleted else "")


class ReuImage:
    """One REU image. Changes are held in memory until save()."""

    def __init__(self, path=None, create_for_test=False):
        self.path = os.fspath(path or default_image())
        try:
            with open(self.path, "rb") as fh:
                self.data = bytearray(fh.read())
        except OSError as exc:
            raise FsError("cannot read %s: %s" % (self.path, exc))
        if not create_for_test:
            self._check_signature()
        self.dirty = False

    # -- header ------------------------------------------------------------
    def _check_signature(self):
        if len(self.data) <= DIR_BASE + 2:
            raise FsError("%s is too small to hold a filesystem" % self.path)
        if self.data[DIR_BASE + 1] != SIGNATURE:
            raise FsError("%s is not a GordonOS filesystem (no $A5 signature at "
                          "bank 5 + $9001). Format it on the machine with "
                          "`format`, or seed one with tools/build-reu.ps1"
                          % self.path)

    def _read24(self, at):
        return self.data[at] | (self.data[at + 1] << 8) | (self.data[at + 2] << 16)

    def _write24(self, at, value):
        self.data[at] = value & 0xFF
        self.data[at + 1] = (value >> 8) & 0xFF
        self.data[at + 2] = (value >> 16) & 0xFF

    @property
    def next_free(self):
        return self._read24(DIR_BASE + H_OFFSET)

    @next_free.setter
    def next_free(self, value):
        self._write24(DIR_BASE + H_OFFSET, value)
        self.dirty = True

    @property
    def capacity(self):
        return self._read24(DIR_BASE + H_CAPACITY)

    @property
    def free(self):
        return max(0, self.capacity - self.next_free)

    @property
    def image_size(self):
        return len(self.data)

    # -- the directory -----------------------------------------------------
    def _slot_base(self, slot):
        return DIR_BASE + slot * ENTRY_SIZE

    def raw_entry(self, slot):
        base = self._slot_base(slot)
        flags = self.data[base + E_FLAGS]
        raw = self.data[base + E_NAME:base + E_NAME + NAME_FIELD]
        deleted = bool(flags & 0x80) or not any(b not in (0, 0x20) for b in raw)
        return Entry(slot, decode_name(raw), self._read24(base + E_OFFSET),
                     self.data[base + E_SIZE] | (self.data[base + E_SIZE + 1] << 8),
                     deleted)

    def entries(self, include_deleted=False):
        """Every entry, in slot order. A slot is dead when bit 7 is set or the
        name is blank (delete does both)."""
        out = []
        for slot in range(1, SLOT_COUNT):
            e = self.raw_entry(slot)
            if e.deleted and not include_deleted:
                continue
            if not e.deleted:
                out.append(e)
            elif include_deleted:
                out.append(e)
        return out

    def find(self, name):
        for e in self.entries():
            if e.name == name:
                return e
        return None

    # -- data --------------------------------------------------------------
    def get(self, name):
        """The bytes of `name`."""
        e = self.find(name)
        if e is None:
            raise FsError("no such file in the image: %s" % name)
        start = DATA_BASE + e.offset
        end = start + e.size
        if end > len(self.data):
            raise FsError("%s says %d bytes at %d, which runs past the end of "
                          "the image" % (name, e.size, e.offset))
        return bytes(self.data[start:end])

    def put(self, name, blob, overwrite=False):
        """Add a file, appended the way the OS appends one.

        `overwrite` deletes the live entry of that name first, which is what a
        file manager's "replace" means; the old bytes stay as a hole until
        `compact` runs on the machine, exactly as delete + save would leave.

        Every check that can refuse runs BEFORE anything is changed, and the
        delete is the last thing before the write. A refused replacement must
        leave the old file where it was: deleting first and then discovering
        there is no room would report "not enough room" and destroy the file the
        caller was trying to replace."""
        check_name(name)
        if not blob:
            raise FsError("a zero-length file cannot be stored -- the "
                          "filesystem reads size 0 as an empty slot", 4)
        if len(blob) > MAX_FILE:
            raise FsError("%d bytes is over the 16-bit size field's %d"
                          % (len(blob), MAX_FILE))
        existing = self.find(name)
        if existing is not None and not overwrite:
            raise FsError("'%s' is already in the image (slot %d); delete "
                          "it first, or use overwrite" % (name, existing.slot), 0)

        # The slot search comes before the delete: a tombstone keeps its extent,
        # so deleting does NOT free a slot and cannot make room here.
        slot = None
        for s in range(1, SLOT_COUNT):
            base = self._slot_base(s)
            if self.data[base + E_SIZE] == 0 and self.data[base + E_SIZE + 1] == 0:
                slot = s
                break
        if slot is None:
            raise FsError("the directory is full (all %d slots are live or "
                          "tombstoned). Run `compact` on the machine to reclaim "
                          "the deleted ones" % (SLOT_COUNT - 1), 2)

        offset = self.next_free
        end = offset + len(blob)
        if end > self.capacity:
            raise FsError("not enough room: %d bytes needed from offset %d, "
                          "capacity is %d (%d free)"
                          % (len(blob), offset, self.capacity, self.free), 1)
        start = DATA_BASE + offset
        stop = start + len(blob)
        if stop > len(self.data):
            raise FsError("the image is smaller than the filesystem's capacity: "
                          "writing to %d would run past its %d bytes"
                          % (stop, len(self.data)))

        if existing is not None:
            self.delete(name)          # nothing below this line can refuse

        self.data[start:stop] = blob
        base = self._slot_base(slot)
        self.data[base + E_FLAGS] = 0
        padded = encode_name(name).ljust(NAME_FIELD, b"\x20")
        self.data[base + E_NAME:base + E_NAME + NAME_FIELD] = padded
        self._write24(base + E_OFFSET, offset)
        self.data[base + E_SIZE] = len(blob) & 0xFF
        self.data[base + E_SIZE + 1] = (len(blob) >> 8) & 0xFF
        self.data[base + E_SIZE + 2:base + ENTRY_SIZE] = b"\x00" * (
            ENTRY_SIZE - E_SIZE - 2)
        self.next_free = end
        return slot

    def delete(self, name):
        """Tombstone `name`: set bit 7 and blank the name, keeping the extent,
        which is what fsxDelete does."""
        e = self.find(name)
        if e is None:
            raise FsError("no such file in the image: %s" % name)
        base = self._slot_base(e.slot)
        self.data[base + E_FLAGS] |= 0x80
        self.data[base + E_NAME:base + E_NAME + NAME_FIELD] = b"\x20" * NAME_FIELD
        self.dirty = True
        return e

    # -- persistence -------------------------------------------------------
    def save(self, force=False):
        """Write the image back atomically. Refused while a VICE process runs
        unless forced, because on Linux and macOS that write would silently
        leave the emulator holding the old image."""
        if not self.dirty:
            return False
        if not force:
            procs = running_vice()
            if procs:
                names = ", ".join(sorted({p[1] for p in procs}))
                raise FsError(
                    "a VICE emulator is running (%s), and it holds this image "
                    "mapped: changing it now would leave the emulator on the "
                    "old copy. Close VICE and try again, or pass --force if it "
                    "is only sitting at an idle prompt" % names)
        directory = os.path.dirname(os.path.abspath(self.path)) or "."
        fd, temp = tempfile.mkstemp(prefix=".reufs-", suffix=".tmp", dir=directory)
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(self.data)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(temp, self.path)
        except BaseException:
            try:
                os.unlink(temp)
            except OSError:
                pass
            raise
        self.dirty = False
        return True

    # -- bulk --------------------------------------------------------------
    def export_to(self, directory, overwrite=False):
        """Write every live file into `directory`. Returns [(name, bytes)]."""
        os.makedirs(directory, exist_ok=True)
        done = []
        for e in self.entries():
            target = os.path.join(directory, e.name)
            if os.path.exists(target) and not overwrite:
                raise FsError("%s already exists -- pass overwrite to replace it"
                              % target)
            with open(target, "wb") as fh:
                fh.write(self.get(e.name))
            done.append((e.name, e.size))
        return done

    def import_from(self, directory, overwrite=False):
        """Add every regular file in `directory` (no recursion: the filesystem
        has no directories either). Returns [(name, bytes)]."""
        done = []
        for name in sorted(os.listdir(directory)):
            path = os.path.join(directory, name)
            if not os.path.isfile(path):
                continue
            with open(path, "rb") as fh:
                blob = fh.read()
            self.put(name, blob, overwrite=overwrite)
            done.append((name, len(blob)))
        return done


# --- self test --------------------------------------------------------------
def _selftest():
    """Exercise every rule above on a synthetic image. Prints one line per
    check and 'selftest: OK'. No emulator, no image from the tree."""
    checks = 0
    failures = []

    def ok(label, cond):
        nonlocal checks
        checks += 1
        if not cond:
            failures.append(label)

    def refuses(label, fn, code=None):
        try:
            fn()
        except FsError as exc:
            good = code is None or exc.code == code
            ok("%s (refused: %s)" % (label, exc), good)
        else:
            ok("%s (NOT refused)" % label, False)

    # name codec: the exact bytes a real image holds
    ok("encode mush", encode_name("musedit.tsk") ==
       bytes([0x0D, 0x15, 0x13, 0x05, 0x04, 0x09, 0x14, 0x2E, 0x14, 0x13, 0x0B]))
    ok("encode underscore", encode_name("gpui_mc.bin") ==
       bytes([0x07, 0x10, 0x15, 0x09, 0x5F, 0x0D, 0x03, 0x2E, 0x02, 0x09, 0x0E]))
    ok("encode digits", encode_name("llama44.anm") ==
       bytes([0x0C, 0x0C, 0x01, 0x0D, 0x01, 0x34, 0x34, 0x2E, 0x01, 0x0E, 0x0D]))
    for probe in ("musedit.tsk", "gpui_mc.bin", "llama44.anm", "MUSIC.MUS", "a"):
        raw = encode_name(probe).ljust(NAME_FIELD, b"\x20")
        ok("round trip %s" % probe, decode_name(raw) == probe)

    # a synthetic 4 KB filesystem
    path = os.path.join(tempfile.gettempdir(), "reufs-selftest.bin")
    blob = bytearray(DATA_BASE + 4096)
    blob[DIR_BASE + 1] = SIGNATURE
    for i, v in enumerate((0, 0, 0)):
        blob[DIR_BASE + H_OFFSET + i] = v
    for i, v in enumerate((0x00, 0x10, 0x00)):      # capacity 4096
        blob[DIR_BASE + H_CAPACITY + i] = v
    with open(path, "wb") as fh:
        fh.write(blob)

    fs = ReuImage(path)
    ok("empty filesystem", fs.entries() == [] and fs.next_free == 0
       and fs.capacity == 4096 and fs.free == 4096)

    ok("put a.bin", fs.put("a.bin", bytes(range(100))) == 1)
    ok("next_free advanced", fs.next_free == 100)
    e = fs.find("a.bin")
    ok("entry recorded", e is not None and e.offset == 0 and e.size == 100
       and e.slot == 1)
    ok("get round trip", fs.get("a.bin") == bytes(range(100)))

    ok("put b.bin", fs.put("b.bin", b"\xAA" * 200) == 2)
    ok("appended, not overwritten", fs.find("b.bin").offset == 100
       and fs.next_free == 300)
    ok("two entries", len(fs.entries()) == 2)

    refuses("duplicate name", lambda: fs.put("a.bin", b"x"), 0)
    refuses("empty name", lambda: fs.put("", b"x"), 4)
    refuses("name too long", lambda: fs.put("abcdefghijkl", b"x"), 3)
    refuses("zero-length file", lambda: fs.put("c.bin", b""), 4)
    refuses("over the 16-bit size", lambda: fs.put("c.bin", b"x" * 65536))
    refuses("no room", lambda: fs.put("c.bin", b"x" * 4000), 1)
    refuses("no such file", lambda: fs.get("zzz"))

    ok("overwrite replaces", fs.put("a.bin", b"NEW", overwrite=True) == 3)
    ok("overwrite kept one entry of that name",
       len([x for x in fs.entries() if x.name == "a.bin"]) == 1)
    ok("overwrite reads back", fs.get("a.bin") == b"NEW")
    ok("the old extent is a hole, not a reuse",
       fs.find("a.bin").offset == 300 and fs.find("b.bin").offset == 100)

    # A refused replacement must leave the file it was going to replace: the
    # delete has to happen after every check that can refuse, or "not enough
    # room" is reported by destroying the file.
    refuses("a replacement that does not fit",
            lambda: fs.put("a.bin", b"x" * 3800, overwrite=True), 1)
    ok("...and the file it would have replaced is still there",
       fs.find("a.bin") is not None and fs.get("a.bin") == b"NEW")
    refuses("a replacement whose name is too long",
            lambda: fs.put("abcdefghijkl", b"x", overwrite=True), 3)

    done = fs.delete("b.bin")
    ok("delete tombstones", done.name == "b.bin" and fs.find("b.bin") is None)
    ok("tombstone keeps its extent", fs.raw_entry(done.slot).size == 200
       and fs.raw_entry(done.slot).deleted)
    ok("tombstone is not reused", fs.put("d.bin", b"Z" * 10) == 4
       and fs.find("d.bin").offset == 303)

    fs.save()
    again = ReuImage(path)
    ok("survives a reload", [x.name for x in again.entries()] == ["a.bin", "d.bin"]
       and again.get("a.bin") == b"NEW" and again.next_free == 313)

    # export / import
    out = os.path.join(tempfile.gettempdir(), "reufs-selftest-out")
    again.export_to(out, overwrite=True)
    ok("export wrote both", sorted(os.listdir(out)) == ["a.bin", "d.bin"])
    scratch = ReuImage(path)
    scratch.delete("a.bin")
    scratch.delete("d.bin")
    added = scratch.import_from(out)
    ok("import added both", len(added) == 2)

    for p in (path,):
        try:
            os.unlink(p)
        except OSError:
            pass
    for name in ("a.bin", "d.bin"):
        try:
            os.unlink(os.path.join(out, name))
        except OSError:
            pass
    try:
        os.rmdir(out)
    except OSError:
        pass

    for f in failures:
        print("  FAILED: %s" % f)
    print("selftest: %d checks, %d failed" % (checks, len(failures)))
    return 0 if not failures else 1


# --- command line -----------------------------------------------------------
def _fmt(nbytes):
    if nbytes < 1024:
        return "%d B" % nbytes
    return "%.1f KB" % (nbytes / 1024.0)


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Read and write GordonOS's REU filesystem in an image.")
    ap.add_argument("-i", "--image", default=None,
                    help="the REU image (default: this repo's reu/REU.bin)")
    ap.add_argument("--force", action="store_true",
                    help="allow a change while a VICE emulator is running")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("ls", help="list the filesystem")
    p = sub.add_parser("get", help="write one file out of the image")
    p.add_argument("name")
    p.add_argument("out")
    p = sub.add_parser("put", help="add one file to the image")
    p.add_argument("file")
    p.add_argument("--name", default=None,
                   help="the name to store it under (default: the file's own)")
    p = sub.add_parser("rm", help="delete one file")
    p.add_argument("name")
    p = sub.add_parser("export", help="write every file into a directory")
    p.add_argument("dir")
    p = sub.add_parser("import", help="add every file in a directory")
    p.add_argument("dir")
    sub.add_parser("selftest", help="check itself against the OS's rules")

    args = ap.parse_args(argv)
    if args.cmd == "selftest":
        return _selftest()

    fs = ReuImage(args.image)
    try:
        if args.cmd == "ls":
            entries = fs.entries()
            for e in sorted(entries, key=lambda x: x.name.lower()):
                print("%-14s %8s  offset %d" % (e.name, _fmt(e.size), e.offset))
            print("%d file(s), %s used of %s, %s free"
                  % (len(entries), _fmt(fs.next_free), _fmt(fs.capacity),
                     _fmt(fs.free)))
        elif args.cmd == "get":
            blob = fs.get(args.name)
            with open(args.out, "wb") as fh:
                fh.write(blob)
            print("wrote %s (%s) from %s" % (args.out, _fmt(len(blob)), args.name))
        elif args.cmd == "put":
            with open(args.file, "rb") as fh:
                blob = fh.read()
            name = args.name or os.path.basename(args.file)
            slot = fs.put(name, blob, overwrite=True)
            fs.save(force=args.force)
            print("put %s (%s) in slot %d" % (name, _fmt(len(blob)), slot))
        elif args.cmd == "rm":
            e = fs.delete(args.name)
            fs.save(force=args.force)
            print("deleted %s (slot %d; the space returns with `compact`)"
                  % (e.name, e.slot))
        elif args.cmd == "export":
            done = fs.export_to(args.dir, overwrite=True)
            print("exported %d file(s) to %s" % (len(done), args.dir))
        elif args.cmd == "import":
            done = fs.import_from(args.dir, overwrite=True)
            fs.save(force=args.force)
            print("imported %d file(s) from %s" % (len(done), args.dir))
    except FsError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
