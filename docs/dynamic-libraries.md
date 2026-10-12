# Dynamic Kernel Libraries

> How GordonOS moves cold kernel code out of resident RAM and loads it on
> demand as shared, refcounted `.lib` binaries in the task pool.
> Dispatch is through self-patching jump entries: `libLoad` rewrites the entry in
> place, so a warm call is a 3-cycle `jmp` with no `libVec`/`libFlag` table in
> between.

---

## 1. What they are

A **dynamic kernel library** is a relocatable binary stored on the REU
filesystem (name `<name>.lib`), loaded into the task pool at runtime, and
**shared + reference-counted** across all the tasks that need it. It has no
scheduler slot and no screen — only a pool footprint and a set of public
entry points.

Libraries let the kernel keep only a small **resident core** (scheduler, IRQ,
text output, the loader itself) while cold subsystems move out to the pool:

| Lib | ID | Entries | Load policy | Holds | Consumers |
|---|---|---|---|---|---|
| `time.lib` | 0 | 3 | lazy | `kGetTime` / `kSetTime` / `kPrintTime` | `clock`, `time` |
| `filesys.lib` | 1 | 9 | lazy | `kReuFormat` / `kReuSave` / `kReuDelete` / `kReuRename` / `kReuDirEntry` / `kReuCreate` / `kReuOpen` / `kReuReadAt` / `kReuWriteAt` | shell, `basic`, `banner`, `copy`, `del`, `dir`, `edit`, `format`, `fstest`, `godzi`, `gortris`, `granim`, `grknoid`, `grpaint`, `grview`, `rename`, `sidplay`, `type` |
| `gfx.lib` | 2 | 13 | eager | `kPlot` / `kLine` / `kBox` / `kFillBox` / `kCircle` / `kEllipse` / `kFloodFill` / `kGetPixel` / `kClearBitmap` / `kSetGfxColor` / `kGfxChar` / `kGfxString` / `kFillMatrix` | `basic`, `fpdemo`, `gfxdemo`, `granim`, `grpaint`, `grview`, `spirog` |
| `fp.lib` | 3 | 1 | eager | `fpExec` (FADD / FSUB / FMUL / FDIV / FPOW / FNEG / FABS / FINT / FSGN / FSQR / FEXP / FLOG / FSIN / FCOS / FTAN / FATN / FRND / FCMP / F2FX / AYFC / FMUL10 / FDIV10 / FLOAD / FSTORE / FPI / BYTEF) | `basic`, `fpdemo` |
| `string.lib` | 4 | 7 | lazy | `kStrlen` / `kStrcpy` / `kStrcmp` / `kSkipSpaces` / `kByteToHex` / `kHexDigit` / `kNibbleToHex` | shell, `dir`, `ps`, `del`, `time.lib`, `filesys.lib` |
| `sid.lib` | 5 | 2 | lazy | `kSidPlay` (play a `.mus` tune from RAM, blocking) / `kSidHush` (silence the SID, and stop a running player) | `sidplay.tsk`, plus `gortris`, `godzi` and `grknoid` — the *direct* callers, each from a thread child that declares ZP `$02-$0A` — and any task that declares that window and owns its own tune buffer |
| `ipc.lib` | 6 | 2 | lazy | `kIpcPost` (X = channel, A = byte — push into that channel's ring, blocking while full) / `kIpcPick` (X = channel → A = next byte, `C=1` when empty) | any task pair that declares `libMask` bit 6 — no caller ZP, no filesys needed |
| `sprite.lib` | 7 | 4 | eager | `kSpriteSheet` (bind an FS file as a sprite's sheet) / `kSpriteFrame` (load one 64-byte frame) / `kSpritePos` (place it) / `kSpriteReg` (any shadow field) — plus the resident `kSpriteCollide` | `godzi`, `grknoid`, `grpaint`, `sprdemo` — the display owner's calls; the per-task state is handed over with the display, so two sprite tasks coexist |
| `mouse.lib` | 8 | 1 | eager | `kMouseCall` (`MOUSE_READ` / `MOUSE_ENABLE` / `MOUSE_DISABLE`) — the Commodore **1351** on control port 2, publishing signed deltas against the position it remembers | `grpaint` (its pointer) and `mtest` (the readout). Which pointer this machine has is the kernel's `mouseKind` byte, set by `mouse 1351` — and the library never consults it |

> **`ipc.lib` is the first library that is mostly *state* rather than code.**
> Its four channel rings live in the library's own data, and a library's data is
> **one copy shared by every task that declares the lib** — the same property
> that makes `sidOwner` in `sid.lib` work — so the library is a mailbox between
> task pairs rather than a code-sharing device. It is also the clearest example
> of what that costs: **638 bytes of code and 18 fixups across 3 pool pages**,
> of which 512 are the rings themselves. Full reference:
> [`lib-ipc.md`](lib-ipc.md).

### Giving a library back early — `kLibHold`

A `libMask` is a **lifetime** declaration: a library a task declares stays
resident until that task *exits*, even if the task stopped using it after the
first few instructions. `kLibHold` lets a task say "I am done with everything I
declared except these", so the pages go back at once instead of at exit:

```asm
    lda #(1 << 5)           ; keep sid.lib (id 5) -- (1<<5)|(1<<7) keeps two
    jsr kLibHold            ; and release everything else I declared
```

It **clears the kept bits in the task's stored 16-bit declaration mask**
(`dynTaskLibMaskLo/Hi`), runs the loader's own release path (`dlLibRelease`) — which
walks the mask *stored in the dyn slot*, decrements each library's refcount and frees
the pool pages of any that reaches zero — and then stores the kept bit alone as the
mask ("I hold only these now"). A library another task also declares is safe: the
refcount simply does not reach zero, so its code and pages stay. There is no
failure return and no bad value: A is a mask, so every 8-bit value names a set of
libraries to keep -- bit n is library n, and 0 hands back everything the task
declared.

⚠️ **A released library stops serving the task.** Keep every library the task
still calls in the mask -- a task that drives sprites every frame has to keep the
sprite library, or its per-frame calls do nothing and the sprites freeze on the
last state that was published.

> ✅ **The order of those three steps is the whole routine.** Store the kept bit
> **after** the release walk, never before: `dlLibRelease` walks the mask stored in
> the dyn slot, so a mask already narrowed to "keep sid" makes it release **sid**
> and leave filesys held — and a library reloaded at refcount 0 can never be freed
> again.

> ⚠️ **One-way: do not use a library you have released.** The *code* still works
> — `libFree` restored the entry to its cold stub, so the next call reloads the
> library — but refcounts are taken **once, at spawn, from the binary's
> `libMask`**, so a reload after a release leaves the library **owned by nobody**
> (`libRefCount == 0`). A refcount-0 library is *immortal*: the release path
> refuses to decrement below zero (the underflow guard), so nothing can ever
> free it again and its pages are stranded — until a reboot, and a **warm** one
> reclaims them: `warmBootReset` calls the loader's own `libFree` for every id
> before `jmp start` (`docs/kernel.md`). ≈ 11 pages for
> `filesys.lib`, 13 for `sid.lib`).
>
> This is not new with `kLibHold` — it is what already happened if a task called
> a lazy library's entry **without declaring it**. The system's invariant is
> **"the declaration is the ownership"**. The upside of the same rule is that an
> ownerless library can never be freed *under* a task that is using it.

**The reference consumer is `sidplay.tsk`:** it needs `filesys.lib` for the few
milliseconds it takes to read the tune into RAM, then plays for minutes out of
`sid.lib`, so it keeps only `sid.lib` across the song. **`gortris` and `grknoid`
are the other side of that trade**: both also load their tunes, but neither hands
`filesys.lib` back, because both have to *write* to the REU filesystem later in the
session and `kLibHold` is one-way (see the `HI SCORES` note in
`src/tasks/dynamic/gortris.inc`) — `gortris` writes `gortris.hi` at game over, and
`grknoid` writes `grknoid.hi` while its music child reads a tune file on every mode
switch. Before this call existed
those ~11 resident pages of `filesys.lib` were the one real difference from the
old all-in-one player — and on a loaded system they showed up as the loader
evicting and restoring other tasks around the player: audible gaps in the music.

See also: [`kLibHold` in `kernel-fragmentation.md`](kernel-fragmentation.md)
(where its 38 bytes live) and [`lib-sid.md`](lib-sid.md).

The gfx **LUTs**, `kAllocBitmap`/`kFreeBitmap`, and the text blitter stay
resident — they are shared by resident code or are syscall wrappers.

**Per-library call references** (inputs, outputs, clobbers, error codes —
for programmers writing tasks):

- [`lib-time.md`](lib-time.md) — `kGetTime` / `kSetTime` / `kPrintTime`
- [`lib-filesys.md`](lib-filesys.md) — `kReuFormat` / `kReuSave` /
  `kReuDelete` / `kReuRename` / `kReuDirEntry`
- [`lib-gfx.md`](lib-gfx.md) — `kPlot` / `kLine` / `kBox` / `kFillBox` /
  `kClearBitmap` + stubs
- [`lib-fp.md`](lib-fp.md) — `fpExec` and its 26 opcodes
- [`lib-string.md`](lib-string.md) — `kStrlen` / `kStrcpy` / `kStrcmp` /
  `kSkipSpaces` / `kByteToHex` / `kHexDigit` / `kNibbleToHex`
- [`lib-sid.md`](lib-sid.md) — `kSidPlay` / `kSidHush` (the COMPUTE!'s
  Enhanced Sidplayer; **the caller owns the tune buffer and must declare ZP
  `$02-$0A`**, because a library can declare neither ZP nor a filesys reference)
- [`lib-ipc.md`](lib-ipc.md) — `kIpcPost` / `kIpcPick` (four one-producer /
  one-consumer byte channels whose rings live in the library's shared data, so
  the kernel needs no syscall, no buffer and no new resident code)
- [`lib-sprite.md`](lib-sprite.md) — `kSpriteSheet` / `kSpriteFrame` /
  `kSpritePos` / `kSpriteReg` (all eight VIC sprites, driven by whichever task
  owns the display; the kernel keeps one task's sprite state live and hands it
  over when the display changes hands, so two sprite tasks coexist)
- [`lib-mouse.md`](lib-mouse.md) — the Commodore **1351** (lib 8, call index 41
  `kMouseCall`): the device on control port 2 — the POT registers, the `$DC00`
  multiplexer select, the hold sequence — the `mtest` readout that settles it,
  and the `mouseKind` byte that says whether this machine has one

---

## 2. Task ABI is unchanged — self-patching jump entries

Tasks keep calling the **same fixed jump-table addresses** they always have.
A library call's jump-table entry is a 3-byte `jmp` that `libLoad` patches
**in place** to the lib routine's real address (and `libFree` restores):

- **Eager** (`jmp libTrap` → patched to `jmp gxPlot`) — patched at spawn;
  the initial `libTrap` (`sec; rts`) is a fail-safe if called unpatched.
- **Lazy** (`jmp libStubTimeGet` → patched to `jmp getTime`) — the first
  call cold-loads the lib, then re-enters through the now-patched entry.

```
; eager (gfx):                          ; lazy (time):
kPlot:  jmp libTrap                     kGetTime: jmp libStubTimeGet
```

Warm dispatch is **one direct 3-cycle `jmp`** for every lib call — no
`jmp (abs)` indirection, no `bit`/`bmi` flag test, no `jmp (abs)` NMOS
page-boundary constraint. The lazy cold stub saves `A/X/Y`, `kArg[0..7]`,
`kPtr`, `dataPtr` and `srcPtr` into `libSaveBuf` (via shared
`libColdSave`/`libColdRestore` helpers), calls `libLoad`, restores
everything (the restore is carry-preserving), and `jmp`s through the
now-patched jump entry. A load that **fails** never returns into the command --
see *What happens when a lazy load fails* in section 5.

`libLoad`/`libFree` locate each call's jump entry through the **read-only**
`libJumpLo/Hi` tables (immutable constants, like `libNameLo/Hi`) and write
the `jmp` opcode + target directly into the entry — no writable vector table.

---

## 3. Binary format

A `.lib` is the same paged binary as a `.tsk` — a 256-byte header then the
code. Field +10/+11 (`HDR_LIBMASK`) is a **16-bit little-endian `libMask`**
(bit N = library N — the `LIB_*` ids), and a library's own is structurally 0.

```
+0/+1   magic              .word HDR_MAGIC               (bytes $47 'G' $4F 'O')
+2      flags              .byte KF_RELOCATABLE          ($01)
+3/+4   origin lo/hi       .word $5000
+5/+6   code size          .word gfxEnd - gfxCode
+7      data size          .byte 0                       (libs use none)
+8      zp base            .byte 0
+9      zp len             .byte 0
+10/+11 libMask            .word 0                       (libs declare none)
+12     name len           .byte <len>
+13..   name               .text "gfx"
        fixup count+offset .word 0, .word 0              (written by the build)
        pad to 256         .fill …
```

The library body starts with an **entry table** — `.word` pointers to each
public routine in call-index order. `libLoad` turns those nominal addresses
into live addresses using the same `dlDelta` the fixup engine applies.

Libraries are built by the exact same three-pass assemble → shift → check →
fixup pipeline as tasks (`tools/assemble-tasks.asm`, `tools/gen-fixups.asm`)
and seeded into the REU FS by `tools/build-reu.ps1` (entries named `*.lib`).

---

## 4. Runtime state

Three families of arrays (all in `main.asm`, pinned by `.assert`s):

| Array | Size | Index | Meaning |
|---|---|---|---|
| `libNameLo/Hi` | 16 | lib id | pointer to the `"<name>.lib\0"` kernel string |
| `libEntryCount` | 16 | lib id | number of exposed calls (call-index base) |
| `libEager` | 16 | lib id | non-zero → load at spawn; zero → lazy |
| `libStartPage` | 16 | lib id | `$FF` = not loaded, else first pool page |
| `libPages` | 16 | lib id | pool pages held |
| `libRefCount` | 16 | lib id | resident tasks depending on it |
| `libJumpLo/Hi` | `LIB_CALLS` = 42 (×2 arrays = 84 B) | call index | address of the call's jump entry (read-only) |
| `libInitLo/Hi` | `LIB_CALLS` = 42 (×2 arrays = 84 B) | call index | the entry's initial target — `libTrap` (eager) or the per-call cold stub (lazy) (read-only) |
| *(spent)* growth point | 0 B | — | no `.fill` follows the four tables: `LIB_CALLS` is at its ceiling, so growing the tables by one index moves every pinned address below them (`gfxRowLut*`, the `FONT_*` block, the task shadows) by 4 bytes |

**Call-index rule:** a lib's calls start at `sum(libEntryCount[0..id-1])`.
`LIB_CALLS = 42` (`main.asm`), and the indices are allocated
`time`=0–2, `filesys`=3–11, `gfx`=12–24, `fp`=25 (one entry, reached at the
fixed `kFpCall` jump entry `$E113`), `string`=26–32, `sid`=33–34
(`kSidPlay`/`kSidHush`), `ipc`=35–36 (`kIpcPost`/`kIpcPick`),
`sprite`=37–40 (`kSpriteSheet`/`kSpriteFrame`/`kSpritePos`/`kSpriteReg`),
`mouse`=41 (`kMouseCall`) —
**all 42 indices are in use, and the tables now end flush against `gfxRowLutLo`,
so a further call needs a dispatching entry rather than an entry
per call** (`fpExec`/`kFpCall` is the pattern). `libJumpLo/Hi` hold the
jump-entry address for each call index and `libInitLo/Hi` its restore target,
so the jump entries stay **scattered** (`kStrcmp` at `$E107`, `kFillMatrix` at
`$E10A`, `kFpCall` at `$E113`) — and a new call's entry does not have to sit in
the `$E000` table at all: that table is full (its only free byte is `$E119`),
which is why the five `kSprite*` stubs live in the `$CDDE` pocket instead and
the `sid.lib` and `ipc.lib` entries went to the free block at `$FF7E`.

> ⚠️ **The call-index space is the ceiling here, and it is spent.** The four
> scan tables are `LIB_CALLS` wide and carry one index per library **call**, so
> the cap counts calls, not libraries. **The load policy is irrelevant to it:**
> `libEager` only decides whether a library loads at spawn or on its first call,
> while an index is consumed per **call**, so an eager and a lazy library need one
> just the same. The library **IDs** are *not* the constraint — `MAX_LIBS = 16`
> with ids 0–7 used leaves 8 free, so a library can be declared long before its
> calls fit.
>
> #### A lazy library's cold stubs need a home too
>
> A lazy library needs room for its call entries **and** their cold stubs: the
> `$E000` table is full, and `libstubs.inc` (the cold stubs for every other lazy
> lib) ends at `$1C6A` (`libStubsEnd`) against `syscall.inc`'s `sysExit` block at
> `$1C6E` — **4 bytes of headroom**, and the assert is a `<=` rather than an
> `==` (`libStubsEnd <= $1C6E`), so a new lazy stub has to go into the free block
> at `$FF7E`,
> which is also why `libNameSid` is not beside the other lib name strings:
> `lib.inc`'s string block ends at `$FF7D`, and eight more bytes there would
> have consumed that pocket. `ipc.lib` followed the same day, and the block now
> runs **`$FF7E-$FFE5` (104 B)**: four 3-byte entries, four cold stubs, and the
> two name strings.
>
> ⚠️ That block sits at the very top of addressable RAM and is opened with
> `.pc = $FF7E`, so it **must stay the last thing assembled** — a `.pc` moves the
> location counter, and anything emitted after it silently walks off the end of
> memory (that is exactly how the first attempt broke six `gfx.asm` aliases).
>
> **Each index costs 4 bytes** (one in each table) and they come out of the
the **growth reservoir** — the `.fill` directly after the tables in `main.asm`,
which
is **spent** (all 42 indices are in use, so the tables end flush against
`gfxRowLutLo`). Growing the tables shifts
> `gfxRowLut*` and the whole `FONT_*` block, whose addresses are hard-coded in
> `gfx.asm`, `kernel.inc` **and** `kernel-data.inc` (the task-facing copy is not
> covered by any assert — only the kernel build checks it), so a missed copy is
> silent.
> The alternative to spending reservoir bytes is **freeing** indices: collapse a
> multi-index library into a single dispatcher entry the way `fp.lib` does
> (opcode in `A` — which `gfx`/`string` need for their inputs, so a dispatcher
> cannot serve them, but viable for `filesys`'s in-place I/O group, which takes
> everything in `kArg`/`kPtr`).

The library table is **separate** from the dynamic task table and the
residency records. Pool eviction scans task slots only — it structurally
cannot evict a library. A library leaves the pool **only** when its refcount
reaches 0 — or when the OS warm-reboots: the "no alive tasks" path goes through
`warmBootReset`, which releases every library before re-running `start:`.
A warm reboot must not leave one behind: its patched call entries point into pool
pages the reboot's fresh bitmap calls free.

---

## 5. Load / free / refcount

### `libLoad(A = lib id)` — `src/kernel/lib.inc` (`$FE66`)

`php`/`sei` at entry, `plp` before **every** `rts` (preserves the caller's I
flag), and `cli` on all error paths:

1. `libStartPage[id] != $FF` → already loaded, return `C=0`.
2. Locate `"<name>.lib"` via `reuFindFile`.
3. DMA the 256-byte header into `scratchBuf` (`$C400`), parse with
   `dynParseHeader` (**`dataPtr` must point at a valid buffer — it writes the
   name**).
4. Relocate + copy the code into the pool with the **shared** `dlLoadCore`
   (records `dlStartPage`/`dlPages`).
5. For each exposed call: patch the jump entry at `libJumpLo/Hi[call]`
   to `jmp <entry>` (the entry addresses are already relocated by
   `dlLoadCore`'s fixup pass).

`libLoad` re-asserts `sei` after `reuFindFile`/`reuDmaRange` (both return
CLI'd) and must **never** use `kArg+8`+ (it aliases `savedSP`).

### `libFree(X = lib id)` — `src/kernel/lib.inc`

`freeFromPool` the pages, clear `libStartPage = $FF`/`libPages = 0`, restore
every jump entry to its initial target from `libInitLo/Hi` (`libTrap` for
eager calls, the per-call cold stub for lazy calls).

### What happens when a lazy load fails

The stub reports it (`? could not load <name>.lib`) and then leaves through
`libFailExit` (`src/kernel/libstubs.inc`, at the end of the stub block, reached
from every stub's shared fail trampoline), because **C cannot
carry the news**: the stub's C=1 is also an ordinary library result (an empty
directory slot, a failed compare, `kReuFormat`'s failure), so a caller reads a
load failure as data and carries on with the library absent -- printing stale
buffer contents, or asking for the library again once per call.

`libFailExit` therefore **ends the calling task**. A command that cannot load its
library cannot do its job, so every caller refuses without testing anything --
rather than each command deciding whether C meant a failed load or data.

The **system shell** is the exception: it has to stay alive, but the *command* it
was running must not. It is **re-entered at its own entry with a fresh stack**
(`taskLo/Hi[curTask]`, SP reset to the cold-start value `$F7`), which is the path
a restored instance already takes -- the entry finds the surface it kept and
lands on the prompt -- so the command is abandoned, the message appears once, and
the prompt returns. Nothing in the shell has to test anything. Its `dataPtr` is
taken from the task's instance-buffer record first, because a library may have
used `dataPtr` as scratch (`gfx.lib` does, for its string drawer).

The shell is identified by its **parent link** -- `dlRegister`
writes it once from `curTask`, `initTCB_ptr` does not touch it (so it survives
eviction and restore), and `findFreeSlot` starts at slot 1, which makes slot 0
boot-only: a task whose parent is 0 is the boot target, and nothing else can be.
No id is stored, so nothing can go stale.

⚠️ The window is real, and it is the shell's: a task's loaded libraries stay
refcount-pinned by its own `libMask` for as long as it stays resident, and
*eviction* is what releases them -- while the shell is the one long-lived
**evictable** task (`edit` ([edit.md](edit.md)), `godzi`, `gortris` and `grknoid` are pinned). `run basic` hands
the shell's library pages back, and the first `fsinfo`/`save`/`load`/`run
<name>.bat` after the swap-in reloads them: `libLoad` sets `dlNoSelfEvict`, so the
shell can never be its own victim, and 10 contiguous `filesys.lib` pages can still
fail on a fragmented or starved pool. `pool` is not exposed to this -- `pcPool`
uses no library at all (its columns are decimal, via resident `kByteToDec`).

### Refcount lifecycle

- **Spawn** — the task header's `libMask` (parsed into `dlLibMask`) is walked
  by `dlLibRefcount`: each declared lib's refcount is bumped; if it was 0 and
  the lib is **eager**, `dlLibEagerLoad` loads it now. A failure **unwinds**
  (`dlRegUnwind` frees the task's pages + already-loaded libs and kills the
  slot) — spawn is transactional, no half-loaded leaks.
- **First lazy call** — the stub cold-loads the lib (refcount already bumped
  at spawn).
- **Exit / kill** — `dlLibRelease` walks `dynTaskLibMask`, decrements each
  declared lib; at 0 the lib is freed. `kill` also *reads* that mask (bit 5 =
  `sid.lib`) before killing, to decide whether the victim's SID drone needs
  silencing — see [lib-sid.md](lib-sid.md) § *Cleaning up after a kill*.
- **Eviction** — decrements via `dlLibRelease`; the cold restore re-declares
  (refcount 0→1) and reloads if the lib is gone.

**Lib-to-lib dependencies:** `time.lib` calls `kByteToHex` and
`filesys.lib` calls `kStrlen` (both in `string.lib`), but a `.lib` has no
scheduler slot and carries `libMask = 0` — libs cannot declare lib
dependencies. The lazy stub reloads `string.lib` on demand if a task's
exit freed it, so the dependency is safe (a 1-page reload at worst).
`kByteToDec` stays resident (used by `syscall.inc` for `parent.N` thread
names).

---

## 6. How a task declares libraries

The header's +10/+11 is the task's **16-bit `libMask`** — bit N = library N.
The bits are named `LIB_*` in `src/kernel/task-header.inc`, and those ids are
the index order of the descriptor tables in `src/main.asm`, so
`tools/check-lib-ids.ps1` fails the build if the two ever disagree. `gfxdemo`
declares gfx:

```asm
.word (1 << LIB_GFX)     // +10: libMask
```

Declaring a `libMask` is a **lifetime** commitment — the library stays in the
pool until the task exits or calls `kLibHold`. Who declares what:

| Library | Bit | Declared by |
|---|---|---|
| `LIB_TIME` | 0 | `clock`, `time` |
| `LIB_FILESYS` | 1 | the shell, `basic`, `banner`, `copy`, `del`, `dir`, `edit`, `format`, `fstest`, `godzi`, `gortris`, `granim`, `grknoid`, `grpaint`, `grview`, `rename`, `sidplay`, `type` |
| `LIB_GFX` | 2 | `basic`, `fpdemo`, `gfxdemo`, `granim`, `grpaint`, `grview`, `spirog` — **eager**, loaded at spawn |
| `LIB_FP` | 3 | `basic`, `fpdemo` — **eager** |
| `LIB_STRING` | 4 | the shell, `del`, `dir`, `ps` — lazy, loaded on first call |
| `LIB_SID` | 5 | `godzi`, `gortris`, `grknoid`, `sidplay` — lazy |
| `LIB_IPC` | 6 | `ipctest`, and any task pair built on `ipc.lib` — lazy |
| `LIB_SPRITE` | 7 | `godzi`, `grknoid`, `grpaint`, `sprdemo` — **eager** |
| `LIB_MOUSE` | 8 | `grpaint`, `mtest` — **eager** |

`fpdemo` additionally declares ZP `$02`–`$C5` — its per-task state plus the fp
window (`$90`–`$C5`) — so FP state survives preemption via the scheduler's ZP DMA.

### `fp.lib` API & error contract

`fpExec` (call index 25 → the fixed `kFpCall` jump entry, `$E113`) is a
single-entry dispatcher: `lda #opcode; jmp kFpCall` (still a `jmp`, so
`fpExec`'s tail-call discipline — handlers `rts` straight back to the
task's caller — is unchanged). All operands
live in the shared 40-bit floats `fac1`/`fac2` (EhBASIC addresses
`$AC-$B7`), result in `fac1`. Binary ops follow the EhBASIC evaluator
convention: **`fac2` = LEFT operand, `fac1` = RIGHT operand, result →
`fac1`** (`FSUB` = fac2−fac1, `FDIV` = fac2/fac1, **`FPOW` = fac2^fac1**,
`FCMP` → A=$01 fac1>fac2 / $FF fac1<fac2 / $00 equal). FLOAD reads a
5-byte float at `(kPtr)` into fac2; AYFC takes A=hi/Y=lo; BYTEF takes Y;
FSTORE packs fac1 to `(kPtr)`. Errors return **C=1 + A** = error code:

| A | Meaning | BASIC equivalent |
|---|---|---|
| 0 | divide by zero | `$14` division by zero |
| 1 | overflow | `$0A` overflow |
| 2 | illegal argument (log ≤ 0, sqrt < 0, tan blow-up) | `$08` function call |
| 3 | conversion range (≥ 2^24 for F2FX) | `$08` function call |
| 4 | unimplemented opcode | — |

Success returns C=0. The lib writes only ZP in the window `$90-$C5`
(fac1/fac2 stay at their EhBASIC addresses; scratch remapped into the
window pockets). A consumer must declare a ZP region covering the
window and must not keep its own persistent state inside `$90-$C5`.

---

## 7. Adding a new library

> ⚠️ **Start with §4.** This section is the mechanical recipe, and its step 4
> allocates an index (`sum(entryCount[0..id-1]) + entry`). Indices 33/34 are
> reserved for `sid.lib` and their table rows already exist, so a new library
> either spends reservoir bytes (§4) or reuses indices freed by collapsing an
> existing library's calls into one dispatcher entry.

1. Create `src/libs/<name>.asm` — wrapper + entry table, `.label <name>End`.
   Prefer unique label prefixes (KickAssembler shares one global namespace
   across all imported task files).
2. Add its segment to `tools/assemble-tasks.asm` and `tools/gen-fixups.asm`,
   and a `@{ name = "<name>.lib"; file = "tasks-out/<name>lib.bin" }` entry
   to `tools/build-reu.ps1`.
3. In `main.asm`: extend `libNameLo/Hi`, `libEntryCount`, `libEager` (mind
   `MAX_LIBS`), and the name strings in `lib.inc`.
4. Turn the relevant `kernel.asm` jump entries into an eager `jmp libTrap`
   or a lazy `jmp libStub<Name>` stub in `libstubs.inc`, and add their
   `libJumpLo/Hi` + `libInitLo/Hi` rows in `main.asm` (call index =
   `sum(entryCount[0..id-1]) + entry`).
5. Set the declaring tasks' `libMask` bit(s).
6. Rebuild tasks + REU, and update the `.assert` pins.

---

## 8. Related task flags

Libraries are orthogonal to the task-instance flags, but they interact with
the loader's single-instance logic:

| Flag | Value | Meaning |
|---|---|---|
| `KF_RELOCATABLE` | `$01` | code has a fixup table — loads at any free address |
| `KF_REENTRANT` | `$04` | **shared code** — first load copies code into the pool; later `run`s share it and get a fresh per-instance data buffer (`data_size > 0` required). `ps` shows `shared`. |
| `KF_RE_RUNNABLE` | `$20` | **fresh copy per `run`** — like plain relocatable, but a second `run` of the same name is allowed (no `? already running`). For stateless tasks that keep no per-instance data (`gfxdemo`, `maze`, `clock`). |
| `KF_NOT_EVICTABLE` | `$40` | **pinned** — `dlEvict` never swaps this task out. If every resident task is pinned, a pool-full load fails with error 4 (`? no space in pool`). Used by `edit` (unsaved document data), `gortris`, `grknoid` and `godzi` (a cold restart would lose the run). ⚠️ A task that has live **thread** children is in effect unswappable too, without the flag: `dlEvDo` finds a live thread child (a `kDynLoad` child does not count — it has its own pages) and **kills the task and its whole subtree** instead of swapping, because the children run the parent's code pages. See docs/programmers-guide.md → *Pool fragmentation / eviction*. Note: libraries themselves are never eviction victims — they are released by refcount. Their **pool placement** is from the **top** (`dlAllocHi`) while task code/RAM/`kMalloc` grow from the bottom, so a library can never sit between two task blocks and split the free space. |
| (neither `$04` nor `$20`) | — | **single instance** — a second `run` of the same name is refused with error 11 (`basic`, `gortris`, `grknoid`). |

The distinction:

- **Reentrant** = one shared code copy + N private data buffers (lowest RAM
  per extra instance; requires per-instance state).
- **Re-runnable** = N independent code copies, no private data (simplest;
  each instance is a plain relocatable load that happens to be repeatable).
- Both coexist with libraries: a re-runnable task that declares `libMask`
  still bumps the shared lib refcount on each `run`, so `gfx.lib` is loaded
  once and freed only when the last `gfxdemo`/`fpdemo`/`spirog` exits.

---

## 9. What stays resident (never a library)

scheduler / IRQ / syscall dispatcher · `kDynLoad` + `dlLoadCore` /
`allocFromPool` / `freeFromPool` / `dlRestore` · `reuFindFile` /
`reuDmaRange` / `reuCmpName` / `reuDirPageDma` · `kReuLoad` (boot loads the
font) · the whole text-blit path (`kPrintChar`…`kPrintGlyph`) · keyboard /
`kReadString` · `switchView` / `csrBoth` (IRQ F-key switch) · the REU DMA
API (`kReuToC64`/`kReuFromC64`/`kReuFillC64`/`kReuFillReu`) ·
`kAllocScreen`/`kFreeScreen`/`kGetTaskName` · `kMul16`/`kDiv16`/
`kByteToDec`/`reuCmpName` (kernel-internal callers) · the jump table itself.
