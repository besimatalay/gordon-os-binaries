# GordonOS — Feature Overview

GordonOS is a preemptive multitasking operating system for the Commodore 64 with a
RAM Expansion Unit. The KERNAL and BASIC ROMs are banked out, so the whole 64 KB address
space is RAM — shared between the kernel, the display and the task pool that task
binaries are loaded into — while a 16 MB REU carries the per-task stacks and zero-page
shadows, the screen surfaces, the sprite state, and a persistent filesystem that holds
every task and library binary.

This page is the tour: what the system offers, and where the detail lives for each
part. Nothing here is a substitute for the deep documents, which are linked throughout.

- New to running it: [quick-start.md](quick-start.md)
- Writing tasks: [writing-relocatable-tasks.md](writing-relocatable-tasks.md) and
  [programmers-guide.md](programmers-guide.md)
- Kernel internals: [kernel.md](kernel.md), [architecture.md](architecture.md),
  [memory-map.md](memory-map.md)

---

## 1. The machine it makes of a C64

- **The whole 64 KB address space is RAM.** Both ROMs are banked out, so nothing is
  shadowed by the KERNAL or BASIC — but the space is **shared**, not the kernel's:
  the kernel core and its `$E000` call band, the video matrix (`$0400-$07FF`) and the
  framebuffer (`$2000-$3FFF`), the task pool (about 27 KB of it, sized in
  `src/kernel/pool.inc`) and the byte the CPU port points at all live in it. The pool
  is where task binaries are loaded at run time, so a task's own code and data sit
  inside that same 64 KB. [memory-map.md](memory-map.md) has the byte-level split.
- **All-bitmap display.** The VIC-II stays in hires bitmap mode permanently: the
  framebuffer is `$2000-$3FFF` and the video matrix `$0400-$07FF`. "Text" is an 8×8
  glyph layer blitted over bitmap surfaces, so text and graphics mix freely on any
  screen, in both hires (320×200) and multicolour (160×200).
- **The REU is the system's storage, not a cache.** Task binaries, libraries, screens,
  stacks, sprite sheets, fonts, music and the scores all live there.
- **One clock, two rates.** The scheduler ticks on CIA #1 timer A at ~60 Hz. The
  *display* frame is the VIC's, 50.1 Hz on PAL and 59.8 Hz on NTSC — anything animated
  is paced on `frameCount`, the display's own clock, never on the tick.
- **Two images, one OS.** `reu/REU.bin` declares `speed 200` (VICE at 200% of real
  time) and `reu/REU-C64U.bin` declares `speed 100` (a C64 Ultimate, or any real
  machine). See [quick-start.md](quick-start.md) → *speed*.

## 2. Multitasking

- **Up to 24 concurrent tasks**, each with its own 256-byte stack image in REU and its
  own preserved zero page.
- **Preemptive, priority-driven round-robin.** Six priority levels (0-5), a per-task
  time slice, and a context switch driven by the timer interrupt.
- **REU-accelerated context switches.** The outgoing stack and the incoming stack are
  moved by REU DMA rather than by copying through the CPU.
- **Per-task zero-page preservation on demand.** A task declares the window it cares
  about (`zp_base`/`zp_len` in its header, within `$02-$EF`) and the scheduler DMAs
  that window to and from a per-slot REU shadow on every switch. A task that declares
  nothing pays nothing. `$F0` is the kernel's own `blinkRate` and is never a task's.
- **Tasks can be paused, resumed, reprioritised and killed** from the shell
  (`pause`, `resume`, `prio`, `kill`), and `kill` cascades to a task's thread children.
- **Threads.** A task can spawn children that share its code pages (`SYS_THREADSPAWN`),
  named `parent.N`. They are cheap — no loader entry, no separate image — and the
  scheduler holds a child whose parent has died or been swapped out.
- **Semaphores.** Four counting semaphores, of which index 0 is the screen lock every
  kernel output routine takes; 1-3 are free for tasks.
- **IPC.** `ipc.lib` provides four fixed 128-byte byte channels with a lock-free
  single-producer/single-consumer ring, a blocking post that yields under
  backpressure rather than spinning, and no caller zero page. See [lib-ipc.md](lib-ipc.md).

## 3. Memory: one pool, two directions

- **A single page-granular pool** from `$5700` to `$C400`. Tasks, program RAM and
  `kMalloc` grow up from the bottom; libraries allocate down from the top, so a
  library can never split the task region.
