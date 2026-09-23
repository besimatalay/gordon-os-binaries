# GordonOS - Binaries

> Preemptive multitasking kernel for the Commodore 64 with REU — **v1.0 beta**

Prebuilt binaries for **GordonOS**, a preemptive multitasking operating
system kernel for the Commodore 64 with a RAM Expansion Unit (REU). This
repository contains only the binaries needed to *run* GordonOS - source code
is not included here.

## The files

| File | What it is |
|---|---|
| `build/gordon-os.prg` | The kernel. Autostart it in VICE, or on a real machine with an REU. |
| `reu/REU.bin` | The REU image to boot it with **in VICE**, whose `boot.bat` declares `speed 200` — the 200% fast-forward the launch scripts use. |
| `reu/REU-C64U.bin` | The same image built for a **C64 Ultimate** (or any real machine): `speed 100`. Its turbo raises the CPU speed without moving the SID's clock or the video timing, so a real machine must not be told 200%. |

The two images differ only in that one declaration, and they are alternatives: boot the
kernel with one of them.

## What is GordonOS?

GordonOS is a from-scratch OS kernel for the C64 + REU. Both KERNAL and BASIC
ROMs are banked out, giving the kernel full control of all 64KB of RAM.

Everything is bitmap: the VIC-II stays in hires bitmap mode permanently, and
"text" is an 8x8 glyph layer blitted on top of bitmap surfaces. Every screen
is a 10 KB REU bitmap slot, and each task can own up to 8 virtual screens with
their own cursor, colors and charset.

Fully relocatable, reentrant and re-runnable tasks are a major feature: the
same binary can be loaded into multiple instances at any free address
(reentrant shares one code copy; re-runnable loads a fresh copy per `run`).
The system supports up to 24 concurrent tasks, each with its own full 256-byte
stack and a preserved zero-page region. Cold kernel code (time/filesys/gfx/fp/string/sid/ipc)
ships as shared `.lib` binaries loaded on demand.

Key features:

- Preemptive multitasking - CIA #1 timer interrupts at ~60 Hz, round-robin
  scheduler with per-task priority (0-5)
- Dynamic task loader - `run <name>` loads relocatable + reentrant +
  re-runnable task binaries from the REU filesystem at runtime, with pool
  eviction when the pool is full
- Dynamic kernel libraries - shared `.lib` binaries (time/filesys/gfx/fp/string/sid/ipc) loaded
  on demand
- Generic kernel heap - task-owned memory blocks preserved across eviction;
  `pool` shows the pool map
- Gordon Basic (derived from EhBASIC) - full floating-point BASIC with
  bitmap-graphics commands (`mode`/`pen0`-`pen3`/`plot`/`line`/`box`/`circle`/
  `ellipse`/`flood`/`gchar`/`gtext`/…), a persistent 64 KB REU working file
  `basicwrk` opened with `run basic` (reused if present, created if absent,
  deleted on `exit`), with `save`/`load`
  to `.bas` files — see the [Gordon Basic language reference](docs/gordonbasic.md)
- Shared floating-point library - `fp.lib` (the EhBASIC FP core) consumed
  by BASIC and the `fpdemo` task, which draws a sine + cosine wave pixel by
  pixel across the full bitmap
- REU-accelerated context switches - each task gets its own full 256-byte
  stack, saved/restored by DMA
- Per-task ZP preservation - tasks can preserve their own zero-page (ZP)
  memory across context switches
- Bitmap graphics - REU-backed bitmap surfaces (28 slots) in hires (320x200)
  and multicolor (160x200); `gfx.lib` draws lines/boxes/circles/flood-fill and
  pixel-positioned text, all MC-aware
