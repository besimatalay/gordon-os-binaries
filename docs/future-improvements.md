# GordonOS — Future Improvements

> Work that is **not built yet.** Anything already implemented is documented
> where it lives: [`kernel.md`](kernel.md) for the kernel API,
> [`programmers-guide.md`](programmers-guide.md) for task authoring, and
> [`dynamic-libraries.md`](dynamic-libraries.md) for libraries.
>
> What the system cannot do today — including the limits that are staying, not
> just the work in progress — is [limitations.md](limitations.md).
>
> Section numbers are document order, not priority — see
> [Recommended order](#recommended-order).

## Roadmap

### 1. SEND/RECEIVE IPC — the missing half

**Effort:** Medium-Hard

[`ipc.lib`](lib-ipc.md) is the primitive today: four fixed 128-byte rings in the
library's own data (`kIpcPost`/`kIpcPick`, calls 35/36, `X` = channel),
single-producer / single-consumer, shared by every declaring task with no kernel
buffer, no new syscall and no caller zero page. `kIpcPost` blocks while a ring is
full; `kIpcPick` never blocks. What is missing, in order of usefulness:

1. **A library-side semaphore.** The kernel's counting semaphores (syscalls 10/11,
   indices 1-3, owner-tracked, released on task death) cover a mutex between two
   tasks, and `semCount`/`semOwner` are published in `kernel-data.inc` so a task
   sets its own initial count with one store. A semaphore living in
   [`ipc.lib`](lib-ipc.md)'s own data would remove the last kernel dependency, but
   it needs a death story: a task that dies holding a library semaphore leaves it
   locked, because the kernel's death-release scan only knows its own
   `semCount`/`semOwner` pool. The library would have to be told, or the pair
   would have to elect a survivor. The design is the blocker, not the space: the
   `LIB_CALLS` **growth reservoir is spent**, so a library semaphore needs its own
   call index (a dispatching entry, or a relocation of the two `LIB_CALLS`
   tables).
2. **Channel allocation.** The four channels are fixed and anonymous, so a pair
   cannot claim one for itself and the kernel cannot tell when an owner dies.
   Numbering is not the gap — allocation and ownership are.
3. **Message boundaries, and a wakeup.** A ring carries bytes with no framing,
   and `kIpcPick` never blocks on purpose (a dead producer must not strand a
   consumer), so a consumer polls — up to a jiffy of latency per byte.

**Unbuilt design — a blocking, zero-copy handoff.** Each task gets a message
queue; `send(target, msg_ptr)` blocks until the receiver calls
`receive(buf_ptr)`, and both block until the handoff completes — no buffering, no
copying. The kernel mediates by swapping message *pointers*.

- Per-task `waitingSender` / `waitingReceiver` fields (2 bytes each)
- `send(tid, msgPtr)` — if the receiver is waiting in `receive`, hand off
  immediately; otherwise block
- `receive(bufPtr)` — if a sender is waiting, hand off immediately; otherwise block
- Zero-copy: the message pointer is passed, not the data

It fits because each task already has a 256-byte stack saved and restored by REU
DMA: the per-task fields slot into existing kernel data arrays, and no buffer has
to be allocated.

---

### 2. Signals

**Effort:** Medium

A task registers a signal handler address and mask. Another task (or an IRQ handler) calls `sendsig(tid, signal)` which sets a bit in the target's pending-signal bitmap. When the target is next scheduled, the kernel patches in a call to the signal handler before resuming normal execution.

**Signal types:**

| Bit | Name | Purpose |
|---|---|---|
| 7 | SIG_INT | Allow blocking syscalls to be interrupted (returns E_INT) |
| 6 | SIG_CHLD | Thread-spawned child task has terminated |
| 3-0 | SIG_USR1-4 | User-defined signals |

**Why it matters:** `kReadString` and `semWait` block forever — no timeout and no cancellation. SIG_INT makes them interruptible; SIG_CHLD lets a parent learn a child exited without polling `ps`.

---

### 3. Stream Abstraction

**Effort:** Medium (~100 lines)

`GETC`/`PUTC` on named streams. Decouples I/O from hardware and enables shell pipelines.

**Design:**
- Stream table: 8 streams, each with a read-end task and write-end task
- `openStream(readTid, writeTid)` — creates a pipe between two tasks
- `putc(streamNum, char)` / `getc(streamNum)` — blocking read/write on a stream
- Shell keyboard → stream 0 (stdin), shell screen ← stream 1 (stdout)
- Enables: `ls | grep foo | wc`