- **A generic kernel heap.** `kMalloc`/`kFree` hand out task-owned blocks that survive
  the owner being swapped out; `pool` prints the map (`pool` cannot show a *placement*
  problem — see [kernel-fragmentation.md](kernel-fragmentation.md)).
- **Eviction when the pool is full.** The loader swaps a victim out to REU or kills it
  (with its thread children), and the caller is never the victim.
- **Residency records for shared code.** A reentrant binary resident once is refcounted
  per instance, so several running copies share one set of pages.
- [memory-map.md](memory-map.md) has the byte-level view.

## 4. The dynamic loader

- **Tasks and libraries are files, not code linked into the kernel.** `run <name>`
  loads a relocatable binary from the REU filesystem into the pool at any free address.
- **Three kinds of binary**: `.tsk` (a full task), `.com` (a command that runs on the
  shell's screen and exits), `.lib` (a kernel library).
- **Flags that change how a task is treated**: relocatable, reentrant (one code copy,
  many instances), re-runnable (a fresh copy per `run`), not-evictable (pinned),
  takes-args, needs-screen, program-RAM.
- **Relocation is verified at build time.** Every task is assembled three times at
  three origins and the fixup results are compared, so a botched fixup fails the build
  rather than the machine. See [writing-relocatable-tasks.md](writing-relocatable-tasks.md).

## 5. Libraries

Shared code loaded on demand and refcounted, so a task declares what it needs and the
loader does the rest. Nine ship today:

| Library | Loading | What it gives you |
|---|---|---|
| `time.lib` | eager | the CIA time-of-day clock: `kGetTime`, `kSetTime`, `kPrintTime` |
| `filesys.lib` | lazy | the REU filesystem: `format`, `save`, `delete`, `rename`, `dirEntry`, `create`, `open`, `readAt`, `writeAt` |
| `gfx.lib` | lazy | the bitmap primitive set (section 7) |
| `fp.lib` | eager | the EhBASIC floating-point core, usable on its own — `fpdemo` is the demo |
| `string.lib` | lazy | `kStrlen`, `kStrcpy`, `kStrcmp`, `kSkipSpaces`, hex/decimal helpers |
| `sid.lib` | lazy | the SID player (section 9) |
| `ipc.lib` | lazy | the byte channels (section 2) |
| `sprite.lib` | eager | the sprite API (section 8) |
| `mouse.lib` | eager | the Commodore **1351** reader: `MOUSE_READ` (raw x/y, signed deltas, the button lines), `MOUSE_ENABLE`, `MOUSE_DISABLE`, behind one dispatching call entry |

Each is eager or lazy, and a caller never needs to know which: the signature is the
kernel call's own, so `kStrlen` reads the same however the library came to be there.
[dynamic-libraries.md](dynamic-libraries.md) and
[library-call-inventory.md](library-call-inventory.md) cover the machinery and every
entry.

## 6. Screens and text

- **Every screen is a 10 KB REU bitmap slot** (28 of them). A task can own several
  virtual screens with their own cursor, colours and charset.
- **Surfaces are handed over, not shared by accident.** `kAllocScreen` takes one,
  `kSwitchView` displays a task's own screen and takes keyboard focus, `kShareScreen`
  attaches a task to another's screen (which is how the shell's commands print),
  `kFreeScreen` releases it. The whole screen state — framebuffer, matrix, colours,
  cursor, char shadow — follows the display.
- **Text is a glyph layer**, so it takes the surface's text colour and mixes with
  graphics: `kPrintChar`/`kPrintString`/`kPrintAt` for the text cursor, `kPrintGlyph`
  and `kPrintGlyphAt` for custom glyphs, `kBlitChar`/`kBlitCharRev` to place a
  character at an explicit cell without touching the cursor.
- **Scroll regions.** A task can restrict output to a band of rows
  (`kSetScrollRegion`), and the region scrolls on its own. This is what a terminal, a
  multi-pane console or a fixed HUD is built from.
- **Char shadow, cursors and colours.** Per-task text colour, cursor colour, cursor
  enable, and an optional char shadow that mirrors what is on screen for a task whose
  surface is not displayed.
- **Custom charsets** load as `.fnt` files (`setfont`) and banners as `.bnr` images
  (`banner`), both straight from the REU filesystem.

## 7. Graphics

`gfx.lib` draws straight into the task's bitmap surface, in either hires or
multicolour mode, in the current graphics colour:

- **Primitives**: `kPlot`, `kLine`, `kBox`, `kFillBox`, `kCircle`, `kEllipse`,
  `kFloodFill`, `kClearBitmap`, `kSetGfxColor`, `kFillMatrix`, `kFillColorRam`.
- **Pixel-positioned text**: `kGfxChar`, `kGfxString`, both hires- and
  multicolour-aware.
- **Read-back**: `kGetPixel`, `kCharAt`.
- **Mode switching in place**: `kSetGfxMode`.

See [lib-gfx.md](lib-gfx.md).

## 8. Sprites

- **All eight hardware sprite slots are task sprites** — nothing is reserved.
- **State is per task and swapped with the display.** A task's sheets, shadow registers
  and frame indices live in its own 128-byte REU block and are installed when its
  surface is displayed, so several sprite tasks coexist and each keeps its own art.
- **The API**: `kSpriteSheet` (resolve a `.spr` sheet from the filesystem into a slot),
  `kSpriteFrame`, `kSpritePos`, `kSpriteReg` (enable, colour, priority, MC mode,
  expansion) and `kSpriteCollide` (the hardware collision latches).
- **Collision is the VIC's own**: per-pixel, latched, and accumulated until read.
- See [lib-sprite.md](lib-sprite.md) and [programmers-guide.md](programmers-guide.md) →
  *Sprites*.

## 9. Sound

- **`sid.lib` plays Compute!'s Sidplayer tunes** (`.mus` files) with a single call:
  `kSidPlay` blocks for the length of the tune and `kSidHush` silences the chip.
- **The library owns all machine-speed compensation.** A caller asks for the tune's
  own tempo and transpose; the library derives the ticks-per-jiffy and the pitch shift
  from the machine's declared speed, so the same call is right on any machine.
- **The SID is a claimed resource.** A second player is refused, `kill` silences the
  chip for a task that declared `sid.lib`, and `sidrst` is the manual fallback.
- See [lib-sid.md](lib-sid.md).

## 10. Storage: the REU filesystem

- **A flat filesystem in REU bank 5**: 512 fixed 32-byte directory entries and a data
  area, with `format`, `save`, `delete`, `rename`, `dirEntry`, `create`, `open`,
  `readAt` and `writeAt`. The shell's `copy` and `compact` commands are built on those
  primitives rather than being calls of their own.
- **It persists because it is an image.** The filesystem lives in the REU image file,
  so files saved in one session are there in the next. `tools/build-reu.ps1` seeds a
  fresh image from the task list and the project's data files.
- **It is the loader's source.** Every `.tsk`, `.com` and `.lib` is a file here; the
  same API serves the shell's `save`/`load`/`dir`/`type`/`fsinfo`, the editor's
  documents, the games' hi-score tables and BASIC's working file.
- **`format` gives you an empty one, `compact` reclaims the holes, `fstest` proves the
  bank boundary.** See [lib-filesys.md](lib-filesys.md).

## 11. The shell and the commands

The shell boots as a task and gives you line editing, cursor keys, mid-line editing
and a blinking block cursor.

Shell built-ins: `help`, `clear`, `view`, `exit`, `run`, `pool`, `runbatch`, `print`,
`fsinfo`, `save`, `load`, `wait`.