- Thread support - tasks can spawn child threads that share the parent's memory
- REU filesystem - `format`/`save`/`load`/`del`/`rename`/`copy`/`dir`/`type`/`fsinfo`/`compact`, persists across reboots
- IRQ-driven keyboard - 16-byte ring buffer, key repeat, F-key screen switching
- Interactive shell - line editing, cursor keys, blinking cursor,
  custom-glyph `.bnr` banners (`banner <file> <row> <col>`), and a machine
  speed the OS derives its timings and its music from (`speed <percent>`).
  **100** (the C64 Ultimate image, `REU-C64U.bin`) and **200** (the VICE image,
  `REU.bin`) are what the shipped images declare; higher values are not
  recommended, because the pitch shift is one whole octave per step and one is
  all a 200% machine needs
- Full-screen text editor - the `edit` task: 25×40, insert/overwrite modes,
  two-way scrolling with content-aware cursor movement; the document grows on
  the fly (24-line chunks are kMalloc'd/freed as you type, up to 192 lines).
  Region editing: `STOP+M` marks a selection (cursor keys extend it, drawn in
  reverse video), `STOP+Y` copies it to an in-memory clipboard, `STOP+K` cuts
  it, `STOP+P` pastes at the cursor
- Batch file support as .bat files
- Dynamic loading of charsets as .fnt files
- Sprite sheets as .spr files (64-byte frames, authored as `assets/sprites/*.txt`
  and converted by `tools/gen-sprites.py`; seeded by the `$assets` array in
  `tools/build-reu.ps1`) — see `docs/programmers-guide.md` → *Sprites*.
- **Games** - `run gortris` is a full Tetris: a 10x20 board, attract screens,
  level select, the reference's game-over animation, three hi scores kept in the
  REU filesystem and typed in under the blinking cursor, keyboard *and* joystick,
  and its own music (an arrangement of Korobeiniki played through `sid.lib`). It
  is ported from Wiebo de Wit's `tetris.c64` (MIT) — see `NOTICE` for that port
  and for the piano sheet the tune's notes were read from.
  `run grknoid` is **Gorkanoid**, an Arkanoid/Breakout game: a paddle and a ball
  against a wall of bricks, five lives, four attract screens, a game-over screen
  whose tune plays through before it leaves, the same REU-filesystem hi scores
  and the same keyboard-or-joystick choice, with the paddle's step accelerating from
  1 px to 3 px while a direction is held. Its music is three Compute's Gazette
  Sid Collection tunes (`katmand`/`immig`/`firstdt`, one per mode) played through
  `sid.lib` out of one buffer held for the session — see `NOTICE` for the collection credit
## Files

| File            | Size   | Purpose                                     |
|-----------------|--------|---------------------------------------------|
| `gordon-os.prg` | ~63 KB | Kernel image (load into VICE)               |
| `REU.bin`       | 16 MB  | RAM Expansion Unit image (filesystem+tasks) |

Both files are required: the kernel boots the shell and bundled tasks from
the REU filesystem.

## Run it with VICE

Requires [VICE](https://vice-emu.sourceforge.io/) **3.10 or later** (`x64sc`)
with REU support. Older versions use the removed `-reuimagesize` flag.

```bash
x64sc -speed 200 -reu -reusize 16384 -reuimage /absolute/path/to/REU.bin -reuimagerw gordon-os.prg
```

`-speed 200` runs VICE at 200% of real time, which is what **`REU.bin` is built for**.
The OS keeps the machine's speed in one runtime setting — **`speed <percent>`**, declared
by a line in the image's `boot.bat` — and derives the rest from it: the kernel's **cursor
blink** and **keyboard repeat** tick counts, and **sid.lib**'s pitch and tempo
compensation, so neither the music nor the keyboard needs per-task tuning. Change it live
with `speed` at the shell; `blink <n>` / `keyrpt <delay> <repeat>` still override the
timings afterwards, and must be run *after* `speed`.

> **A speed change is not only a blink/repeat change.** `-speed` runs the whole emulated
> machine faster, so everything measured against the host's clock moves with it: the blink
> and key repeat above, a game's perceived pace (its rules are emulated time, so it stays
> self-consistent, but the player feels the ratio), time-sensitive task output (the `clock`
> task), and **the SID's pitch** — a voice's output frequency is its register value scaled
> by the CPU clock, so at 200% every note is an octave higher. Declaring the speed is what
> absorbs the keyboard's and the music's share of that; the [quick-start
guide](quickstart.binaries.md) has the table of values.
>
> **Two images, one setting.** `REU.bin` declares 200% for VICE. **`REU-C64U.bin`** is the
> same image built with `speed 100`, for a C64 Ultimate — see below.
>
> **A C64 Ultimate needs none of this.** Its turbo is a *CPU* speed setting (up to 48x, 64x on
> an Elite-II): the CPU gets more of the fast system clock's time slots, the VIC keeps
> priority, and accesses that leave the board — the SID sockets among them — still run at
> 1 MHz. So the SID is clocked as it is at 1x and **the pitch does not change**, the video
> timing stays standard (blink and key repeat included), and the music these binaries carry
> needs no transpose. Turbo buys CPU throughput, not wall-clock speed.

`-reuimagerw` writes the REU image back to disk when VICE exits, so files
you `save` in GordonOS persist. Or drag `gordon-os.prg` into the VICE window,
then load the image via **Settings > Cartridges > RAM Expansion Module >
16384K > Browse**, select `REU.bin`, and check **"Write image on detach/emulator
exit"** there so saved files persist.

## Run on a C64 Ultimate / Ultimate 64

The same files run on real hardware via the built-in 16 MB REU of the
Ultimate-II+ cartridge or an Ultimate 64 board. The REU image is a raw
16,777,216-byte memory dump, and the Ultimate accepts any filename or
extension, so `REU.bin` works as-is.

1. Copy `gordon-os.prg` and `REU.bin` to a FAT32 USB flash drive and insert it.
2. Boot into the Ultimate menu (middle button on the Ultimate-II+; the menu
   button on an Ultimate 64).
3. Press **F2**, open **C64 and Cartridge Settings**, and enable the
   **RAM Expansion Unit (REU)** with a size of **16 MB**.

Then load the REU image using either method:

- **Manual on-demand load:** in the file browser, highlight `REU.bin`, press
  **Return**, and choose **Load into REU**.
- **Persistent boot preload:** in settings, set **REU Preload Image** to
  `REU.bin` on the USB drive (e.g. `/Usb0/REU.bin`) and set **REU Preload** to
  **Enabled**.

Finally, return to the file browser, select `gordon-os.prg`, press **Return**
and choose **Run** (DMA load) to start GordonOS.

### Persistence

The Ultimate does not automatically write the REU contents back to USB. Any
changes GordonOS makes (for example files you `save`) live in REU memory only
until you export them. Before powering down:

1. Press the **Menu** button to interrupt the C64.
2. Press **F5** to open the Command/Action menu.
3. Navigate to **C64 Machine**.
4. Select **Save REU Memory**.
5. Enter a filename (e.g. `REU.bin` to overwrite the image) and press Enter to
   write the raw 16 MB block back to the USB drive.

## Quick start

See the [quick-start guide](quickstart.binaries.md) for what you can do once
the shell boots.

## License / Notice

GordonOS is licensed under the GNU GPL v2 or later - see `LICENSE.md`.
Third-party notices (EhBASIC, filesystem code, and the Enhanced SID
Player used by the `sidplay` task) are in `NOTICE`.

The `sidplay` player routine is a port of COMPUTE!'s Enhanced SID
Player (Craig Chamberlain, 1986) as disassembled by Chris Zinn (2025).
Neither the original nor the disassembly carries an explicit license —
see `NOTICE` before redistributing.

## Contact

The GordonOS source repository is **not public yet** — the system is still in
active development. If you'd like to contribute, or have help, suggestions, or
code to offer, contact **Besim Atalay** at
[besim.atalay@gmail.com](mailto:besim.atalay@gmail.com).
