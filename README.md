# GordonOS - Binaries

Prebuilt binaries for **GordonOS**, a preemptive multitasking operating
system kernel for the Commodore 64 with a RAM Expansion Unit (REU). This
repository contains only the binaries needed to *run* GordonOS - source code
is not included here.

## What is GordonOS?

GordonOS is a from-scratch OS kernel for the C64 + REU. Both KERNAL and BASIC
ROMs are banked out, giving the kernel full control of all 64KB of RAM.

Everything is bitmap: the VIC-II stays in hires bitmap mode permanently, and
"text" is an 8x8 glyph layer blitted on top of bitmap surfaces. Every screen
is a 10 KB REU bitmap slot, and each task can own up to 8 virtual screens with
their own cursor, colors and charset.

Fully relocatable and reentrant tasks are a major feature: the same binary can
be loaded into multiple instances at any free address. The system supports up
to 24 concurrent tasks, each with its own full 256-byte stack and a preserved
zero-page region.

Key features:

- Preemptive multitasking - CIA #1 timer interrupts at ~60 Hz, round-robin
  scheduler with per-task priority (0-5)
- Dynamic task loader - `run <name>` loads relocatable + reentrant task
  binaries from the REU filesystem at runtime, with pool eviction when the
  pool is full
- [Gordon Basic](docs/gordonbasic.md) (derived from EhBASIC) - full
  floating-point BASIC, `run basic`
- REU-accelerated context switches - each task gets its own full 256-byte
  stack, saved/restored by DMA
- Per-task ZP preservation - tasks can preserve their own zero-page (ZP)
  memory across context switches
- Bitmap graphics - REU-backed hires bitmap surfaces (28 slots), text/bitmap
  coexistence via char shadows
- Thread support - tasks can spawn child threads that share the parent's memory
- REU filesystem - `format`/`save`/`load`/`del`/`dir`, persists across reboots
- IRQ-driven keyboard - 16-byte ring buffer, key repeat, F-key screen switching
- Interactive shell - line editing, cursor keys, blinking cursor

## Files

| File            | Size   | Purpose                                     |
|-----------------|--------|---------------------------------------------|
| `gordon-os.prg` | ~63 KB | Kernel image (load into VICE)               |
| `REU.bin`       | 16 MB  | RAM Expansion Unit image (filesystem+tasks) |

Both files are required: the kernel boots the shell and bundled tasks from
the REU filesystem.

## Run it with VICE

Requires [VICE](https://vice-emu.sourceforge.io/) (`x64sc`) with REU support.

```bash
x64sc -reu -reuimagesize 16384 -reuimage /absolute/path/to/REU.bin gordon-os.prg
```

Or drag `gordon-os.prg` into the VICE window, then load the image via
**Settings > Cartridges > RAM Expansion Module > 16384K > Browse** and
select `REU.bin`.

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

See [Quick start](docs/quickstart.md) for what you can do once the shell
boots.

## License / Notice

GordonOS is licensed under the GNU GPL v2 or later - see `LICENSE.md`.
Third-party notices (EhBASIC, filesystem code) are in `NOTICE`.
