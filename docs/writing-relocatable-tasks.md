# Writing Relocatable Tasks for GordonOS

> Audience: someone writing a **new task or command** for GordonOS in 6502
> assembly. Everything here is about producing a *relocatable* binary that
> `run`, the shell, and the dynamic loader can place anywhere in the pool.
>
> This document is the single place for: the task header, the fixup table, the
> build pipeline and the two task flavours (`.tsk` and `.com`). The kernel
> surface API itself (screen, keyboard, strings, math) lives in
> **[kernel.md](kernel.md)**; the library APIs in
> **[dynamic-libraries.md](dynamic-libraries.md)** and the `lib-*.md` files.
>
> **New to this?** **[tutorial.md](tutorial.md)** walks the same material one
> runnable step at a time. This document is the reference that walkthrough lands on.

---

## Contents

1. [Two kinds of task: `.tsk` and `.com`](#1-two-kinds-of-task-tsk-and-com)
2. [How a relocatable binary is laid out](#2-how-a-relocatable-binary-is-laid-out)
3. [How fixups are applied at load](#3-how-fixups-are-applied-at-load)
4. [Header field reference](#4-header-field-reference)
5. [Flags](#5-flags)
6. [Declaring libraries (`libMask`)](#6-declaring-libraries-libmask)
7. [Rules that apply to every task](#7-rules-that-apply-to-every-task)
8. [Part A — writing a `.tsk` task](#8-part-a--writing-a-tsk-task)
9. [Part B — writing a `.com` command](#9-part-b--writing-a-com-command)
10. [Adding the task to the build](#10-adding-the-task-to-the-build)
11. [Testing it on the machine](#11-testing-it-on-the-machine)
12. [Troubleshooting](#12-troubleshooting)
13. [Checklists](#13-checklists)
14. [Reference tables](#14-reference-tables)

---

## 1. Two kinds of task: `.tsk` and `.com`

Both are the *same* kind of binary — a relocatable dynamic task loaded from
the REU filesystem into pool pages. The difference is **who spawns it and how
long it lives**:

| | `.tsk` (task) | `.com` (shell command) |
|---|---|---|
| Started by | `run <name>`, `boot.bat`, `spawn`, `threadSpawn` | a command word typed at the shell prompt |
| Lifetime | stays until it `exit`s or is `kill`ed | runs once and `exit`s; the shell waits for it |
| Screen | its own surface (`kAllocScreen`), or the shell's | **shares the shell's surface** (`kShareScreen`) |
| Arguments | optional, via `KF_TAKES_ARGS` (instance buffer) | always via the shell's `cmdArgsBuf` |
| Source dir | `src/tasks/dynamic/` | `src/tasks/cmd/` |
| FS name | `<name>.tsk` | `<name>.com` |
| List in `ps` | yes | only while running |

**Rule of thumb:** if it leaves something running, it is a `.tsk`; if it does
a job and comes back, it is a `.com`.

You never type the extension: `run hello` looks up `hello.tsk`, and the
command word `hello` looks up `hello.com`. `run` rejects an explicit
extension with `? run: no extension`.

---

## 2. How a relocatable binary is laid out

A task binary is a **256-byte header page** followed by the **code body**:

```
file offset 0                 header page (256 bytes)
             +0    magic "GO"
             +2    flags
             +3    origin (nominal)
             +5    code size
             +7    data_size
             +8    zp_base, zp_len
             +10   libMask (16-bit)
             +12   name_len, then the name bytes
             ...   fixup count, fixup table, sentinel (see §4)
file offset 256               code body  <-- entry point is its first byte
```

The **code body always starts at file offset 256**, in every build variant,
because the wrapper zero-pads the header page. That is why the loader can
copy the body to any page-aligned pool address and only patch high bytes.

**What happens at `run` time:**

1. The loader finds the file in the REU FS and reads the header page.
2. It allocates `code_size` bytes (rounded up to pages) in the pool. A
   relocatable task gets **whatever page the pool has room for**, so the
   address it actually runs at is usually *not* the `origin` in the header.
3. It copies the code body to that address, then walks the fixup table
   adding the page delta `(load_addr - origin)/256` to each listed byte.
   Low bytes never change; only high bytes do. That is the whole trick.
4. It sets up the instance buffer (`data_size`), the per-task ZP region
   (`zp_base`/`zp_len`) and loads the declared libraries (`libMask`).
5. It spawns the task at the entry point = the first byte of the code body.

**What this means for you:** any 16-bit absolute address *inside your own
code* is a relocation site and must be listed in the fixup table. Absolute
addresses to *fixed* things (the kernel jump table at `$E000`, hardware
registers like `$D020`, screen RAM `$0400`) never need fixups. You do not
write the fixup table — the pipeline derives it from three assemblies
(§10).

### 2.1 How relocation works, and what a fixup is

This is the machinery behind the word "relocatable", and it explains most of
the rules in §7.

**The constraint that makes it cheap.** Pool pages are 256 bytes
(`POOL_PAGE_SIZE`, `src/kernel/pool.inc`) and the allocator hands out whole
pages. A task's origin is page-aligned, so the code body — which starts one
page above the origin, at `origin + 256` — is page-aligned too. The loader
therefore never moves code by a partial page: a task runs at
`origin + 256 + k × 256` for some whole number of pages `k`.

**What that means for a 16-bit address.** An absolute address inside your own
image was assembled relative to `origin + 256`. When the loader places that
image at a different page, every such address must change — but only in its
**high byte**, because adding a whole number of pages never touches the low
byte. So the loader needs to know exactly one thing: *which bytes of the code
are the high bytes of in-image addresses*. Those bytes are the **fixups**.

Worked example. A wrapper declaring `origin = $5000` is assembled with its code
at `$5100`, and the body contains `lda #>msg` where `msg` lands at `$5120`:

- the assembler emits `A9 51` — `51` is the high byte of `$5120`
- the pipeline records the offset of that `51` byte in the fixup table
- the loader places the code at `$6300` instead, so
  `delta = load_hi − (origin_hi + 1) = $63 − $51 = $12`
- it finds that byte and writes `$51 + $12 = $63`, so the instruction now reads
  `A9 63` = `$6320` — the same label, at its new address

**The delta is one byte, and it wraps.** The loader subtracts with `SBC` and
adds with `ADC`, discarding the carry — so a task can also load *below* its
origin. A task declares its nominal origin in the header — say `$C200` — so its code is assembled at `$C300`
(`$C200` plus its header page), while the pool it is loaded into sits at
`$5700-$C3FF`. Placed at `$A900`, say, the delta is `$A9 − $C3 = $E6`
(−26 in 8 bits); `$C3 + $E6` = `$1A9`, and dropping the carry leaves `$A9`.
This works as long as the whole image stays inside one 64 KB address space,
which it always does.

**Why the origin must be page-aligned.** It is what keeps the low byte
constant, which is what makes a fixup one byte and the delta one byte. A
non-aligned origin would mean low bytes change on relocation too, making every
such byte a fixup with its own addend and forcing 16-bit arithmetic per fixup.
It is also why the pool only ever hands out whole pages: `kMalloc`/`kFree` are
page-granular, and no sub-page allocator is offered or planned (see
[`programmers-guide.md`](programmers-guide.md) → Pools).
The loader *enforces* alignment: a non-page-aligned origin is refused with
error 8, `? origin not aligned` (`dynload.inc`: "Origin must be page-aligned
(delta_lo = 0 requirement)").

**What costs a fixup, and what does not.**

| Reference | Fixup? | Why |
|---|---|---|
| `lda #>mylabel` | **yes** | high byte of an in-image address |
| `lda #<mylabel` | no | low byte — unchanged by a whole-page move |
| `.word mylabel` | **one, for the high byte** | little-endian: byte 0 is the low byte, byte 1 the high |
| `jsr kPrintString` | no | the jump table is pinned at `$E000` for everyone |
| `sta $D020`, `$0400` | no | hardware and screen RAM are fixed addresses |
| ZP references | no | zero page does not move |
| branches, immediates | no | no address is involved |

That is why §7 recommends pointing at your data with ZP pointers:
`lda #<msg / sta kPtr / lda #>msg / sta kPtr+1` costs exactly one fixup and
works from any load address, while a table of `.word` addresses costs one per
entry.

**How the fixup table is built.** Not by hand — the pipeline derives it from
three assemblies of the same source (§10):

| Pass | `.pc` | Output |
|---|---|---|
| base | `origin` | `*.base.bin` |
| shift | `origin + $100` | `*.shift.bin` |
| check | `origin + $200` | `*.check.bin` |

Diffing base against shift *reveals* the fixups: a byte that had to change when
the whole image moved up one page is, by definition, a high byte of an in-image
address. The pipeline records every offset where `shift[i] − base[i] == 1`.

**Why three assemblies, and not two.** The first two passes **produce** the
table. The third **tests** it, and testing it needs a different distance,
because a rule cannot be checked against the very data it was derived from:

- **base vs shift** answers *"which bytes are address high bytes?"* — anything
  whose value moved by exactly one page did so because it holds the high byte of
  an in-image address. That is the derivation, and its output *is* the fixup
  table.
- **base vs check** (the source two pages up) answers the two things that
  derivation cannot answer about itself:
  - *"Is every byte you listed really an address byte?"* A genuine one tracks the
    page delta linearly, so it must move by exactly **two** pages when the source
    moves two pages. The pipeline asserts `base[i] + 2 == check[i]` for every
    entry. A byte that merely happened to change by one page fails this.
  - *"Did you list everything that had to be listed?"* Every byte **not** in the
    table must be *identical* in base and check. A position-dependent byte the
    `== 1` detector could not classify — a low byte that moved because an origin
    was not page-aligned, an expression that changes only at certain deltas —
    shows up here, and the build fails with
    `non-fixup byte changed at code offset N`.

The loader never sees the check variant; it needs only the table. The third pass
is a gate on the *people writing the task*, and it costs one extra KickAssembler
run over sources that are already being assembled twice — seconds.

What it buys, concretely:

- Without it the pipeline has a **derivation with no test**. It would still
  build, and a byte it got wrong would surface at run time as a wild pointer or a
  corrupted label — the hardest failure in this system to attribute, because the
  task itself looks correct and the fault moves when the pool layout changes.
- With it, position-independence is **checked for every byte of the code body**
  rather than assumed. For `sidrst`, which carries **0** fixups, this
  check is the only evidence that they are relocatable at all.

Why not simply have the assembler emit the list? KickAssembler emits no
relocation information and cannot enumerate which immediates and data words hold
in-image addresses. Two shifted assemblies plus a checker is the cheapest way to
recover that from the binary itself — and because the table is derived and
checked on every build, it cannot drift out of date the way a hand-maintained
list would.

**How the loader applies them.** After copying the code body from file offset
256 to the pool page, `dynload.inc` computes `delta` and walks the table.

The table lives in the *file*, after the code body, so it is never in the
staged header page: the loader streams it from the REU in chunks of 128 fixups
(256 bytes each) and applies each chunk before fetching the next. For each
entry it reads a 16-bit code-body-relative offset, checks that it lies inside
the code (`offset < code_size`, else error 1 — `? bad task file`), and adds
`delta` to the byte at `code_base + offset`.

Chunking is what removes any ceiling on the count: a task with 2,000
relocations loads the same way as one with none. A wrapper never mentions any
of this — the emitter writes the table and the loader consumes it.

The whole load — code DMA, fixup walk, bounds checks — runs with interrupts
disabled, so a task can never be scheduled half-relocated.

### 2.2 Referencing kernel routines, syscalls and libraries

Task and library sources normally contain **no `.import` lines at all**. The
task pipeline imports the shared files once, before anything is assembled, and
KickAssembler symbols are global across the whole assembly — so re-importing
any of them from a task source is a duplicate-symbol error, not a fresh copy.

| You want to call | Names come from | Notes |
|---|---|---|
| a kernel routine (`kPrintChar`, `kAllocScreen`, `kMalloc`, …) | `kernel/jumptable.inc` — the `k*` constants | imported by the task pipeline |
| a syscall (`SYS_GETTID`, `SYS_SLEEP`, …) | `src/kernel/syscalls.inc` | imported by the pipeline *and* the kernel build |
| the syscall dispatcher | `jsr syscall` — an alias for `kSyscall = $E090` | defined in the pipeline preamble |
| kernel data (`taskState`, `taskParent`, `cmdArgsBuf`, `reuFs*`, `dynTask*`, `curTask`, …) | `src/tasks/kernel-data.inc` | imported by the pipeline |
| pool geometry (`POOL_BASE`, `POOL_PAGES`, `POOL_PAGE_SIZE`, `POOL_END`, `poolAsl`/`poolLsr`) | `src/kernel/pool.inc` | imported by the pipeline *and* the kernel |
| task header ABI (`HDR_*`, `KF_*`, `LIB_*`, `DYN_FLAG_SWAPPED`) | `src/kernel/task-header.inc` | imported by the pipeline *and* the kernel |
| floating-point constants and asserts (`FP_*`, `fpZPFree`, `fpZpDeclared`) | `src/libs/fp.inc` | imported by the pipeline |
| the shared ZP aliases (`dataPtr`, `kPtr`, `srcPtr`, `taskNamePtr`, `spawnPtr`, `kArg`, `screenBase`) | defined at the top of the generated `tools/assemble-tasks.asm` | always available |
| a library's entry points | the same `k*` jump-table constants | a lib-backed entry is patched to the lib routine on load |

Worth knowing:

- The `k*` names exist twice on purpose. `kernel.asm` defines them as real
  labels (`kPrintChar: jmp printChar`) for kernel-internal calls, while
  `kernel/jumptable.inc` defines them as constants for task code. That is also
  why the kernel build cannot import `jumptable.inc` — the names would collide.
- Use the names, not raw addresses: `jsr kPrintString`, never `jsr $E006`.
- Declaring a library you call is a **header field**, not an import: set the bit
  in `libMask` (§6). Importing a lib's constants does not load it.
- Library call references (inputs, outputs, clobbers, errors) are in
  [lib-time.md](lib-time.md), [lib-filesys.md](lib-filesys.md),
  [lib-gfx.md](lib-gfx.md), [lib-fp.md](lib-fp.md), [lib-sid.md](lib-sid.md),
  [lib-mouse.md](lib-mouse.md); the kernel routines
  themselves in [kernel.md](kernel.md).

---

## 3. How fixups are applied at load

The fixup table lives **after the code body**, and the header records where.
The count is a 16-bit word and the `fixup_offset` word that follows it is the
table's own file offset — always `256 + code size`. `dynParseHeader` asserts
that agreement, so a file whose table is not where its header claims is
refused with `? bad task file` rather than loaded with wrong addresses.

There is no ceiling on the count. The table is DMA'd in from the REU in
chunks of 128 fixups (256 bytes at a time), so a task with 2,000 relocations
loads the same way as one with none — which is why no task has to worry about
how many absolute addresses it contains.

Each entry is a code-body-relative offset; the loader adds the page delta to
the byte at that offset, and bounds-checks it against the code size first.

The wrapper never writes any of this by hand: see §4 for the fields and §10
for how the build fills them in.

---

## 4. Header field reference

The wrapper (`src/tasks/dynamic/<name>.asm`) lays this out by hand. Offsets
are file offsets from the start of the wrapper's `...BinStart` label.

| Offset | Size | Field | Notes |
|---|---|---|---|
| +0 | 2 | magic | `HDR_MAGIC` (`$4F47`). **This emits bytes `$47 $4F`** — `$47 'G'` then `$4F 'O'`. Never spell the value out: `.word $474F` emits `$4F $47` and the loader rejects it as a bad magic. |
| +2 | 1 | flags | see §5 |
| +3 | 2 | origin | nominal page-aligned origin, **must match `origin` in `tools/tasks.json`**. The pipeline assembles at `origin`, `origin+$100`, `origin+$200`; this field stays at `origin` in all three. |
| +5 | 2 | code size | `end_label - entry_label`. Exactly this: anything before the entry label is *excluded* (see §7). |
| +7 | 1 | data_size | bytes of per-instance private buffer. `dataPtr` (`$F1/$F2`) points at it. `0` = none. Use it for scratch you want to survive preemption without declaring ZP. |
| +8 | 1 | zp_base | first ZP byte this task wants preserved (see §7) |
| +9 | 1 | zp_len | length of that region; `0` = no ZP save, zero overhead. `base + len ≤ $F0`. The window is **zeroed when your task is spawned**, so you always start on zeros — never on whatever the slot's previous occupant left there. |
| +10 | 2 | libMask | 16-bit little-endian library bitmask; the bits are the `LIB_*` ids (§6) |
| +12 | 1 | name length | bytes in the name that follows |
| +13 | name_len | name | screen codes. Shown by `ps` and used as the shared-code residency key. Keep it ≤ 11 chars. |
| +13+name_len | 2 | fixup count | 16-bit little-endian; the build writes it |
| +15+name_len | 2 | fixup offset | the table's own file offset — always `256 + code size`, which the loader asserts |
| … | — | padding | zeroes up to file offset 256 |
| +256 | — | code body | |
| +256+code_size | 2·F | fixup table | F little-endian words of code-body-relative offsets |
| +256+code_size+2·F | 2 | sentinel | `$FFFF` terminating the fixup list |

`.encoding "screencode_mixed"` must be active when the wrapper's `.text`
name is assembled, so the name is emitted as screen codes.

---

## 5. Flags

Every value in the header is declared in **`src/kernel/task-header.inc`**,
which is imported once by each build — `src/kernel/kernel.inc` for the kernel,
and `tools/gen-task-asm.ps1` (which generates `tools/assemble-tasks.asm`) for
every task and library. Write the names, never the numbers:

```asm
    .word HDR_MAGIC              // +0:  magic 'G','O' (LE)
    .byte KF_RELOCATABLE | KF_NOT_EVICTABLE   // +2:  flags
    .word (1 << LIB_FILESYS)     // +10: libMask
```

Do **not** re-declare any of them in a wrapper: KickAssembler symbols are
global, so a local copy is a duplicate-symbol error. The values in the table
below are for reading, not for copying.

| Flag | Value | Meaning |
|---|---|---|
| `KF_RELOCATABLE` | `$01` | **Required for every task.** Has a fixup table; loadable at any page-aligned pool address. |
| `KF_NEEDS_SCREEN` | `$02` | Task requires an allocated screen. *Defined but not used by any task in the tree today* — allocate explicitly with `kAllocScreen` and check the carry instead. |
| `KF_REENTRANT` | `$04` | Relocatable **and resident**: the first load copies the code into pool pages, later loads of the same name share those pages and only get a fresh instance buffer. `ps` shows `shared`. Use for a task you may run twice (the shell is `$0D`). |
| `KF_TAKES_ARGS` | `$08` | The loader copies up to `MAX_TASK_ARGS` (64) bytes of `run`-supplied arguments into the instance buffer at spawn. Used by `edit`, `gfxdemo`, `godzi`, `granim`, `grpaint`, `grview`, `shell`, `sidplay`, `spirog` — and by nothing else. **Not needed for `.com` commands** — they read the shell's `cmdArgsBuf` instead. |
| `KF_MALLOC_RAM` | `$10` | A **spawn-time** reservation: the loader `kMalloc`s a block of `kArg+2/+3` pages for this task (`? pages required`, error 9, if 0). **Defined but set by no task in the tree** — like `KF_NEEDS_SCREEN` above. It is *not* how tasks get pool memory: that is the **`kMalloc` kernel call** (`$E0AE`), which any task may make whenever it wants and which `banner`, `copy`, `edit`, `godzi`, `gortris`, `grknoid` and `sidplay` all call. The flag is only for a task that needs its pages reserved *before it starts*. |
| `KF_RE_RUNNABLE` | `$20` | Relocatable **multi-instance**: each `run` loads a *fresh* pool copy (no sharing), but a second `run` of the same name is allowed instead of `? already running`. In the tree: `edit`, `fpdemo`, `gfxdemo`, `granim`, `grview`, `maze`, `spirog`, `sprdemo` — and nothing else. **Not** for a task that owns a global resource for the duration — `godzi` holds the SID claim while it runs, and `gortris`/`grknoid` own the display for their whole life and hold their board in their own image, so all three stay single-instance on purpose (a second `run` gets `? already running`, not a second game fighting for the screen). **Sprites are not such a resource**: each task's sprite state is saved with its slot and swapped in with the display, so any number of sprite tasks may run at once (see [lib-sprite.md](lib-sprite.md)). |
| `KF_NOT_EVICTABLE` | `$40` | Pinned — pool eviction will never swap this task out. Use only when cold-restart would lose something the user cares about (`edit` would lose the document it is holding; `gortris` and `grknoid` would each have to restart a live game cold, and each owns the display for its whole life; `godzi` likewise — its music thread and its look would reset mid-show). The whole set is `edit`, `godzi`, `gortris`, `grknoid`. Each pinned task permanently costs its pages. |

**`KF_MALLOC_RAM` versus `kMalloc`.** Both get pool pages; they are two different *moments*. The flag reserves a **second contiguous block at spawn**: the loader counts it into the eviction plan (so `dlPreNeed` includes the RAM), allocates it beside the code block, records its base and length in the instance buffer and frees it with the task. `kMalloc` is a kernel call any task may make at any time.

Choose the flag only when the workspace must exist **before your first instruction**. It makes the spawn **atomic** — code + RAM fit together or the load fails cleanly (`? pages required`, `? no space in pool`) and unwinds — so a startup cannot half-run for want of memory, and the reservation never triggers an eviction of its own because it was planned before the load began. `kMalloc` trades the other way: pages only while you want them, but a full pool makes it **evict another task**, and it clobbers `kArg..kArg+7`. There is also a cap on the reservation (`MAX_MALLOC_PAGES`, error 4).

Every `.com` command in the tree is plain `$01`. That is the right default for
a command: it is short-lived, takes its arguments from the shell, and exits.

Without `KF_REENTRANT` or `KF_RE_RUNNABLE`, a second `run` of the same name is
refused with `? already running`.

> **A task can spawn another task by name, not just the shell.** `kDynLoad` is a
> plain kernel call: point `kPtr` at a buffer holding the FS name,
> null-terminated, followed by the argument string — exactly what the shell
> builds, `"sidplay.tsk\0commodo 2\0"` — then `jsr kDynLoad` with `kPtr` set. On
> success **`X` is the new task's slot**, which is what you watch in `taskState[]`
> or hand to `kill` (on failure `C=1` and `kArg` holds the error; "already
> running" and "pool full" are both transient, and a spawner that retries on a
> cadence absorbs them). ⚠️ **`exit` does not cascade** — a task that exits
> leaves what it spawned running, and only `threadSpawn` children cascade under
> `kill` (syscall.md §0) — so a task that spawns must clean up itself, and should
> check the slot it is about to kill still holds the name it expects (a slot that
> died and was recycled belongs to somebody else). The example in the tree is the
> shell itself (`pcRun`/`pcRunf` build exactly that buffer and load it). Prefer
> a **library** over a spawned task whenever the work is code you can hold —
> `godzi` does this for its music (`sid.lib` from a thread child, `gortris`'s
> arrangement), which costs one
> `libMask` bit and no slot to watch, no re-load cadence and no `sidrst` to
> clean up after a kill. Keep `kDynLoad` for loading something the user asked for by
> name, where its own arguments and screen are the point.
>
> ⚠️ **And if you spawn a THREAD child (`SYS_THREADSPAWN`), reap it before you
> exit.** A thread child has no dyn entry and runs *your* code pages, so it is not
> a tidy-up detail: `kill` cascades over the whole thread subtree, pool eviction
> refuses to swap a task that has live thread children (it kills the subtree
> instead), and `findNextAlive`'s `childGate` holds any thread child whose parent
> has exited or been swapped — so a survivor cannot be scheduled into freed
> pages. It is still never *reclaimed* (it keeps its TCB slot), so the contract
> stands: reap. `godzi`/`gortris`/`ipctest` reap.

### 5.1 Re-runnable vs reentrant — how they differ, and the do's and don'ts

These two flags are the ones people confuse, because both let you start the same
task twice while meaning completely different things.

| | `KF_RE_RUNNABLE` (`$20`) | `KF_REENTRANT` (`$04`) |
|---|---|---|
| Second `run` of the same name | allowed | allowed |
| Code pages | a **fresh copy per instance** — each `run` costs its own pool pages | **one copy shared** by every instance |
| Where private state lives | instance buffer (`data_size`) + declared ZP | instance buffer (`data_size`) + declared ZP |
| `ps` shows | one row per instance | `shared` on the resident copy |
| Pool cost | pages × instances | pages once |
| Keyed by | the dynamic slot | the name of a **live instance** (`findLiveByName`) — derived, never stored |
| Pool eviction | each instance can be swapped out on its own | skipped while more than one instance shares it |
| In the tree | `edit`, `fpdemo`, `gfxdemo`, `granim`, `grview`, `maze`, `spirog`, `sprdemo` | `shell` |

**Re-runnable (`$20`) — do**

- use it for stateless or self-contained tasks: demos, test tasks, anything whose
  only state is in the instance buffer or declared ZP
- use it when you *want* isolation — two copies cannot disturb each other through
  the code image
- budget the pool: five copies of a 10-page task need 50 continuous pages, and
  the allocator only hands out contiguous runs

**Re-runnable — don't**

- don't assume you are alone. Two instances that both write the border, the SID,
  or `$0400` will visibly fight; the last writer wins
- don't treat a shared hardware resource (SID voices, border, a surface you both
  `kShareScreen`) as yours alone
- don't reach for it just to "allow reruns" on a task that must be a singleton
  (a device driver, a daemon with one job) — the default, with no flag, already
  refuses the second `run` with `? already running`, which is what you want
- don't set it on a task whose live footprint is a large fraction of the pool. The
  loader sizes the second load as code + its eager libraries, and `dlEagerLibPages`
  counts a **resident** library in full — so a second instance of a big task can
  evict the first one, and the copy that gets evicted is the one that is *running*
  (`grpaint` before its `KF_NOT_EVICTABLE` flag was set)

```asm
    .byte KF_RELOCATABLE | KF_RE_RUNNABLE
    .byte 0, 0, 0                // data_size, zp_base, zp_len
```

**Reentrant (`KF_REENTRANT`) — do**

- use it when one program should back several tasks and the code is big enough
  that sharing pays — the shell is the reference case (`KF_RELOCATABLE |
  KF_REENTRANT | KF_TAKES_ARGS`)
- keep **all** mutable state in the instance buffer (`dataPtr`) or in declared ZP
- keep the header name unique and stable: it *is* the residency key, so two
  different binaries that declare the same name would share each other's code
- remember the residency table holds **4** records — a fifth distinct reentrant
  binary resident at once gives `? too many shared tasks`

**Reentrant — don't**

- **never keep writable state inside the code image.** Every instance maps the
  same bytes, so a buffer in the code segment is a shared variable, not a private
  one. This is the trap that makes a task "work alone, corrupt in pairs"
- don't self-modify code, for the same reason
- don't put per-instance initialisation in the code image and assume each load
  re-runs it in isolation — the first load DMAs the code, later loads share it
- don't combine `KF_REENTRANT` with `KF_RE_RUNNABLE`: they express opposite
  intents (one shared copy versus one copy each)

```asm
    .byte KF_RELOCATABLE | KF_REENTRANT | KF_TAKES_ARGS
    .byte SHELL_DATA_SIZE        // 105: the shell's whole command block lives here
                                 //      (shell.asm's own constant — your task
                                 //      declares whatever ITS state needs)
```

**Where should my state live?** In order of preference:

1. **Instance buffer** — `data_size` bytes addressed through `dataPtr`. Private
   per instance, works with every flag, survives preemption, no ZP cost. The
   right default.
2. **Declared ZP** — `zp_base`/`zp_len`. Also private per instance, but DMA'd on
   every context switch, so use it only when the code needs ZP addressing modes.
3. **Never** — a label inside the code image, if the task might ever become
   reentrant. With `KF_RE_RUNNABLE` it happens to be private (fresh copy each
   time), which is exactly why the bug stays hidden until someone adds `$04`.

---

## 6. Declaring libraries (`libMask`)

Cold kernel code ships as shared, refcounted `.lib` binaries that are loaded
on demand and released when the last declaring task exits. Declare what you
use in the 16-bit `libMask` at `+10`:

| Bit | Lib | Value | Loading |
|---|---|---|---|
| 0 | `time.lib` | `$0001` | lazy |
| 1 | `filesys.lib` | `$0002` | lazy |
| 2 | `gfx.lib` | `$0004` | eager |
| 3 | `fp.lib` | `$0008` | eager |
| 4 | `string.lib` | `$0010` | lazy |
| 5 | `sid.lib` | `$0020` | lazy |
| 6 | `ipc.lib` | `$0040` | lazy |
| 7 | `sprite.lib` | `$0080` | eager |
| 8 | `mouse.lib` | `$0100` | eager |

`gfx.lib`, `fp.lib`, `sprite.lib` and `mouse.lib` load at spawn; the rest are
pulled in on the first call to one of their entries. The authority is the
`libEager` byte table in `src/main.asm` — `lib 2`, `lib 3`, `lib 7` and `lib 8`
are non-zero there.

⚠️ **Bits 5 and 6 come with caller obligations.** `sid.lib` keeps the player's
state in its own data, but its *scratch* lives in ZP `$02-$0A` — the declaring
task has to declare that window too (a library cannot declare ZP), and it owns
the tune buffer as well. `ipc.lib`'s four 128-byte channel rings are also the
library's own data, shared by every declaring task, and it needs no caller ZP
at all.

```asm
    .word $0012                  // +10: filesys (bit 1) | string (bit 4)
```

Eager libs are loaded before your task is spawned; if one fails to load, the
spawn is rolled back cleanly and the shell reports the error. Lazy libs are
loaded on first call through a self-patching jump entry. If you call a
library routine, you **must** declare its lib, or you will execute a trap
stub.

Full mechanism and how to add a library:
**[dynamic-libraries.md](dynamic-libraries.md)**.

---

## 7. Rules that apply to every task

**The entry label must be the first label in the body.** The header's
`code size` is `end - entry`, and the loader spawns the task at `entry`. Any
helper placed *before* the entry label is not counted in the size field, so
the fixup offsets can exceed the declared code size and the loader rejects
the file with `? bad task file`. Put helpers and constants **after** the
entry point (see the `helloMsg` data at the end of the example in §8).

**Labels are global.** KickAssembler shares one symbol namespace across all
files the pipeline assembles, so every wrapper must use a unique label
prefix: `<name>BinStart`, `<name>Name`, `<name>NameEnd`, `<name>End`, and the
body's own entry label must be unique too. Two files that both define
`start:` will collide at assembly time. (This is why the two worked examples
below use different prefixes — `hello` for the task, `hi` for the command —
rather than both being called `hello`.)

**Do not set `.pc`.** The pipeline sets it from the manifest's `origin`
(`.pc = <origin> + SHIFT`, where `SHIFT` is 0/256/512 for the three passes).
A `.pc` in your source breaks the fixup derivation.

**What costs a fixup.** Every 16-bit absolute reference to something inside
your own image:

```asm
    lda #<msg                    // low byte — never a fixup
    sta kPtr
    lda #>msg                    // high byte — ONE fixup
    sta kPtr+1
    jsr kPrintString             // jump table — no fixup
    sta $D020                    // hardware — no fixup
    bne loop                     // branches — no fixup
```

Point at data with ZP pointers (`kPtr`, `srcPtr`, `dataPtr`) rather than
absolute addressing. A missed one is not a silent bug: the pipeline's
position-independence check fails the build (see §10).

**ZP and private state.** ZP `$00-$01` are the 6510 port registers — never
touch them. `$F0` is `blinkRate`, a kernel global — never use it. `$F1-$FF`
are kernel-owned. If you need ZP state that survives preemption, declare
`zp_base`/`zp_len` and the scheduler DMAs that window to a per-task REU
shadow on every context switch; `zp_len = 0` costs nothing. That shadow is
per-slot and outlives its task, so the kernel **zeroes it when a task is
spawned** — the window you start with is zeros, never the previous
occupant's state. For scratch that
is simpler than declaring ZP, ask for `data_size` and use `dataPtr`.

**Use the named constants for syscalls.** The number goes in A and the kernel
dispatcher is `syscall`. Write `lda #SYS_GETTID` / `jsr syscall`, not
`lda #7` — the `SYS_*` constants live in `src/kernel/syscalls.inc`, which both
the kernel build and the task pipeline import, and they must match the
dispatcher table in `src/kernel/syscall.inc`. Syscalls 8-11 are reserved no-ops
and are deliberately not named. (These are **not** the loader error codes that
`kDynLoad` returns in `kArg` — different numbering at the same values.)

**NMOS 6502 only.** No `phy`, `ply`, `stz`, `bra`. Use `tya; pha` / `pla; tay`.

**Kernel call clobbers are real.** Every kernel routine documents what it
destroys, and the screen output routines (`kPrintChar`, `kPrintString`,
`kNewline`, `kScrollScreen`, `kClearScreen`) clobber A, X, Y, `kPtr` **and
`kArg`**. If you pass something in X to a routine that does not explicitly
preserve X, save it. This is the single most common source of "worked in
isolation, broke in the OS" bugs.

**Every task must be able to end itself.** The shell is **evictable**: another
task's load -- or a `kMalloc` that has to make room -- can swap the shell's code
out, and the kernel only **restores** swapped tasks when a task exits (`dynFree`
runs `dlRestore`). A task that never ends can therefore leave the shell swapped
out and unreachable: there is no prompt, and `ps`, `kill` and `view` are shell
commands, so they are no help. The F-key screen cycle (F1/F3/F5/F7 and their
Shift variants) only changes what you see and where you type -- it does not run
the shell. A command is worse still: the shell waits for a `.com` in `pcFgWait`
until the child's `taskState` is 0, so a command that never exits blocks the
shell outright. A `KF_NOT_EVICTABLE` task adds a second cost: eviction can never
take its pages, so only the task *ending* frees them -- its own `exit`, or a
`kill` from a shell that is still reachable -- and the pool can be unable to fit
anything else for the rest of the session.

End it on a key the user can find, and say so on screen. The tasks in this tree
are the reference:

| task | how the user leaves it |
|---|---|
| `maze`, `gfxdemo`, `fpdemo`, `spirog`, `sprdemo`, `godzi`, `gortris`, `grknoid`, `granim` | `q` |
| `grpaint` | `q` — a second `q` confirms leaving with unsaved work ([gordonpaint.md](gordonpaint.md)) |
| `grview` | any key but `m`, which reinterprets the picture instead |
| `basic` | the `exit` command |
| `edit` | `STOP+Q` (quit), `STOP+X` (save and exit) — see [edit.md](edit.md) |
| the shell itself | `exit` — leaving the last shell warm-reboots the OS |
| every `.com` command | `SYS_EXIT` when its one-shot job is done; `mtest` runs until a key |

`SYS_EXIT` frees your surface and hands the display back, so leaving cleanly is
also what brings the shell back. A deliberately endless task is acceptable only
when it never takes the display and never pins its pages: `clock` (an overlay that
shares its parent's surface and allocates none) is that shape, and so is `sidplay`
with `repeats = 0` (no screen, one tune buffer, `kill`able from the prompt).

**You are in a multitasking system.** No unbounded blocking without yielding
or sleeping, no writing outside your granted memory, no assuming you are the
only writer of a global. Screen output during your timeslice is fine; the
cursor is handled by the kernel (do not manage `cursorOn` yourself when
calling kernel output routines).

### 7.1 Guarding your task with `.assert`

Asserts are the cheapest defence against the failure modes in this document,
because they run **at assembly time** and cost nothing at runtime. Use them for
anything you can compute while assembling: buffer sizes, ZP bounds, flag values,
and the entry-label rule.

**Syntax.** Use the three-argument form:

```asm
.assert "message", expression, expected
```

Two traps:

- the expression must be a **number**, so a boolean comparison has to be wrapped
  as `(condition) ? 1 : 0` and compared against `1`
- the two-argument form is a parser trap — always supply the expected value

A passing assert prints `message=actual (expected)`; a failing one prints
`ERROR IN ASSERTION`. KickAssembler **exits 0 even when an assertion fails**, so
the build scripts wrap every invocation in `tools/kick.ps1`, which turns
`ERROR IN ASSERTION` / `Made N asserts, M FAILED!` into a real build failure. A
green build therefore means your asserts held.

**The four asserts worth writing in a task:**

```asm
// --- in the wrapper, right after the body import -------------------------
// The entry label must be the first label in the body: anything emitted before
// it is excluded from the code-size field and the loader rejects the file with
// "? bad task file". Put a label immediately before the import to pin that.
myBodyStart:
.import source "mybody.inc"
.label myEnd = *

.assert "mytask: entry label must be the first body label", myEntry, myBodyStart

// --- in the body, next to the constants the asserts need -----------------
// Define MY_* in the wrapper so the header fields and the asserts share them.
.const MY_BUF = 0
.const MY_END = MY_BUF + 48          // instance-buffer layout

.assert "mytask: instance layout exceeds data_size", (MY_END <= MY_DATA_SIZE) ? 1 : 0, 1
.assert "mytask: ZP region must stay below $F0", (MY_ZP_BASE + MY_ZP_LEN <= $F0) ? 1 : 0, 1
.assert "mytask: flags must be KF_RELOCATABLE | KF_RE_RUNNABLE", (MY_FLAGS == $21) ? 1 : 0, 1
```

Real examples in the tree: `compact.inc` asserts its instance layout fits
`CMP_DATA_SIZE`; `basic.asm` asserts its ZP range against `$F0` and its flag
value; `edit.inc` asserts its record-chunk arithmetic and clipboard fields;
`shell.inc` asserts its command strings fit in 256 bytes. Libraries ship assert
macros too — `fpZPFree` and `fpZpDeclared` (`src/libs/fp.inc`) check that your ZP
declaration does not collide with the floating-point window.

**What you cannot assert:** the fixup count. It is derived after assembly, so the
generated emitter enforces the only limit instead — a header page too small to
hold the name is refused with `header overflow`.

---

## 8. Part A — writing a `.tsk` task

A `.tsk` is a long-lived task. It allocates its own surface, does its work,
and either loops forever (the timer preempts it) or calls `sysExit`.

### Wrapper — `src/tasks/dynamic/hello.asm`

```asm
// ==========================================
//  hello.asm — "hello" task (relocatable)
// ==========================================
//  Wraps hello.inc — zero changes to the body. The pipeline sets .pc from
//  tools/tasks.json and appends the fixup table, so this file has neither.

.encoding "screencode_mixed"

helloBinStart:
    .word HDR_MAGIC              // +0:  magic 'G','O' (LE)
    .byte KF_RELOCATABLE | KF_RE_RUNNABLE  // +2:  flags
    .word $5000                  // +3:  origin (nominal — match tasks.json)
    .word helloEnd - hello       // +5:  code size = end - ENTRY LABEL
    .byte 0                      // +7:  data_size (0 = no instance buffer)
    .byte 0, 0                   // +8/+9: zp_base, zp_len (0 = no ZP save)
    .word 0                      // +10: libMask = 0 (declare what you call; see §6)
    .byte helloNameEnd - helloName     // +12: name length
helloName:
    .text "hello"
helloNameEnd:
    .word 0                      // fixup_count + fixup_offset — written by the build
    .fill 256 - (* - helloBinStart), 0  // pad the header page: code at offset 256

helloBodyStart:
.import source "hello.inc"
.label helloEnd = *              // the pipeline uses this as the code size

// Build-time guard: the entry label must be the FIRST label in the body.
// Anything emitted before it falls outside the code-size field above, which
// makes the fixup offsets exceed the declared size and the loader rejects the
// file with "? bad task file". See §7.1 for more asserts worth writing.
.assert "hello: entry label must be the first body label", hello, helloBodyStart
```

### Body — `src/tasks/dynamic/hello.inc`

```asm
// ==========================================
//  hello.inc — body of the "hello" task
// ==========================================
//  Owns a surface, prints one line, sleeps, repeats until `q`.
//  A task that owns the display has to be leaveable -- see §7 for why an
//  endless task can strand the shell.

hello:                           // ENTRY — first label in the body
    // --- own a 10KB surface (hires-text, dark grey border on black) ---
    lda #$0b; sta kArg           // border
    lda #$00; sta kArg+1         // bg0
    lda #$00; sta kArg+2         // bg1
    lda #$00; sta kArg+3         // bg2
    lda #0                       // 0 = hires-text surface
    jsr kAllocScreen             // C=1: no free surface slot
    bcs helloNoScreen

helloLoop:
    lda #<helloMsg               // low byte — no fixup
    sta kPtr
    lda #>helloMsg               // high byte — one fixup
    sta kPtr+1
    jsr kPrintString             // note: clobbers kArg, kPtr, X, Y
    jsr kNewline
    lda #50
    sta kArg+1                   // syscall 13 takes its count in kArg+1
    lda #SYS_SLEEP
    jsr syscall                  // sleep ~50 ticks (~0.8s)
    jsr kScanKeyboard            // non-blocking poll: $FF = no key, or not focused
    cmp #$ff
    beq helloLoop
    cmp #'q'                     // q leaves, and the shell comes back with it
    bne helloLoop
    lda #SYS_EXIT
    jsr syscall                  // exit — never returns

helloNoScreen:
    lda #SYS_EXIT
    jsr syscall                  // exit — never returns

.encoding "screencode_mixed"
helloMsg:
    .text "hello from a relocatable task"
    .byte 0
```

**Notes on the example**

- `kAllocScreen` takes the colours in `kArg..kArg+3` and the mode in A
  (0 = hires-text, 1 = mc-graphics). It clobbers A/X/Y/`kPtr`, so do not
  leave anything live in those registers across it.
- A task with its own surface is only *visible* when it is displayed — use
  `view <id>` from the shell, or `kShareScreen` the shell's surface instead
  (that is the `.com` pattern in §9).
- If you want a fixed header or status bar, narrow the scroll region with
  `kSetScrollRegion` and draw the fixed rows with `kPrintCharAt`.
- Do not call `kFreeScreen` in your entry path if the task could be
  pool-evicted and re-entered — `kAllocScreen` is idempotent for restored
  tasks and will re-use the existing surface.
- Sleep (`syscall 13`) or yield (`syscall 3`) rather than spinning if you have
  nothing to do; a tight loop still costs its timeslice and power.
- `kScanKeyboard` is the poll to use for a quit key: it answers `$FF` when there
  is no key **and** when you do not own focus, so a background task cannot
  swallow another task's keystrokes. `kReadKey` instead *pops* one buffered key
  and returns 0 for an empty buffer (a release reads as 0 too), so only use it
  when you are the foreground and every 0 is meaningful.
- `threadSpawn` (`syscall 12`) children are *cascade-killed* when you are
  killed, and `exit` leaves them running as orphans. Pick deliberately.

---

## 9. Part B — writing a `.com` command

A `.com` is a one-shot task the shell runs in the foreground. It shares the
shell's surface, reads its arguments from the shell's `cmdArgsBuf`, prints
what it wants, and **exits**. The shell waits for it and then reprompts.

### Wrapper — `src/tasks/cmd/hi.asm`

```asm
// ==========================================
//  hi.asm — "hi" command (relocatable)
// ==========================================

.encoding "screencode_mixed"

hiBinStart:
    .word HDR_MAGIC              // +0:  magic 'G','O' (LE)
    .byte KF_RELOCATABLE         // +2:  flags
                                 //      (no KF_TAKES_ARGS — see the notes)
    .word $5000                  // +3:  origin (nominal — match tasks.json)
    .word hiEnd - hi             // +5:  code size = end - ENTRY LABEL
    .byte 0                      // +7:  data_size (0 = no instance buffer)
    .byte 0, 0                   // +8/+9: no ZP region
    .word 0                      // +10: libMask = 0 (declare what you call; see §6)
    .byte hiNameEnd - hiName     // +12: name length
hiName:
    .text "hi"
hiNameEnd:
    .word 0                      // fixup_count + fixup_offset — written by the build
    .fill 256 - (* - hiBinStart), 0

.import source "hi.inc"
.label hiEnd = *
```

### Body — `src/tasks/cmd/hi.inc`

```asm
// ==========================================
//  hi.inc — body of the "hi" command
// ==========================================
//  Shares the shell's screen, echoes any arguments, exits.

hi:                              // ENTRY — first label in the body
    // --- find the shell (our parent) and share its surface -----------
    lda #SYS_GETTID
    jsr syscall                  // gettid → A = my slot
    tax                          // X = my slot
    lda taskParent,x             // the shell's slot (set by the spawner)
    tax
    jsr kShareScreen             // X = target; C=1 if it has no surface
    bcs hiNoScreen

    // --- print the greeting on the shared surface -------------------
    lda #<hiMsg
    sta kPtr
    lda #>hiMsg
    sta kPtr+1
    jsr kPrintString

    // --- echo arguments from the shell's cmdArgsBuf -----------------
    lda cmdArgsBuf               // first argument byte
    beq hiDone                   // nothing typed → done
    lda #<hiArgMsg
    sta kPtr
    lda #>hiArgMsg
    sta kPtr+1
    jsr kPrintString

    ldx #0
hiEcho:
    lda cmdArgsBuf,x             // the shell copies the args in, space-separated
    beq hiEol
    jsr kPrintChar               // clobbers kArg/kPtr/X/Y
    inx
    cpx #40                      // never loop past the buffer
    bne hiEcho
hiEol:
    jsr kNewline

hiDone:
    lda #SYS_EXIT
    jsr syscall                  // exit — the shell reprompts

hiNoScreen:
    lda #SYS_EXIT
    jsr syscall                  // exit anyway: never leave the shell waiting

.encoding "screencode_mixed"
hiMsg:
    .text "hi"
    .byte 0
hiArgMsg:
    .text " args: "
    .byte 0
```

### What makes a `.com` different from a `.tsk`

1. **Source goes in `src/tasks/cmd/`**, and the manifest entry names it
   `<word>.com` (§10). The shell appends `.com` itself.
2. **Share the shell's screen** — the `gettid` → `taskParent` →
   `kShareScreen` sequence above. Commands have no surface of their own; if
   you allocate one with `kAllocScreen`, your output is invisible because the
   user is looking at the shell.
3. **Read arguments from `cmdArgsBuf`.** The shell copies everything after
   the command word into that buffer before spawning you. Parse it with an
   index in X or a ZP pointer; commands commonly null-terminate a filename in
   place so they can pass it to filesys calls. Cap names at 11 characters.
4. **Do not set `KF_TAKES_ARGS`.** That flag is for tasks spawned with
   explicit `run <name> <args>`; commands are handed `cmdArgsBuf` by the
   shell and every command in the tree is plain `$01`.
5. **Always `exit`** (`syscall 0`), on every path including error paths. The
   shell is blocked waiting for you — a command that returns with `rts`, or
   loops forever, hangs the prompt.
6. **You inherit the shell's cursor and text colours.** Use the kernel print
   routines and do not manage `cursorOn` yourself; they save/restore it.
7. **Keep it short.** The shell is unavailable until you exit, and the pool
   holds your code the whole time.

---

## 10. Adding the task to the build

The pipeline is driven by **one manifest file**: `tools/tasks.json`. You do
not edit the assembler files.

> The environment that runs this — the toolchain, the three build stages and
the gates a change passes through — is [development.md](development.md).

```json
{ "name": "hello", "source": "src/tasks/dynamic/hello.asm",
  "origin": "$5000", "fsName": "hello.tsk", "kind": "tsk",
  "note": "hello demo task" }
```

| Field | Meaning |
|---|---|
| `name` | label prefix and the temp binary base name (`tasks-out/temp/hello.base.bin` …) |
| `source` | the wrapper `.asm` to import |
| `origin` | nominal origin; must equal the `+4` origin in the wrapper |
| `out` | *(optional)* final binary name under `tasks-out/`, defaults to `<name>.bin`. Only `fplib` needs it (it emits `fp.bin`). |
| `fsName` | the filename inside the REU filesystem (`.tsk`, `.com` or `.lib`) |
| `kind` | `tsk`, `com` or `lib` — grouping/docs only |
| `note` | emitted as the block comment in both generated files |

Then:

```bash
pwsh -NoProfile -File tools/build-tasks.ps1                                 # Linux/macOS
pwsh -NoProfile -File tools/build-reu.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File tools/build-tasks.ps1   # Windows
powershell -NoProfile -ExecutionPolicy Bypass -File tools/build-reu.ps1
```

or in VS Code, the **"Build dynamic tasks + REU"** task, or the
**"Build & Launch with fresh REU"** launch flow (§11.1).

**What `build-tasks.ps1` does**

1. Runs `tools/gen-task-asm.ps1`, which regenerates two files from the
   manifest: `tools/assemble-tasks.asm` and `tools/gen-fixups.asm`. Both are
   **generated — never edit them by hand**; they are checked in so the change
   shows up in review, and the generator only rewrites them when stale.
2. Clears `tasks-out/*.bin` and `tasks-out/temp/*.bin`. Every binary is written
   again below, so a file left by an earlier run — or by an entry that has
   since left the manifest — cannot survive as a stale binary.
3. Assembles `assemble-tasks.asm` three times (`:shift=0/256/512`), writing
   `tasks-out/temp/<name>.{base,shift,check}.bin` for every manifest entry.
   (Why three? See §2.1 — two passes derive the fixup table, the third tests
   it.)
4. Runs `gen-fixups.asm`, which for each task **diffs the three code bodies**:
   every byte where `shift[i] == base[i] + 1` is an absolute high byte and
   becomes a fixup. It then verifies each fixup satisfies
   `base + 2 == check`, and that every *non*-fixup byte is identical in base
   and check. A task that is not truly position-independent **fails the
   build** here rather than misbehaving at runtime.
5. Emits the final binary into `tasks-out/<out>`, printing its code size and
   fixup count.
6. Writes `tasks-out/build.stamp`: a content hash of `tools/tasks.json` plus
   every `.asm`/`.inc` under `src/`, which is the input set the assembly reads
   (a task pulls shared files in with `.import source`). `build-reu.ps1`
   refuses to seed a set the sources have moved on from — see
   `tools/tasks-stamp.ps1`.

`tools/build-reu.ps1` then formats the REU filesystem and seeds every
manifest entry under its `fsName`, plus the fonts, `src/batch/*.bat`,
`src/banners/*.bnr`, `src/corpus/*.bas` and `music/*.mus`. The manifest order
is the order files land in the FS, so append new entries at the end to keep
the image layout stable.

> **Why the assembler files are generated.** KickAssembler needs a distinct
> `.segmentdef`/`outBin` per task, and a segment *name* must be a literal
> identifier — a computed name fails with `Not implemented`, a macro
> parameter as the name expands to `Invalid directive`, and `.import source`
> demands a string constant. So the per-task blocks cannot be produced inside
> the assembler and are emitted as text instead.

---

## 11. Testing it on the machine

1. Rebuild tasks and the REU (above). **No kernel rebuild is needed** — the
   kernel does not embed tasks.
2. Boot. `dir` should list your new `hello.tsk` / `hello.com`.
3. `.tsk`: `run hello`. `ps` should show it with its code address, size and
   pool usage; `view <id>` to look at its surface; `q` on its screen to leave
   (`kill <id>` from the prompt also stops it).
4. `.com`: type `hi world` at the prompt. It should print and return you
   to the prompt.

**Watch out:** the REU filesystem persists. VICE is launched with
`-reuimagerw`, so a session writes the image back and a stale binary can
shadow a fresh build. If you change a task's source and the old behaviour
persists:

- prefer the **"Build & Launch with fresh REU"** flow, which rebuilds
  `reu/REU.bin` before starting VICE, or
- `del hello` in the shell and re-seed, or
- delete `reu/REU.bin` and rebuild it.

A stale **`tasks-out/`** is caught before the image is written: `build-reu.ps1`
refuses to seed when the sources have changed since the last task build, because
the image would otherwise hold the old binary while every other check still
passed — see `tools/tasks-stamp.ps1`.

Also note the loader keys **shared-code residency on the name in the header**,
not the FS filename: if you change a reentrant task's name, remember that
both the wrapper's name and the manifest `fsName` describe the same thing
from different sides.

### 11.1 Driving all of this from VS Code (F5)

Everything above is also one keypress. `launch.json` defines two VICE
configurations, and both are launched with `-reuimagerw`, so the session writes
the REU image back on exit:

| Configuration (Run and Debug view) | Builds first | Use when |
|---|---|---|
| **Build & Launch with REU** | the kernel only (`VS64: Build`) | kernel-only changes; the existing `reu/REU.bin` is current |
| **Build & Launch with fresh REU** | kernel + dynamic tasks + a fresh filesystem (`Prepare fresh REU`) | **you changed, added or removed a task** — this is the one you want |
| **Publish binaries** | the kernel only (`VS64: Build`) | you are publishing: it copies `build/gordon-os.prg` and `reu/REU.bin` into the binaries clone, commits and pushes — a missing artifact is built first |

So the normal loop for task work is: edit your `.asm`/`.inc`, pick **"Build &
Launch with fresh REU"** in the Run and Debug view, press **F5**. The task
binaries are rebuilt, `reu/REU.bin` is regenerated, VICE starts, and you can
`run <name>` at the prompt.

> **The trap:** "Build & Launch with REU" does **not** rebuild dynamic tasks. Use
> it after a task change and you boot the *previous* binary — and because the
> session writes the image back, the stale copy persists. When a change seems to
> have no effect at all, this is why.

The same steps are available individually under **Terminal → Run Task**, which is
handy when you want the output without starting the emulator:

| Task | Runs |
|---|---|
| **Build dynamic tasks** | `tools/build-tasks.ps1` — regenerates both pipeline files from `tools/tasks.json`, then assembles and emits every task |
| **Build REU** | `tools/build-reu.ps1` — reseeds `reu/REU.bin` and `reu/REU-C64U.bin` from `tasks-out/` |
| **Build dynamic tasks + REU** | both, in order |
| **VS64: Build** | the kernel through VS64/Ninja, assert-safe via `tools/kick.ps1` |
| **Prepare fresh REU** | kernel + tasks + REU |
| **VICE with REU** / **VICE with fresh REU** | the two launch flows above, without F5 |
| **Publish binaries** | `tools/publish-binaries.ps1` — no kernel build up front, so whatever is in `build/` is what gets published (a *missing* PRG or REU image is built on the spot); the F5 target always rebuilds first |

Changing only task sources never *requires* a kernel rebuild — the kernel does not
embed task binaries or a seed table.

---

## 12. Troubleshooting

The shell prints a message per loader error code. What to check:

| Message | Loader code | Likely cause |
|---|---|---|
| `? no free dyn slots` | 0 | The dynamic-table is full (8 entries). Kill something and retry. |
| `? bad task file` | 1 | Fixup offset past the end of the code body — nearly always the **entry label is not the first label in the body**, or the `code size` field is wrong. Also: the generated `FF FF` terminator ran past the header page. |
| `? not relocatable` | 2 | The binary's `flags` field does not set `KF_RELOCATABLE`. Every GordonOS task and library must set it — a fixed-address image is refused. |
| `? address in use` | 3 | The task's reserved region overlaps a resident task (e.g. its program-RAM block). |
| `? no space in pool` | 4 | No *contiguous* run of free pool pages large enough. Total free pages is not enough — the pool allocator needs a single run. Kill tasks, or `compact` the FS, or make the task smaller. |
| `? no fs or not found` | 5 | The FS filename does not match — check `fsName` in the manifest (`.com` vs `.tsk`) and that you rebuilt the REU. |
| `? origin not aligned` | 8 | The origin field is not page-aligned. |
| `? pages required` | 9 | `KF_MALLOC_RAM` set with `kArg+2/+3` = 0 pages. |
| `? too many shared tasks` | 10 | The shared-code residency table (4 records) is full of reentrant binaries. |
| `? already running` | 11 | Non-reentrant task, second `run`. Add `KF_RE_RUNNABLE` or `KF_REENTRANT`. |
| `? instance heap full` | 12 | Out of instance-buffer space. Reduce `data_size`. |
| `? no free task slots` | 13 | All 24 task slots are in use. |
| `? no screens available` | — | All 28 REU surface slots are taken (`kAllocScreen` returned carry set). |

Build-time failures you may meet:

| Error | Meaning |
|---|---|
| `: header overflow` | The header page cannot hold the 13 fixed bytes, the name and the 4-byte fixup trailer. Shorten the task's `name`. |
| `: non-fixup byte changed at code offset N` | Your code is not position-independent at that offset — an absolute reference that the diff could not classify (often a 16-bit address written as two separate immediates, or a data table of addresses). |
| `: fixup verify failed at code offset N` | A byte moved by one page but did not move by two in the `+$200` variant — usually an address into a region that is not page-aligned. |
| `Invalid directive`, `Import source must be given a string constant` | You hand-edited a generated file. Regenerate it. |
| `.assert` failures | `tools/kick.ps1` makes them fatal on purpose. Read the assertion message. |

---

## 13. Checklists

**New `.tsk`**

1. `src/tasks/dynamic/<name>.asm` (wrapper) + `<name>.inc` (body).
2. Entry label first in the body; helpers and data after it.
3. Unique label prefix; no `.pc` in the source.
4. Version: `$03` unless you have a reason for `$02`.
5. Flags: `KF_RELOCATABLE` + `KF_RE_RUNNABLE` (or `KF_REENTRANT`); add
   `KF_NOT_EVICTABLE` only if you must.
6. `data_size` / `zp_base`+`zp_len` if you need private or ZP state.
7. `libMask` for every library you call.
8. Allocate a surface with `kAllocScreen` (check carry), or share one.
9. A **quit path** (a key, a command, or a menu action) that ends in `syscall 0`
   — a task that only loops forever can strand the shell (§7).
10. Manifest entry with `kind: "tsk"` and `fsName: "<name>.tsk"`.
11. Build tasks → build REU → `run <name>`.

**New `.com`**

1. `src/tasks/cmd/<name>.asm` (wrapper) + `<name>.inc` (body).
2. Same header rules, flags `$01`.
3. `gettid` → `taskParent` → `kShareScreen` before printing.
4. Arguments from `cmdArgsBuf`; names capped at 11 characters.
5. `syscall 0` on **every** exit path.
6. Manifest entry with `kind: "com"` and `fsName: "<name>.com"`.
7. Build tasks → build REU → type the command word at the prompt.

---

## 14. Reference tables

### Fixup budget

There is no ceiling on the fixup count. The table lives in the file after the
code body and is streamed in 128-entry chunks at load time, so a task with
2,000 relocations loads the same way as one with none.

The only size constraint is the header page itself — `13 + name_len + 4 ≤ 256`
— which the build enforces with `header overflow`, and which no realistic name
approaches.

### Pool

| | |
|---|---|
| Pool base / size | `POOL_BASE = $5700`, `POOL_PAGES = 109` × 256B = 27,904 bytes |
| Origin field | **nominal only.** The loader places the code wherever the pool has room and uses `origin` solely to compute the fixup delta — a task may declare `$C200` and still load into the `$5700-$C3FF` pool. |
| Allocation | **contiguous pages only** — this is why `? no space in pool` can appear with free pages remaining |
| Placement | **task code/RAM/`kMalloc` grow up from the bottom; libraries come down from the top.** An exiting task's pages always rejoin the contiguous task region, and a library can never sit between two task blocks. Neither kind reserves pages, and both directions make the same fit decision — a load fails only when no run of that size exists |
| Diagnosing `? no space in pool` | `pool`'s used/free come from the **tables**, so a correct-looking `pool` with a failing load means *placement*, not shortage. Compare the `pg` column with a fresh boot: a library whose `pg` moved (e.g. `19` → `59`) was freed and re-loaded, i.e. its declaring task was evicted. Check the largest free **run** too — `basic` needs 65 contiguous pages for its code alone |
| Eviction | when a new task does not fit, the loader cold-swaps the largest suspectable task out (its code pages are freed and it is re-loaded on demand at its entry point, losing program state) |

### Surface slots

| | |
|---|---|
| Slots | 28 REU surfaces, 10 KB each |
| Allocate | `kAllocScreen` (A = mode, `kArg` = colours) |
| Share | `kShareScreen` (X = target) |
| Free | `kFreeScreen` — only the owner can free |
| Display | the focused task's surface; `view <id>` / `kSwitchView` to look at another |

### Where things live

| What | Where |
|---|---|
| Task wrapper + body | `src/tasks/dynamic/` |
| Command wrapper + body | `src/tasks/cmd/` |
| Libraries | `src/libs/` |
| Manifest | `tools/tasks.json` |
| Generated: stage 1 / stage 2 | `tools/assemble-tasks.asm`, `tools/gen-fixups.asm` |
| Generator | `tools/gen-task-asm.ps1` |
| Build scripts | `tools/build-tasks.ps1`, `tools/build-reu.ps1` |
| Output | `tasks-out/*.bin`, seeded into `reu/REU.bin` |
| Kernel API | [kernel.md](kernel.md) |
| Syscalls | [syscall.md](syscall.md) |
| Libraries | [dynamic-libraries.md](dynamic-libraries.md) |
