# GordonOS - Binaries

Prebuilt binaries for **GordonOS**, a preemptive multitasking kernel for the
Commodore 64. This repository contains only the binaries needed to *run*
GordonOS - source code is not included here.

## Files

| File            | Size   | Purpose                                     |
|-----------------|--------|---------------------------------------------|
| `gordon-os.prg` | ~63 KB | Kernel image (load into VICE)               |
| `REU.bin`       | 16 MB  | RAM Expansion Unit image (filesystem+tasks) |

Both files are required: the kernel boots the shell and bundled tasks from
the REU filesystem.

## Run it

Requires [VICE](https://vice-emu.sourceforge.io/) (`x64sc`) with REU support.

```bash
x64sc -reu -reuimagesize 16384 -reuimage /absolute/path/to/REU.bin gordon-os.prg
```

Or drag `gordon-os.prg` into the VICE window, then load the image via
**Settings > Cartridges > RAM Expansion Module > 16384K > Browse** and
select `REU.bin`.

After boot the shell prompts; try `dir`, `ps`, `run border`, `help`.

## License / Notice

See the `NOTICE` file in this repository.
