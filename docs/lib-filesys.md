# `filesys.lib` — Library Reference

REU filesystem: format, save, delete, rename, dirEntry, and the in-place
I/O primitives create/open/readAt/writeAt. (Only `kReuLoad` and the
resident helpers remain in the kernel.)

| | |
|---|---|
| Lib ID | 1 |
| Entries | 9 (`format`, `save`, `delete`, `rename`, `dirEntry`, `create`, `open`, `readAt`, `writeAt`) |
| Load policy | **lazy** — auto-loaded on the first call |
| Call indices | 3–11 (jump entries patched via `libJumpLo/Hi` + `libInitLo/Hi`) |
| Kernel entry points | `kReuFormat`, `kReuSave`, `kReuDelete`, `kReuRename`, `kReuDirEntry`, `kReuCreate`, `kReuOpen`, `kReuReadAt`, `kReuWriteAt` |
| Source | `src/libs/filesys.asm` |

## Calling

Call the kernel entry points from any task. Each is a lazy cold stub: on the
cold path it saves your registers + `kArg` block + `kPtr` + `dataPtr` +
`srcPtr`, loads `filesys.lib`, restores them, then jumps through the
now-patched jump entry.

- If the lib **cannot be loaded**, the stub returns immediately with
  **C = 1**.
- **Scratch ZP caveat:** a lazy load clobbers `srcPtr`, `taskNamePtr` and
  `spawnPtr` -- and so do the routines themselves, which walk file names and
  records with `srcPtr`. Don't hold a value in them across these calls: address
  what you need through `kPtr`, or re-derive it afterwards.
- Every entry checks the FS signature; if the FS is disabled/unformatted,
  the call fails (`C = 1`) without touching the image.

## Shared conventions

- **Filenames** are null-terminated **screen codes** (what keyboard input
  produces), 1–11 characters, passed as a 16-bit pointer.
- Error results return **C = 1** with a code in `kArg+6` where noted.
- `format`/`save`/`delete`/`rename` all run with interrupts disabled around
  the REU directory DMA (`sei` … `cli`) and return with IRQs enabled.

## Entries

### `kReuFormat` — format the filesystem

- **Input:** none.
- **Output:** C = 0 (always on success). A fresh, empty FS: directory
  zeroed, slot-0 signature + capacity + free offset written,
  `reuFsEnabled` set.
- **Clobbers:** A and `kArg`+0…+4 (used for the fill params); X is
  preserved (`kReuFillReu` keeps X).
- **Notes:** unfiles everything — only the 16 KB directory is zero-filled;
  the data region is left untouched, so **file contents survive a `format`**
  (it is not a secure erase). The shell's `format` command wraps this.

### `kReuSave` — save a C64 memory block

- **Input:**
  - `kArg`/`kArg+1` = filename pointer (screen codes, NUL-terminated,
    1–11 chars)
  - `kArg+2`/`kArg+3` = end address (**exclusive**)
  - `kPtr`/`kPtr+1` = start address
- **Output:** C = 0 saved. C = 1 error, code in `kArg+6`:

  | Code | Meaning |
  |---|---|
  | 0 | duplicate name already exists |
  | 1 | no space left in FS |
  | 2 | directory full |
  | 3 | name too long (>11 chars) |
  | 4 | empty name |
  | (unset) | bad size (end ≤ start) or FS disabled |

- **Clobbers:** A, X, Y, `kPtr`, `srcPtr`; `kArg`+0…+6 used (the error
  code lands in `kArg+6`). The directory scan detects a duplicate name
  explicitly (error 0) and at the same time latches the first free slot.
- **Notes:** the block is copied to the REU via DMA; sizes are byte-exact.

```asm
lda #<filename          // "myfile" in screen codes
sta kArg
lda #>filename
sta kArg+1
lda #<$c000             // save $0400-$c000
sta kArg+2
lda #>$c000
sta kArg+3
lda #<$0400
sta kPtr
lda #>$0400
sta kPtr+1
jsr kReuSave
bcs saveFailed          // kArg+6 = reason
```

### `kReuDelete` — delete a file

- **Input:** `kArg`/`kArg+1` = filename pointer (screen codes).
- **Output:** C = 0 deleted (entry flagged + name cleared). C = 1 not
  found or FS disabled.
- **Clobbers:** A, X, Y, `kArg`+0…+6 (scratch); `reuFsName`/`reuFsFlags`
  (kernel FS state, safe to ignore).
- **Notes:** deletion is a **tombstone** — bit 7 of the flags byte is set,
  the 16-byte name field is blanked, and the data offset + size are left
  intact. **Nothing is reclaimed.** The file's bytes stay allocated
  (`nextFreeOffset` never decreases) and the directory slot never becomes
  reusable, because the allocator's free-slot test is `size == 0` while a
  tombstone keeps its nonzero size. Only the *name* is freed (tombstones are
  skipped by the duplicate check), so `del x` → `save x` works but consumes
  a fresh slot and fresh data. **Only `kReuFormat` recovers the space**, and
  after 511 delete cycles the directory reports "dir full" even with an
  empty data area. Nothing is erased: contents remain readable through any
  file record obtained before the delete.

### `kReuRename` — rename a file

- **Input:**
  - `kArg`/`kArg+1` = old name pointer (screen codes)
  - `kArg+2`/`kArg+3` = new name pointer (screen codes, 1–11 chars)
