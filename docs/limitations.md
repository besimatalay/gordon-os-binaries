# GordonOS — Limitations

> What GordonOS cannot do, why, and what to do instead. These are the limits of
> the design: some are the C64's, some are deliberate trades.
>
> The honest summary: on a 1 MHz 6502 with 64 KB of RAM the system is **full**.
> Everything a first release needs is there and working — but the room to add
> more *resident* features is gone, so new capability goes into libraries, into
> the REU, or into the task rather than the kernel. Every limit below has a
> documented way around it, and most of them are already used by the tasks that
> ship in the image.

---

## 1. The kernel has no room left — and it is complete

| | |
|---|---|
| Free space in the kernel's address space | **125 bytes across 22 pockets** |
| The kernel core's growth headroom | **15 bytes** (`$13C5-$13D3`, `kernelCoreEnd` to `reuDirBuf`) |
| Largest free pocket that can hold kernel code | **9 bytes**. The two larger runs (31 B at `$02A1`, 18 B at `$020D`) are below `$0801` and can never be used at all (VICE autostart takes the PRG's first block as the file start), and the 15-byte run after `kernelCoreEnd` is the core's own growth headroom, reserved for core changes |
| The `$ECDC-$FC3E` code chain's growth room | **5 bytes** |
| The `$FF7E` block at the top of RAM | **zero slack** — any growth in the code band collides with it and fails the build |
| Spare jump-table entries | **none** — `kMouseCall` took the last one (`$E0F6-$E0F8`) |

The space is spent on features, not on waste: **102 jump-table entries**, **196
documented call addresses**, nine libraries, 14 syscalls, a dynamic loader,
malloc, a filesystem, per-task screens, sprites and a sprite hand-over, all
inside a core that is about 2.9 KB of code between `$0801` and `$13D4`.

Three constraints make the last bytes especially awkward:

- **Two of the biggest free runs can never hold code.** `$02A1-$02BF` (31B) and
  `$020D-$021E` (18B) sit below `$0801`; KickAssembler writes PRG blocks in
  ascending address order and VICE's autostart treats the first block as the load
  base, so a block down there breaks the whole image.
- **The `$E000` band's labels are ABI.** `keyrpt` pokes addresses inside it and
  `gfx.lib` hardcodes scratch addresses that sit above it, so changing its
  size means updating 17 asserts in `main.asm` and every external consumer in the
  same commit — or giving the bytes back as an inert `.fill n, $ea` sled.
- **A growth pocket is not storage.** Parking a routine at the bottom of the
  core's 15 bytes leaves the whole core band with no room, and the next change
  fails the build with a block overlap.

**Working with it.** New capability belongs in a **library** — that is what the
lazy-loading, refcounted, evictable library system is for — or in a task, not in
the kernel. Before adding anything resident, check whether an existing call does
the job, and whether it can be expressed with the calls that already exist. When
resident code really is the answer, [kernel-fragmentation.md](kernel-fragmentation.md)
lists every free run and [development.md](development.md) §6 lists the gates that
will tell you if the layout broke; a genuine growth change is a planned
relocation, not an edit. The flip side is stability: the build's own asserts (a
few hundred of them, added as guards over the years) plus the layout gates
protect this surface, so what is there does not drift.

---

## 2. The task pool is 27.25 KB

The pool is **109 pages of 256 bytes, `$5700-$C3FF`** (configurable in
`src/kernel/pool.inc`). Everything a task needs from C64 RAM comes out of it —
task code, program RAM, `kMalloc` blocks and libraries — and it is boxed:

- `$2000-$3FFF` beneath it is the **live framebuffer**;
- `$C400` above it is `scratchBuf`;
- below it, `scrollScreenSlot`'s band leaves 131 bytes — less than one page.

So it cannot simply be made bigger. What that means in practice:

- **A task's footprint is its code rounded up to pages, plus its data.** A task
  whose code crosses a page boundary costs a page more, so keeping code off the
  next boundary is worth the effort.