Command tasks (each a `.com` that runs on the shell's screen and exits):
`ps`, `dir`, `time`, `kill`, `pause`, `resume`, `prio`, `format`, `type`, `setfont`,
`rename`, `copy`, `del`, `compact`, `banner`, `sidrst`, `blink`, `keyrpt`, `speed`,
`mouse`, `fstest`, `ipctest`, `mtest`.

`edit` is the full-screen text editor: 25×40, insert/overwrite, two-way scrolling with
content-aware cursor movement, mark/copy/cut/paste and a document that grows on demand.
Full reference: [edit.md](edit.md).

`runbatch <file>` runs a `.bat` script; `boot.bat` in the image is what declares the
machine's speed at boot and can start tasks before you touch the keyboard.

## 12. What ships in the image

| | |
|---|---|
| **The system** | `shell` (reentrant), `edit`, `basic` — EhBASIC with bitmap-graphics commands and a persistent 64 KB REU working file |
| **Games** | `gortris` (Tetris, with attract loop, level select and REU-file hi scores), `grknoid` (Arkanoid: paddle, ball, brick wall, five levels), `godzi` (the two-mode sprite demo). Full reference: [gortris.md](gortris.md) and [grknoid.md](grknoid.md) |
| **Graphics** | `spirog` (integer spirograph, presets, single shapes or a montage), `gfxdemo`, `fpdemo` (a graphics demo for `fp.lib`: a sine and cosine wave drawn pixel by pixel across the full bitmap), `sprdemo` (eight sprite balls with real collision) |
| **Pictures** | `grpaint` — the **1351 paint program**: a full-screen canvas in hires or multicolour, with the palette, thirteen tools and an undo/redo ring in a band over the bottom two cell rows, saved as `.pic` files; `grview`, the viewer for those files. Full reference: [gordonpaint.md](gordonpaint.md) |
| **Other** | `maze` (re-runnable), `clock`, `sidplay` |
| **Animation** | `granim` — a full-screen animation played from the REU filesystem (`.anm` chunks plus a manifest). The bundled film is 360 multicolour frames at 24 fps, 15 seconds, a greyscale conversion of *Caminandes 1: "Llama Drama"* (credit in [../NOTICE](../NOTICE)). `+`/`-` change the rate, SPACE pauses, `q` exits |
| **Libraries** | the nine in section 5 |
| **Data** | charsets, sprite sheets, banners, three tunes, and the animation chunks under `assets/anim/` |

## 13. The kernel interface

- **A jump table of documented entry points** (196 addresses today) — `kPrintChar`,
  `kMalloc`, `kSpritePos`, `kReuToC64` and the rest — plus the `syscall` dispatcher for
  the operations that need a task-slot argument or a block.
- **Every entry documents its clobbers.** On a 6502 that is the difference between
  working code and an intermittent bug; the tables in
  [kernel.md](kernel.md) and the [kernel-call-inventory.md](kernel-call-inventory.md)
  are the contract.
- **The documentation is gated like code.** Two build tools fail if the inventories and
  the jump table disagree, so a new entry cannot land undocumented.

## 14. Building and running

- **Toolchain**: VS64 in VS Code driving KickAssembler and Ninja. `tools/build-kernel.ps1`
  builds the kernel, `tools/build-tasks.ps1` the tasks and libraries, `tools/build-reu.ps1`
  the REU images.
- **The build fails loudly.** Failed `.assert`s fail the build (a wrapper catches
  KickAssembler's exit code), the memory map's pockets and totals are pinned, the REU
  image's contents are checked against the binaries just built, and three tripwires
  check offset arithmetic that no assert can see.
- **Running it**: `tools/launch-vice.ps1` starts VICE with the REU image and the kernel,
  or use the F5 dropdown — *VICE with REU* to keep the existing image, *VICE with fresh
  REU* to rebuild it first.
- **One command line to remember**: VICE needs `-speed 200` with `REU.bin`, and a C64
  Ultimate needs no speed setting with `REU-C64U.bin`.
- **The environment itself** — the toolchain, the three build stages, the gate list and
  the launch flows: [development.md](development.md).

---

## Where to go next

| Topic | Document |
|---|---|
| Setting up the toolchain and building the tree | [development.md](development.md) |
| What it cannot do, and the way around each limit | [limitations.md](limitations.md) |
| Running it, command by command | [quick-start.md](quick-start.md) |
| Writing your first task, step by step | [tutorial.md](tutorial.md) |
| Writing a task or a command | [writing-relocatable-tasks.md](writing-relocatable-tasks.md) |
| The whole programming guide | [programmers-guide.md](programmers-guide.md) |
| Kernel calls and their clobbers | [kernel.md](kernel.md), [kernel-call-inventory.md](kernel-call-inventory.md) |
| The system calls | [syscall.md](syscall.md) |
| How it is put together | [architecture.md](architecture.md), [memory-map.md](memory-map.md) |
| Libraries | [lib-gfx.md](lib-gfx.md), [lib-sid.md](lib-sid.md), [lib-sprite.md](lib-sprite.md), [lib-ipc.md](lib-ipc.md), [lib-filesys.md](lib-filesys.md), [lib-string.md](lib-string.md), [lib-time.md](lib-time.md), [lib-fp.md](lib-fp.md), [lib-mouse.md](lib-mouse.md) |
| Dynamic libraries and the loader | [dynamic-libraries.md](dynamic-libraries.md) |
| The `.pic` picture format | [pic-format.md](pic-format.md) |
| Gordon Basic | [gordonbasic.md](gordonbasic.md) |
| What could come next | [future-improvements.md](future-improvements.md) |