---

### 4. Blocking I/O & Device Drivers

**Effort:** Hard

Allow tasks to block waiting for I/O (keyboard, serial, disk) instead of polling. The scheduler skips BLOCKED tasks. When I/O completes (via IRQ), the waiting task is unblocked.

**Design:**
- `BLOCKED` state + `blockReason` (keyboard, timer, message, etc.)
- IRQ handlers unblock waiting tasks
- Abstraction: `read`, `write` syscalls
- All blocking calls should be interruptible via SIG_INT (see §2)

---

### 5. File System (IEC / Disk)

**Effort:** Very Hard

Read/write files on 1541/1581 disk drives via the IEC serial bus. Would need a from-scratch bit-banging implementation since KERNAL ROM is banked out.

---

### 6. Crash Protection

**Effort:** Hard

If a task crashes (BRK instruction, invalid memory access), the kernel catches it instead of the whole system dying. IRQ handler checks B flag in saved SR; if set, task caused BRK → kill it.

---

### 7. Extended Task Workspace in REU

**Effort:** Medium — needs an REU region carved out of the FS band

General-purpose REU DMA is available to any task today: `kReuToC64` / `kReuFromC64`
take a 24-bit REU address and a length, so a task can keep state in the REU
without new kernel support. What is missing is an **allocator** and a region to
allocate from: bank 0 holds the stack images, shadows and the bounce buffer,
bitmap slots start at bank 1, the filesystem owns banks 5-251 and the malloc
shadow banks 252-255, so a task may only DMA where the kernel already knows
about it.

**The region is a bookkeeping change, not a hardware limit.** The FS band is
vastly under-used — ~147 KB of files inside a region that spans bank 5 to bank
251 — so shortening `REU_FS_*` (or moving the FS up) frees contiguous banks for
anything that needs one. The cost is the capacity formula (`reu-fs.inc` — bank 5
contributes `REU_FS_BANK5_CAP` and each later bank adds its own), `memory-map.md`
and a REU re-seed. That is the donor route for this section and for §8/§9.

The sketch below is the shape it would take, given a region:

| Task | Stack (REU) | Workspace (REU) |
|---|---|---|
| Task 0 | `$000000` | `$001000` |
| Task 1 | `$000100` | `$002000` |
| Task 2 | `$000200` | `$003000` |

**Design:**
- Workspace size: 4KB per task by default (configurable via `REU_WS_SIZE`)
- Task workspace offset = `REU_WS_BASE + (taskIndex × REU_WS_SIZE)`
- The offsets above are illustrative and collide with the live layout, so the
  first step is naming the region to give up — the FS band is the obvious donor

---

### 8. REU-Based IPC Shared Buffer

**Effort:** Medium — takes two of the FS band's banks (§7)

A REU region used as a shared message ring buffer for inter-task communication.
Pairs with §1.

[`ipc.lib`](lib-ipc.md) keeps its four 128-byte rings in the pool deliberately:
a byte costs a `sta` there, while a REU round trip would dominate the transfer.
The REU pays off for **large** messages — sprites, screen regions, audio — where
a DMA beats a copy loop.

```
REU $010000-$01FFFF: 64KB IPC region
  - Ring buffer with head/tail pointers in kernel data
  - Tasks DMA messages in/out of REU
  - Much larger messages possible (sprites, screen regions, audio)
```

The addresses above sit inside the bitmap-slot band, so this takes its region
from the FS band the same way §7 does.

---

### 9. RAM Disk / Sector Cache

**Effort:** High

Use REU as a disk sector cache for the planned IEC filesystem (§5).

```
REU $020000-$02FFFF: 64KB sector cache (256 × 256-byte sectors)
```

**Design:**
- DMA entire 1541 disk tracks into REU for instant access
- LRU or simple ring-buffer eviction policy
- Swap DMA (`$92`) could implement copy-on-write buffering
- The range above sits inside the bitmap-slot band, so it comes out of the FS
  band as in §7

---

### 10. Char Cache for Text Surfaces

**Effort:** Medium (designed, not built)

**Motivation.** A non-displayed surface does not scroll. `printChar`'s wrap path
clamps the cursor at the region bottom instead of scrolling when the target
surface is not the displayed one, so a task that prints more than a screenful
while it is in the background keeps overwriting its bottom row instead of keeping
scrollback. Bulk output on the *displayed* surface is slow for the same reason —
every glyph is a pixel blit, so 100 lines of `dir` cost ~1.5-2 s.

