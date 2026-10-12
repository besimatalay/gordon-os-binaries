# `time.lib` — Library Reference

Real-time clock library (CIA #1 Time-of-Day, 12-hour AM/PM format).

| | |
|---|---|
| Lib ID | 0 |
| Entries | 3 (`getTime`, `setTime`, `printTime`) |
| Load policy | **lazy** — auto-loaded on the first call |
| Call indices | 0–2 (jump entries patched via `libJumpLo/Hi` + `libInitLo/Hi`) |
| Kernel entry points | `kGetTime`, `kSetTime`, `kPrintTime` |
| Source | `src/libs/time.asm` |

## Calling

Call the kernel entry points (`kGetTime` etc.) from any task. Each is a
lazy cold stub: on the cold path it saves your registers + `kArg` block,
loads `time.lib` from the REU FS, restores them, then jumps through the
now-patched jump entry. On the warm path it's a direct 3-cycle `jmp`.

- If the lib **cannot be loaded** (missing from the FS), the stub returns
  immediately with **C = 1** and nothing else happens.
- A task that uses the clock does **not** need a `libMask` bit — lazy load
  covers it. `pool` shows the `time.lib` row while it is resident.
- **Cold-path caveat:** a lazy load clobbers `srcPtr`, `taskNamePtr` and
  `spawnPtr` (kernel scratch pointers). The lib routines re-set what they
  need; your own code should not hold values in those pointers across a
  `kGetTime`/`kSetTime`/`kPrintTime` call.

## Clock format

The CIA TOD registers give 4 BCD-ish bytes:

| Byte | Value |
|---|---|
| 1/10 s | 0–9 |
| seconds | 0–59 |
| minutes | 0–59 |
| hours | 1–12, **bit 7 = AM/PM flag** (VICE convention: bit 7 set = AM, clear = PM) |

The kernel's `time`/`clock` commands are consumers; see also
[`lib-fp.md`](lib-fp.md) style reference for the remaining libs.

## Entries

### `kGetTime` — read the clock

- **Input:** none.
- **Output:** `kArg` = 1/10 s, `kArg+1` = seconds, `kArg+2` = minutes,
  `kArg+3` = hours (bit 7 = AM/PM per the table above).
- **Clobbers:** A. (`X`, `Y` preserved by the routine itself.)
- **Notes:** reads the hardware TOD registers; reading `$DC0B` latches the
  whole TOD.

```asm
jsr kGetTime
lda kArg+2              // minutes
sta somewhere
```

### `kSetTime` — set the clock

- **Input:** `kArg` = 1/10 s, `kArg+1` = seconds, `kArg+2` = minutes,
  `kArg+3` = hours (bit 7 = AM/PM).
- **Output:** none (clock running when it returns).
- **Clobbers:** A.
- **Notes:** writing `$DC0B` stops the TOD clock; the final read of `$DC08`
  restarts it.

```asm
lda #12                 // 12 o'clock PM (bit 7 clear, VICE convention)
sta kArg+3
lda #34; sta kArg+2     // 34 minutes
lda #56; sta kArg+1     // 56 seconds
lda #0;  sta kArg       // 0 tenths
jsr kSetTime
```

### `kPrintTime` — print `HH:MM:SS AM/PM`

- **Input:** `X` = column, `Y` = row (the blit position); reads the clock
  itself.
- **Output:** blits `"HH:MM:SS AM/PM"` (11 chars, no newline) at `(X, Y)`
  on the **displayed** surface via `kBlitChar` — no cursor advance and no
  char-shadow mirror.
- **Clobbers:** A, X, Y, `kPtr`, `srcPtr`, and the `kArg` block (it builds
  the time in `kArg` and calls `kByteToHex`/`kBlitChar`).
- **Interrupt state:** preserved — it does `php`/`sei` … `plp` so the
  time string can't be torn by preemption.
- **Notes:** `kBlitChar` writes the displayed framebuffer only, so callers
  that share a screen must gate on `kSurfDisplayed` (C=1) and skip the call
  while backgrounded (see `clock.inc`). Uses a lib-local buffer, so there
  is no fixed-address dependency on kernel data.

## Accuracy and limits

`time.lib` is a thin wrapper over the **CIA #1 Time-of-Day** registers
(`$DC08`/`$DC09`/`$DC0B`), so everything it reports is only as good as that
emulated clock:

- **Nothing initialises the TOD.** No kernel code writes it — the only writer in
  the tree is `kSetTime` — so a task that displays the time (the `clock` task, or
  `time` with no arguments) shows a meaningful value only after
  `time hh:mm[:ss] [am|pm]` has set it.
- **100% emulation speed only.** It is accurate only while the CPU runs at 100%;
  any other VICE `-speed` value makes the displayed time drift against the wall
  clock.
- **Unreliable under REU load.** An REU operation halts the processor while it
  runs and time is lost, so the clock falls behind whenever the system is doing
  file I/O, task loads or surface switches. Treat it as a rough indication, not a
  timepiece.