- **Only eight task slots have a malloc shadow.** `kMalloc` and program RAM are
  preserved across eviction by a 32 KB REU block per slot in banks 252-255 — four
  banks, **eight slots**. Each of those slots caps at **64 pages (16 KB) of
  `kMalloc`** plus 16 KB of program RAM: half the shadow each.
- **The big tasks dominate.** `basic` needs roughly 65 pages of the 109 and only
  loads after the shell is evicted; `edit` holds 36 pages for its whole life.
- **`? already running` is per-task, and a second copy costs the full
  footprint** unless the task is *reentrant*, in which case several instances
  share one set of code pages and only the instance data is per-copy.

**Working with it.** The image's own tasks show the techniques: keep code tight
(a 6502 project's normal discipline); make a task **reentrant** rather than
re-runnable when several copies at once make sense; put **bulk data in the REU**
— `basic` keeps its whole program, variables and strings in a 64 KB REU working
  file; use one `kMalloc` block for the data a task must hold rather than several
  — `edit`'s document is a chain of 4-page `kMalloc` chunks
  ([edit.md](edit.md)), sized to the document as you type; prefer
  **single-shot tasks that exit** over

---

## 3. Fragmentation: the pool deals in adjacent pages, not free pages

The pool is **page-granular, first-fit and contiguous-only**: a load needs *N
adjacent* free pages, not *N* free pages. `? no space in pool` (loader error 4)
therefore means "there is no single run of N pages", not "the pool is full".

A real field report is the canonical picture:

```
 0- 18  shell                        (19 pages)
19- 70  free                         (52)   <- the shell's own libs + gfxdemo's freed 26-page gfx.lib
71- 72  gfxdemo code                 ( 2)
73- 98  free                         (26)
99-108  libraries parked at the top
        -> a 65-page load (basic's code) has no 65-page run, although 78 pages are free
```

**`pool` cannot show you this.** Its rows and its `used`/`free` totals come from
the *tables* (`pcPool`: dyn tasks, program RAM, malloc, libs), never from the
allocation bitmap — so a healthy-looking listing coexists with a failing load.
It also lists only what is **in memory at that moment**: a swapped-out task has
no row, and a library has one only while a task that declares it is alive — so a
library nothing currently holds is absent by design, not missing.
The fragmentation shows in the **`pg` column**: compare it against a fresh boot
(`shell 0` with the libraries at the top) and a different pattern tells you an
earlier load/free cycle moved things.

What already limits the damage: the **bottom/top split** (task code, program RAM
and `kMalloc` grow up; libraries come down from the top, so a library can never
land above a task and split the task region); **eviction and restore re-place
code**, because the restore path goes through the normal first-fit walk, so the
region repacks itself every time something is evicted and restored; **data
outlives code** (stack, ZP window, instance buffer and `kMalloc` blocks all
survive eviction), so freeing code pages is always safe.

What is still a limitation: **nothing relocates a live block**, so a hole left by
a small task is unusable by a bigger one until something of that size — or a
neighbour's eviction — reclaims it.

**Working with it.** Treat `? no space in pool` as a *placement* problem: `kill`
what you do not need, or reboot to reset the bitmap. Prefer tasks that exit.
Keep large tasks out of the way of large loads. And note the other two
fragmentations in the system: the **REU data area** fragments as files are
deleted (deletion tombstones an entry, `compact` reclaims the space, and
`build-reu.ps1` deliberately leaves one gap for the `fscross.bin` bank-crossing
test), and the **kernel's** 127 free bytes are pockets rather than a region
(section 1).

**Why we stop here.** Defragmenting the pool at runtime would have to relocate
*live* tasks — code (re-applying the hi-byte fixups), ZP, stack, instance data,
surfaces and `kMalloc` blocks — with the fixup machinery existing only at load
time, so every task would have to be frozen and cold-restarted, losing its data,
and a pinned task could not be moved at all. Non-contiguous allocation (a page
list per task) turns every task address computation indirect and rewrites
`allocFromPool`, `kMalloc` and the loader. Both cost more than the fragmentation
they repair. `programmers-guide.md` § *Pool fragmentation* has the full
trade-off table.

---

## 4. Sprites: eight slots, and the display is the unit

- **Eight sprites is the VIC's ceiling, and none is reserved.** `kSprite*` calls
  reject slot 8+, so the whole budget is yours — but it is the whole budget.
- **A frame is 64 bytes and the art can only live in two bands.** The slots are
  fixed hardware addresses (`$02C0-$03FF` for 0-4, `$0F00-$0FBF` for 5-7), and
  nothing between the bands can hold art: `$1000-$1FFF` is char ROM to the VIC
  (sprite fetches included), `$2000-$3FFF` is the framebuffer. `$0FC0` is
  deliberately left free as relocation slack, not as a ninth slot.
- **One colour per sprite** (its own register, plus the two global multicolour
  colours, which are per-task in effect because they are published from the
  shadow, but shared across that task's eight sprites). Expansion is X/Y only —
  it doubles pixels, it does not add resolution.
- **`kSpriteSheet` costs ~1,000-3,000 cycles and runs `SEI`'d** (the FS find and
  the record copy share `reuFsPtr`, so they must be atomic). **Resolve once at
  startup, never in a frame loop.** A sheet is a flat file of 64-byte frames with
  no frame count and no cache.
- **Collision gives masks, not pairs.** `$D01E`/`$D01F` say "this sprite touched
  *someone*", so identifying the pair is a heuristic unless exactly two sprites
  are enabled. There is no geometry, the latches accumulate until read, and a
  disabled sprite cannot collide.
- **The commit has a deadline.** Past raster line 30 the kernel publishes nothing
  for that frame rather than split a visible sprite — a one-frame hold, not a
  lost update.
- **Sprite state is per task and swapped with the display.** That is what lets
  several sprite tasks coexist, but it also means **a task drives sprites only
  while its surface is displayed**: every setter returns `C=1` having written
  nothing when the caller is not the display owner. A hand-over costs two DMAs
  plus up to eight 64-byte frame DMAs.

**Working with it.** One display owner at a time — that is the model, and it is
what the kernel guarantees rather than limits. For anything needing more colours,
more objects or finer shapes than eight 24×21 sprites, draw in the bitmap
instead: `gfx.lib` has the primitives, and text is already a glyph layer over the
same surface. Animate on `frameCount`, never on the scheduler tick. Call
`kSwitchView` before any sprite call, and remember the cost of `kSpriteSheet` is
paid once per sprite, not once per frame.

---

## 5. Libraries: the call-index space is the ceiling, and it is spent

| | |
|---|---|
| Library **ids** available | **16** (`MAX_LIBS`), ids 0-8 in use |
| Library **call indices** available | **42** (`LIB_CALLS`) — **all 42 in use**, and the tables end flush against the first pinned address below them |
| Cost of one more index | **4 bytes** (one byte in each of the four scan tables), out of a 16-byte reservoir that is already gone |
| The `$E000` jump table | **full** — the last entry-sized run went to `kMouseCall`; only the single byte `$E119` remains |
| `libstubs.inc` (the lazy cold stubs) | occupies `$1A1B-$1C69`, with `libStubsEnd` asserted `<= $1C6E` — the tail `$1C6A-$1C6D` is **4 bytes**, room for one more call *index* (4 B) and nothing else |

The cap counts **calls**, not libraries, and it is independent of eager vs lazy:
`libEager` only decides *when* a library loads, while an index is consumed per
call either way. The **ids** are not the constraint — 16 exist and 8 are in use,
so a library can be declared long before its calls fit.

Related limits that follow from the same squeeze:

- **A lazy library needs room for its call entries *and* their cold stubs.** New
  entries therefore do not live in the `$E000` table at all: the five `kSprite*`
  stubs sit in the `$CDDE` pocket and the `sid.lib` and `ipc.lib` entries went
  into the free block at `$FF7E` — which is opened with `.pc` and must stay the
  last thing assembled.
- **A library cannot declare a library.** A `.lib` has no scheduler slot and
  carries `libMask = 0`, so `time.lib`'s use of `kByteToHex` and `filesys.lib`'s
  use of `kStrlen` rely on the lazy stub reloading `string.lib` on demand.
- **An eager library has no cold stub.** Handing one back with `kLibHold` loses
  its calls for good (they fall to `jmp libTrap` and return `C=1`) until another
  task loads it — which is why `sprite.lib`'s bit must stay in the keep mask.
- **A failed lazy load ends the calling task.** That is deliberate: `C=1` is also
  an ordinary result (an empty directory slot, a failed compare), so a caller
  could not tell a missing library from data. The shell is the exception — it is
  re-entered at its own entry with a fresh stack, so the command is abandoned and
  the prompt returns.
- **Libraries share the 27.25 KB pool** and are freed only when their refcount
  reaches 0. Eviction can release them, which is what lets `run basic` fit — but
  the reload can then fail on a fragmented or starved pool (`filesys.lib` is ten
  contiguous pages).

**Working with it.** Use a **dispatcher entry** instead of an index per call —
`fp.lib` is the pattern: one call index (`kFpCall`) with an opcode in `A` selects
among 26 operations. Keep the resident kernel calls for hot paths; that is what
they are for. Declare libraries honestly in `libMask` and keep the ones you still
need in `kLibHold`'s mask. [dynamic-libraries.md](dynamic-libraries.md) §4 has
the index map and the full accounting.

---

## 6. The display: one screen at a time, and it is all bitmap

- **There is one VIC, so exactly one surface is displayed.** 28 REU bitmap slots
  can exist, and eight are reachable from the keyboard (F1, F3, F5 and F7, each
  with SHIFT for the second of its pair), but switching is a 10 KB save plus a
  10 KB load — not free.
- **"Text" is a glyph layer over the bitmap.** The VIC-II stays in hires bitmap
  mode permanently, which is what lets text and graphics mix on one surface — but
  it also means **there is no character cell to read back cheaply**. `kCharAt`
  decodes a cell, and a task can opt in to a 1 KB **char shadow** per surface (24
  available) if it needs to know what is on a surface it is not displaying.
- **There is no RAM font.** Glyphs are DMA'd from the REU filesystem on demand,
  so a character costs pixel work every time it is drawn.
- **Never write the last cell of the last row of a scroll region.** `kPrintChar`
  advances and then wraps, and the wrap scrolls the region as it writes that
  cell — no repositioning afterwards brings the top row back. (This is why
  `gortris` draws its whole frame — row 24 included — through `kPrintGlyphAt`,
  the fixed-cell writer: it wraps and scrolls nothing. See
  [gortris.md](gortris.md).)
- **The blink cursor is drawn into pixels**, so a task taking the display must
  un-draw it first or the cell is baked into the outgoing surface and comes back
  as a phantom block: `kBlinkReset` under `SEI` before `kSwitchView`, with no
  syscall inside that window — the recipe is in programmers-guide.md, under
  *Bitmap Graphics → Switching views*.

**Working with it.** Structure a task as "own the display and drive it" — that is
the model the kernel enforces, and it is why `kSwitchView` exists. Use scroll
regions for panels and HUDs instead of redrawing the screen. Use `kPrintGlyph`
when your art is 8-byte glyphs. From the shell, `view <id>` and the F-keys let
you look at any task's surface without changing its code.

---

## 7. The filesystem: flat, bounded, and on the REU only

- **512 entries × 32 bytes, flat.** Names are 1-11 characters, held as screen
  codes. **There are no subdirectories** — they are designed, not built
  ([future-improvements.md](future-improvements.md) §12).
- **A file's size is a 16-bit field**, so a single file is at most **65,535
  bytes**, and the data region's capacity is derived from how many banks the REU
  has (`$3000 + (banks − 10) × $10000`).
- **Deletion tombstones an entry**; the space is reclaimed by `compact`.
- **There is no directory handle.** `kReuDirEntry` reads entry *n* by index and
  every consumer loops `n = 1, 2, …` until it returns `C=1`, which makes every
  caller a directory scanner.
- **It is an REU image.** Files live in the image, and the host-side
  `tools/build-reu.ps1` formats a *fresh* one — there is no host tool that adds a
  single file to an existing image.
- **The FS is the only filesystem.** There is no IEC/disk support; the KERNAL ROM
  is banked out, so a 1541 or 1581 implementation would be from scratch
  ([future-improvements.md](future-improvements.md) §5).

**Working with it.** Use the **in-place I/O set** (`kReuCreate`/`kReuOpen`/
`kReuReadAt`/`kReuWriteAt`) for fixed-size records instead of reloading whole
files — that is what the hi-score tables and BASIC's working file do. `compact`
after a batch of deletions. Keep a file's size in mind when designing a format:
one file, one 64 KB ceiling.

---

## 8. Memory safety: no MMU, so no protection

**There is no MMU, and that is the source of this section.** Without one there is no
way to give a task its own address space, so every task sees the same flat 64 KB: a
stray store can hit the kernel, another task's data, the video matrix or the
framebuffer, and there is no fault — the machine simply misbehaves. There is also
**no crash protection**: a `BRK` or a bad jump takes the system down rather than
killing the task ([future-improvements.md](future-improvements.md) §6).

**GordonOS is in good company, and this is the point of the section.** The
Commodore Amiga — the multitasking machine of the era, and the usual yardstick for
an OS like this one — had exactly the same hole: its 68000 has no MMU, and AmigaOS
has **no built-in memory protection**, so any task could write over any other and a
bad pointer gave you a Guru Meditation and a reboot rather than one dead task. Its
kernel even counted the single address space as an *advantage*, because message
passing between tasks then needs no copying between address spaces. Later Amigas
shipped an MMU on the CPU and ran the same unprotected OS.

So the missing protection is the ceiling of the hardware generation, not a
shortfall in the implementation. What a 6502 OS *can* afford to isolate, this one
does — the stack, the zero page, `kArg`, and per-task instance data are all private
— and the rest is covered by being strict about the ABI. What *is* isolated, and
what is not:

| Isolated per task | Not isolated |
|---|---|
| the 256-byte stack (REU-swapped on every switch) | any pointer a task chooses to write through |
| the zero page, if the task declares a window (`zp_base`/`zp_len`, `$02-$EF`) | the framebuffer, video matrix and colour RAM |
| the `kArg`/`kResult` block (8 bytes, per-task shadow) | kernel data and other tasks' instance buffers |
| instance data (`dataPtr`) and `kMalloc` blocks | the VIC's registers — a direct write to `$D000-$D02E` disturbs whatever is displayed |

Smaller API facts that follow from the design, and that task code has to respect:

- **`kArg` is 8 bytes and is clobbered by any task's kernel call** — it is
  documented scratch, never state to hold across a call, a `yield` or a sleep.
- **Zero page `$F0-$FF` is not a task's.** `$F0` is the kernel's blink interval;
  `$FB-$FF` belong to the scheduler and the keyboard IRQ. `$00-$01` are the 6510
  port. A task's window is `$02-$EF`, and preserving it **costs an REU DMA on
  every context switch** — which is why it is opt-in and why declaring a narrow
  window is better than declaring all of it.
- **The stack is 256 bytes.** Deep recursion, a large local buffer or an
  unbalanced push/pop overflows into whatever follows.
- **Blocking calls clobber registers.** `SYS_SLEEP` returns with `X = curTask`,
  `SYS_YIELD` returns `A = 0`, and a routine that blocks must re-derive its
  register inputs afterwards (the kernel's own `kIpcPost` parks its values on the
  task stack for exactly this reason).
- **`kReadKey` cannot report "empty"** — a queue drain reads all 16 slots, because
  a key *release* is queued as a byte too.

**Working with it.** This is the normal condition of a 6502 system, and the
mitigations are at build time rather than run time: the build's `.assert`s pin the
layouts and addresses, a wrapper makes a failed assert fail the build, three
linters catch offset arithmetic no assert can see, and the clobber table in
[kernel.md](kernel.md) is the contract every call documents. A task that follows
its declared ZP window, keeps `kArg` as scratch and keeps its stack shallow is a
well-behaved citizen — the isolation it needs is the isolation it declares.

---

## 9. Concurrency: 24 slots, 4 semaphores, no signals

- **24 task slots** (`MAX_TASKS`, a build-time constant — changing it resizes
  every per-task array and the REU layout). Slot 0 is boot-only. The practical
  limit is usually the pool, not the slots.
- **Four semaphores.** Index 0 is the screen lock every kernel output routine
  takes; **1-3 are free for tasks**. They are owner-tracked and released when the
  owner dies, but the pool itself is kernel-owned — a library cannot offer a
  semaphore, because a task dying while holding a library semaphore would leave
  it locked and the kernel's death scan only knows its own pool.
- **No signals.** There is no asynchronous notification, so a task learns about an
  event by polling; a parent cannot be told its child exited.
- **Blocking calls cannot be interrupted or timed out.** `kReadString` and
  `semWait` block until they complete — there is no timeout and no cancellation
  ([future-improvements.md](future-improvements.md) §2).
- **IPC is four fixed, anonymous byte channels**, each with a 128-byte ring in the
  library's own data: **single-producer / single-consumer**, no framing, no
  allocation and no ownership — two tasks cannot claim a channel for themselves.
  `kIpcPost` blocks while the ring is full; **`kIpcPick` never blocks on purpose**
  (a dead producer must not strand a consumer), so a consumer polls, with up to a
  jiffy of latency per byte.
- **No blocking I/O and no device layer.** A task waiting for a device polls or
  sleeps; there is no `BLOCKED` state
  ([future-improvements.md](future-improvements.md) §4).
- **No CPU accounting.** Priorities are 0-5 with 0 meaning paused, and every
  running task gets its time slice — but nothing measures or caps how much of the
  single CPU a task uses.

**Working with it.** `SYS_SLEEP` instead of a spin loop; `SYS_YIELD` to hand the
slice over deliberately; semaphores for mutual exclusion between two tasks; and a
**thread child** for a second activity inside one task — that is how the games
play music while the game runs (the child owns the tune, the parent owns the
display). For larger IPC, a task can DMA to any REU address the kernel knows
about with `kReuToC64`/`kReuFromC64`, which is enough for a private scratch region
or a hand-rolled queue.

---

## 10. Timing: one tick, two clocks

- **The scheduler tick is CIA #1 timer A at 59.2 Hz** (called ~60 Hz). Sleep is in
  ticks (1-255), so the finest delay is about 17 ms.
- **The display frame is a different clock** — 50.1 Hz on PAL, 59.8 Hz on NTSC.
  The tick is sampled about 1.18 times per frame, so **animating per tick
  stutters**; anything animated is paced on `frameCount`, one increment per
  displayed frame, compared for *change*.
- **The two clocks drift against each other by design.** Music is jiffy-based and
  compensated; games are frame-based and therefore naturally standard-independent
  once paced on `frameCount`.
- **The CIA time-of-day clock is the clock**, at 1/10 s resolution, and it loses
  time under heavy REU load because the TOD is frozen while the REU has the bus
  ([lib-time.md](lib-time.md)).
- **Speed is declared, not measured.** `speed <percent>` tells the system what the
  whole machine is doing, and the blink/key-repeat ticks and `sid.lib`'s pitch and
  tempo compensate for it. Above 200% is not recommended: the SID would need more
  than one octave down.

**Working with it.** `frameCount` for anything animated or game-paced; ticks for
timeouts and rates; `speed` once, at boot, from the image's `boot.bat`. If a task
must be real-time on both PAL and NTSC, pace it on frames and let the frame rate
be what it is.

---

## 11. Not built yet

These are designed or planned, not present. Each is documented in
[future-improvements.md](future-improvements.md).

| Missing | Consequence today |
|---|---|
| **Signals** (§2) | blocking calls are uncancellable; a parent polls `ps` to learn a child exited |
| **SEND/RECEIVE IPC** (§1) | no message framing, no blocking receive, no channel ownership |
| **Stream abstraction** (§3) | no stdin/stdout abstraction, no shell pipelines |
| **Blocking I/O and device drivers** (§4) | no `BLOCKED` task state; waiting is polling or sleeping |
| **IEC / disk filesystem** (§5) | the REU filesystem is the only filesystem |
| **Crash protection** (§6) | a `BRK` or bad jump takes the whole system down |
| **Extended task workspace in REU** (§7) | `kReuToC64`/`kReuFromC64` work, but there is no allocator or carved-out region for a task's own REU memory |
| **REU IPC shared buffer** (§8) | no large shared-memory channel; IPC is 128 bytes per channel |
| **RAM disk / sector cache** (§9) | depends on the disk filesystem |
| **Char cache for text surfaces** (§10) | bulk output and background scrollback pay full glyph cost |
| **Editor undo/redo** (§11) | `edit` has no undo ([edit.md](edit.md) → *Limits*) |
| **REU FS directories** (§12) | one flat namespace of 512 entries |

---

## 12. The summary

| Limitation | The way around it |
|---|---|
| Kernel address space full (127B / 22 pockets) | put new capability in a library; reuse the 102 calls that exist; a resident addition is a planned relocation |
| Pool is 27.25 KB, page-granular | reentrant tasks share code; data goes to the REU; single-shot tasks that exit; pin only what must not move |
| Pool needs *adjacent* pages | treat `? no space in pool` as placement — kill what you do not need, or reboot; prefer small re-runnable tasks |
| `pool` cannot show fragmentation | read the `pg` column against a fresh boot |
| 8 sprite slots, 2 art bands, one colour each | draw in the bitmap when you need more; one display owner at a time; resolve sheets once |
| Sprite/bitmap work only while displayed | `kSwitchView` first; the kernel swaps per-task state for you |
| Call-index space spent (41/41) | dispatcher entries (`kFpCall` pattern) instead of one index per call |
| Library load can fail on a starved pool | keep the libraries you need held (`kLibHold` mask); keep hot paths on resident calls |
| No memory protection, no crash guard | follow the declared ZP window; keep `kArg` as scratch; the build's asserts and gates catch layout errors before they reach the machine |
| 4 semaphores, no signals, blocking calls stick | sleep instead of spinning; semaphores for mutexes; a thread child for a second activity |
| IPC is 4 fixed 128-byte SPSC rings | bytes in a ring, or DMA a private REU region for bulk |
| 24 slots, no CPU accounting | the pool is the real ceiling; pace work on `frameCount` |
| FS flat, 512 entries, 11-char names, 64 KB files | in-place fixed-size I/O; `compact` after deletions; one file per record set |
| One screen displayed, all-bitmap text | scroll regions, glyphs and `view <id>`; opt in to a char shadow if a task must read its own surface |
| PAL/NTSC and emulator speed differ | pace on `frameCount`; declare the machine with `speed` |

---

## Where to go next

| Topic | Document |
|---|---|
| What is planned | [future-improvements.md](future-improvements.md) |
| Where kernel code can live | [kernel-fragmentation.md](kernel-fragmentation.md) |
| The pool and its placement rules | [programmers-guide.md](programmers-guide.md) § *Pool fragmentation* |
| The whole address space | [memory-map.md](memory-map.md) |
| Library mechanics | [dynamic-libraries.md](dynamic-libraries.md) |
| Building, and the gates that guard all of this | [development.md](development.md) |