**Mechanics:**
- 1KB char-code cache + 25-bit dirty mask per text surface (kernel data)
- Not displayed: print updates the cache + the dirty bit; scroll rotates the
  cache pointer (free); no pixel traffic
- On display-switch: rasterize the dirty rows into the slot (~150 ms one-time),
  then DMA the slot into the framebuffer (~10 ms)
- Displayed: unchanged fast path
- Cost: 1KB + 4B per screen-owning task — additive, no change to the displayed path

---

### 11. Editor Undo / Redo

**Effort:** Medium-Hard (designed, not built)

**Want.** Undo and redo in `edit.tsk` ([edit.md](edit.md)) covering every mutation — typing, overtype,
backspace, RETURN split/join, the line cascade, insert/delete line, paste, cut and
clear — with "a new edit after an undo discards the redo tail" and a "nothing to
undo" report at the oldest slot.

**Chosen model: full-state snapshots in a reserved REU arena, not an inverse log.**
The document is *lossy* at several mutation sites: `edCascDelDone` discards the
character rolled off a full line, `edInsOverflow`'s full-line branch overwrites the
tail character, and its pool-full path drops the overflow character outright. An
inverse log would have to capture every discarded byte and invert splits, joins,
chunk grow/shrink and clipboard spans. A snapshot never inverts anything — one
commit hook per mutation entry point instead of a bespoke inverse per operation —
and with ample REU the storage cost is irrelevant, so it is also the smaller design.

**Shape**

- **Arena.** Reserve a REU region by shortening the FS data region (e.g. banks
  240-251, 768 KB; the FS keeps banks 5-239). The FS allocator is monotonic and
  never reclaims, an FS-backed scratch file caps at 65535 B (≈ 7 snapshots) and
  would show up in `dir`; a reserved arena has no ceiling, no allocator
  interaction and no directory footprint. Costs the capacity formula, the
  reserved-bank asserts and `memory-map.md`; REU images must be re-seeded.
  Cheaper fallback: a reuse-if-present scratch file per instance (the `basicwrk`
  pattern).
- **Slot.** 32-byte header (version, `chunkCount`, `ED_LINES`, `ED_SIZE`, `ED_WIN`,
  `ED_CURL`, `ED_CURC`, `ED_PREFC`, `ED_MOD`, 8 chunk pointers, slot length) plus
  `chunkCount × 1024` bytes of chunk payload. 1 KB per undo level for a one-chunk
  document, ~8 KB for a full 192-line one — depth adapts inversely to document
  size. Chunks are dumped whole, so each transfer is one aligned 1 KB DMA.
- **Ring.** `ED_UPOS`/`ED_UCOUNT` plus a restore-in-progress guard in the instance
  buffer (~5 B; `data_size` 207 → ~212 of a 704 B heap). Snapshot *before* each
  mutation; undo restores `POS−1`, redo `POS+1`; load and new-file push the
  initial state, so undo reaches the file exactly as it was opened.
- **Routines.** `edUndoEnable` (arena + initial state), `edUndoCommit` (write the
  current state), `edUndoRestore`, `edUndoRun`, `edRedoRun`. `edUndoCommit` is
  called before the mutation from `edInsChar`, `edOvChar`, `edDelDispatch`,
  `edReturn`, `edCascadeStep`, `edInsOverflow`, `edInsLine`/`edDelLine`
  (interactive only, never from a restore), `edPaste`, `edCutDelete` and
  `edClear`.
- **Bindings.** STOP+U (`$15`) = undo, STOP+R (`$12`) = redo; both screencodes are
  free.
- **Cost.** A full 8 KB snapshot is ~8 ms at 1 byte/cycle — cheaper than the screen
  redraw the editor already does per keystroke, so per-keystroke snapshots are
  affordable.

**Traps.** Undo can need *more* chunks than are currently allocated (undoing a
large delete that shrank the document), so the restore either grows chunk by chunk
or all 8 chunks are pre-allocated when undo is enabled (32 pages). Undo must cancel
an active selection. The clipboard is deliberately outside history, so "undo a cut,
then paste" duplicates text. `ED_MOD` needs either an unconditional set or a saved
clean position that clears it.