- **Output:** C = 0 renamed. C = 1 error, code in `kArg+6`:

  | Code | Meaning |
  |---|---|
  | 0 | old name not found |
  | 1 | new name already exists |
  | 2 | bad name (empty or >11 chars) |

- **Clobbers:** A, X, Y, `kPtr`, `srcPtr`, `kArg`+0…+6; `reuFsName`,
  `reuFsFlags`, `reuFsFile`, `reuFsLen` (kernel FS state).
- **Notes:** renaming a file to the same name is a no-op that returns
  C = 0.

### `kReuDirEntry` — read a single directory entry

- **Input:**
  - A = entry index lo, X = entry index hi (0/1) → index 0–511
  - `kPtr`/`kPtr+1` = C64 buffer for the name (12 bytes: 11 chars + NUL)
- **Output:** C = 0 success — buffer filled, `kArg`/`kArg+1` = size,
  `kArg+2` = flags, `kArg+3`/`kArg+4`/`kArg+5` = data offset lo/mid/hi
  (24-bit, file entries). C = 1 entry ≥ 512, empty slot (size 0), or FS
  disabled.
- **Clobbers:** A, X, Y, `kArg`+2…+7.
- **Notes:** entry 0 is the allocator info slot — it returns the
  allocator's `nextFreeOffset` (24-bit) in `kArg+3`/`+4`/`+5` and writes
  `"(free)"` into the name buffer. Callers compute free space as
  `capacity − nextFreeOffset` (3-byte `reuFsCapacity` − `kArg+3/4/5`).
  Iterate entries 1… until C = 1 to list the directory.

## In-place file I/O (fixed-size data files)

Four entries for create/open/read/write of **fixed-size** data files. A
file's size is set at creation and never changes (no append/resize/truncate;
max 65535 bytes). `kReuOpen` resolves the name once and writes a 5-byte
**file record** into caller-owned memory:
`[size lo, size hi, base lo, base mid, base hi]` (16-bit size + 24-bit base).
`kReuReadAt`/`kReuWriteAt` take a pointer to that record, so the directory
is scanned **only at open** — reads/writes do no directory DMA.

### `kReuCreate` — create + zero a fixed-size file

- **Input:**
  - `kArg`/`kArg+1` = filename pointer (screen codes, 1–11 chars)
  - `kArg+2`/`kArg+3` = size (16-bit, > 0)
- **Output:** C = 0 created (zeroed). C = 1 error, code in `kArg+6`:

  | Code | Meaning |
  |---|---|
  | 0 | duplicate name |
  | 1 | no space left in FS |
  | 2 | directory full |
  | 3 | name too long (>11 chars) |
  | 4 | empty name |
  | 5 | zero size |

- **Clobbers:** A, X, Y, `kArg`+0…+7; `reuFs*` state.
- **Notes:** zeroes the new region via multi-bank `kReuFillReu` chunks.
  ⚠️ **It hands back no file record** — only the carry. A caller that means to
  write into the file it just made needs the record, so it must `kReuOpen` the
  name again (`kReuOpen` doubles as the existence check and cannot fail here).
  Creating over an existing name is refused (code 0), and `kReuDelete` does not
  free the slot or the data — a delete is a tombstone — so a caller that may
  overwrite should `kReuOpen` first and write in place when the size already
  matches.

### `kReuOpen` — resolve name → file record

- **Input:**
  - `kArg`/`kArg+1` = filename pointer (screen codes)
  - `kPtr`/`kPtr+1` = 5-byte record buffer (caller-owned)
- **Output:** C = 0 — record written (`size` 16-bit + `base` 24-bit).
  C = 1 not found / FS disabled (`kArg+6` = 6).
- **Clobbers:** A, X, Y, `kArg`+0…+7, `srcPtr`; `reuFs*` state.
- **Notes:** doubles as the existence check (there is no separate
  `kReuFileSize`).

### `kReuReadAt` — read at a 16-bit position (EOF-clamped)

- **Input:**
  - `kArg`/`kArg+1` = record pointer
  - `kArg+2`/`kArg+3` = pos (16-bit, intra-file)
  - `kArg+6`/`kArg+7` = len (16-bit)
  - `kPtr`/`kPtr+1` = C64 destination
- **Output:** C = 0 — `kArg+6`/`kArg+7` = actual bytes read. **0 = EOF**
  (`pos ≥ size`); `< len` = the request ran off the end (clamped).
  C = 1 FS disabled (`kArg+6` = 6).
- **Clobbers:** A, X, Y, `kArg`+0…+7, `srcPtr`; `reuFs*` state.

### `kReuWriteAt` — write at a 16-bit position (past-EOF rejected)

- **Input:**
  - `kArg`/`kArg+1` = record pointer
  - `kArg+2`/`kArg+3` = pos (16-bit)
  - `kArg+6`/`kArg+7` = len (16-bit)
  - `kPtr`/`kPtr+1` = C64 source
- **Output:** C = 0 written. C = 1 error, code in `kArg+6`:

  | Code | Meaning |
  |---|---|
  | 6 | FS disabled |
  | 7 | range past EOF (`pos + len > size`) |

- **Clobbers:** A, X, Y, `kArg`+0…+7, `srcPtr`; `reuFs*` state.
- **Notes:** all-or-nothing — a rejected write leaves the file untouched.