**No new kernel calls** — `kReuToC64`/`kReuFromC64` (or `kReuWriteAt`/`kReuReadAt`
if the arena is exposed as a file) are enough.

**Done when:** undo/redo work for every mutation, including the lossy cascade paths
and across chunk grow/shrink boundaries, with no pool or arena leaks.

---

### 12. REU FS Directories

**Effort:** Medium (traversal API) / Hard (subdirectories) — designed, not built

**Today the filesystem is a flat namespace of 512 fixed 32-byte entries** in bank 5
(`$9000-$CFFF`) plus a 24-bit data region from `$D000`. Every consumer walks the table
itself: `kReuDirEntry` reads entry *n* by index, and the callers (`dir`, `del`, `type`,
`copy`, BASIC's `DIR`) loop `n = 1, 2, ...` until it returns C=1. That works, but it
makes every consumer a directory scanner and leaves no room for a path.

**1. Traversal API — `kReuOpenDir`/`kReuReadDir`/`kReuCloseDir`.** Open/read/close,
mirroring POSIX `opendir`/`readdir`/`closedir`, so a caller iterates without knowing
the table layout:

```
// kReuOpenDir  — begin traversal
// Input:  kPtr/kPtr+1 = path (a directory, e.g. "/")
// Output: C=0 opened (handle kept in the kernel), C=1 not found / not a directory
//
// kReuReadDir  — next non-deleted entry
// Input:  kPtr/kPtr+1 = C64 buffer, 13 bytes or more (12 chars + null)
// Output: C=0 filled (kArg/kArg+1 = size, kArg+2 = flags),
//         C=1 end of directory, or no open handle
//
// kReuCloseDir — end traversal, free the handle
```

One **global** handle — single-threaded traversal, matching the rest of GordonOS (one
`kReadString` buffer, one `reuDirBuf`). The read step skips deleted entries (flags b7).
The scan itself already exists inside `kReuDirEntry`, so this is mostly saved cursor
state plus three jump-table entries — and the band has **no** spare slot left (`$E0F3`
holds `kPrintGlyphAt` and `$E0F6` `kMouseCall`), so each of these entries needs a home
outside the `$E000` table.

**2. Subdirectories.** The design is Lee Davison's ROM FS model (`reference/filesys.asm`)
— already the source of the entry format and `kReuCmpName`. A directory is an entry with
the directory bit set whose payload is a *pointer list* to its children in the REU data
area rather than in the fixed table: files keep their 32-byte entry, directories get one
indirection. `LAB_find`/`LAB_directory` port to `reuPathFind` (a '/' -separated path
walker, ~120B) plus `reuDirStep`/`reuNextEntry`, and two new calls: `kReuMkDir` (a header
plus an empty pointer list) and `kReuRmDir` (mark deleted, refusing a non-empty
directory). A name then identifies a path rather than a leaf, so every existing caller —
`run`, `save`, `load`, `del`, `dir`, BASIC's `DIR` — becomes a path consumer.

**Sequencing:** do (1) first — it is useful on its own and it is the traversal primitive
(2) needs.

## Recommended order

| Priority | Idea | Effort | Why |
|---|---|---|---|
| **1** | Signals (§2) | Medium | Makes blocking calls interruptible — `kReadString`/`semWait` have no timeout and no cancellation |
| **2** | SEND/RECEIVE IPC (§1) | Medium-Hard | The byte channels exist; this adds framing, a wakeup and a blocking handoff |
| **3** | Stream abstraction (§3) | Medium | Pipelines, stdin/stdout |
| **4** | Blocking I/O (§4) | Hard | A BLOCKED state and IRQ-driven wake |
| **5** | Extended REU workspace (§7) | Medium | Per-task private RAM in REU — the region comes from the FS band |
| **6** | REU IPC buffer (§8) | Medium | Large shared memory for IPC — same FS band |
| **7** | Crash protection (§6) | Hard | BRK handler, graceful task death |
| **8** | File system (§5) | Very Hard | IEC disk I/O |
| **9** | RAM disk (§9) | High | REU sector cache, depends on §5 |
| **10** | Char cache (§10) | Medium | Background scrollback and bulk-output latency |
| **11** | Editor undo / redo (§11) | Medium-Hard | The editor has no history — every mutation is final; design is settled, code is not written |
| **12** | REU FS directories (§12) | Medium / Hard | A flat 512-entry namespace: every consumer scans the table itself, and there are no subdirectories |
