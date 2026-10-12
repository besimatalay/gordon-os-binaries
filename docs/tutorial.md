# GordonOS — A Developer Tutorial

> A guided path from "I have read the README" to "I have written and shipped a task".
> Each chapter is a small, runnable step and explains *why* the code is shaped that way.
>
> This is not a 6502 tutorial — it assumes you can read assembly and know what a
> `jsr` costs. It is a tutorial on **this** system: its headers, its ABI, its traps
> and its habits.
>
> Reference material this guide leans on: [features.md](features.md) (what the OS
> does), [development.md](development.md) (the toolchain and the gates),
> [writing-relocatable-tasks.md](writing-relocatable-tasks.md) (the task format in
> full), [kernel.md](kernel.md) (every call and its clobbers),
> [programmers-guide.md](programmers-guide.md) (the runtime model),
> [limitations.md](limitations.md) (what it cannot do).

---

## Before you start

**Who this is for.** You can read 6502 assembly and you know what a `jsr` costs. You
do **not** need to know the Commodore 64: every chapter names the register, timer or
chip a rule comes from, and the documents it links spell the hardware out. If the
instruction set itself is new to you, work through a general 6502 introduction first —
this guide teaches *this* system, not the CPU.

**What has to be working before chapter 1.** A built machine: the kernel PRG, a REU
image and VICE. That is [quick-start.md](quick-start.md) → *Option 2: Build from
source* plus [development.md](development.md) §1–§2. Two things a fresh clone does
**not** have, and the exact error each one produces:

| Missing | The build stops with |
|---|---|
| `.vscode/settings.json` — copy the sample once and edit the four `vs64.*` paths | `KickAss.jar not found at:` followed by **nothing**. The empty path is the tell: the settings file is missing, not KickAssembler |
| `build/build.ninja` — VS64 generates it the first time the folder is opened as a project | `Missing build/build.ninja - run VS64 project generation once` |

### Prove the loop first: five minutes, before any assembly

The commonest way to lose an afternoon is to write a chapter's code before you know
the build actually reaches the machine. Do this once:

1. Press **F5** with **Build & Launch with fresh REU** selected. VICE starts and
   GordonOS boots to a shell prompt.
2. At the prompt: `help` (the commands), `dir` (the files in the image), `ps` (the
   running tasks). Then `run maze` and press `q` — you have run a task and taken your
   prompt back.
3. Now change something. In `src/tasks/cmd/blink.inc` the clamp is `lda #1`; make it
   `lda #30`, press **F5** again, and type `blink 0`. The blink interval is now about
   half a second: the clamp hands `blink 0` the constant you wrote, not its own
   one-tick minimum.

You have edited a compiled program, rebuilt it into the REU image and watched the
change take effect. Every chapter from here is a variation on those three steps.

> **If step 3 shows no change, you have met the image trap.** The task binaries live
> *inside* `reu/REU.bin`, so a rebuild that is not reseeded, or the wrong F5 flow,
> boots the previous copy. `pwsh tools/check-reu-current.ps1` answers it in one line —
> [§14](#14-finding-out-what-went-wrong) explains why.

**How to read a chapter.** Each one is a piece of the shipping code, a **What to
notice** list (the rules it demonstrates) and a **Try this** (the smallest exercise
that uses them). Do the exercise: a rule you have broken once is a rule you keep.
When something misbehaves, read [the traps table](#the-traps-that-cost-the-most-time)
*first* — nine symptoms in ten are already named there, with their cause.

**The jargon.** This system has its own vocabulary, and the C64 adds a hardware one on
top of it. The tree keeps **one** glossary of record —
[architecture.md → Glossary](architecture.md#glossary), about fifty terms from `CIA` and
`RTS` up to `surface`, `fixup` and `raster commit`. Read it once and the rest of the
documentation stops needing footnotes; the chapters below introduce the task-author words
(`kArg`, `libMask`, the instance buffer) where they are first used.

**If you get stuck.** [CONTRIBUTING.md](../CONTRIBUTING.md) says how to ask and what to
include. A documented rule that turns out to be wrong is a documentation bug — please
report it.

---

## 1. What you are actually writing

Five facts, and most of the tutorial follows from them:

1. **Everything user-facing is a task** — the shell included. There is no privileged
   mode and no second kind of code.
2. **A program is one relocatable binary** in the REU filesystem: a 256-byte header,
   then the code body, then a fixup table the loader uses to place it at any free
   pool address.
3. **The kernel is a call library.** Most things are a plain `jsr` to a fixed
   address in the `$E000` jump table (`jsr kPrintString`). The 14 **syscalls** are
   only for operations that need a task-slot argument or a block of arguments
   (`exit`, `spawn`, `kill`, `yield`, `sleep`, `gettid`, semaphores, threads).
4. **Nothing is protected.** Every task sees the same flat 64 KB, so you *declare*
   what you need — a ZP window, an instance buffer, libraries — and the kernel
   honours exactly that. See [limitations.md](limitations.md) §8.
5. **Two clocks.** The timer preempts you at ~59.2 Hz; the display has its own clock
   (`frameCount`, 50.1 Hz PAL). Anything animated or game-paced follows the display.

Two kinds of binary come out of the same pipeline:

| | `.tsk` — a task | `.com` — a command |
|---|---|---|
| Started by | `run <name>` (or another task) | the shell, by typing its name |
| Own screen | allocates one with `kAllocScreen` | shares the shell's with `kShareScreen` |
| Arguments | `KF_TAKES_ARGS` → instance buffer at `dataPtr` | the shell's `cmdArgsBuf` |
| Lifetime | until it exits, or is killed | until it exits — always brief |
| The shell | is not waiting for it | **is blocked until you exit** |

Source layout: a **wrapper** `.asm` (the header) plus a **body** `.inc` (the code),
in `src/tasks/dynamic/` for tasks and `src/tasks/cmd/` for commands. Two files
because the header needs the body's first and last labels, and because the same body
can be wrapped for a second variant.

---

## 2. The shape of a program

Read `src/tasks/cmd/blink.asm` first — thirty lines, no code, everything visible:

```asm
blinkBinStart:
    .word HDR_MAGIC              // +0:  magic 'G','O' (LE)
    .byte KF_RELOCATABLE        // +2:  flags
    .word $5000                  // +3:  origin (page-aligned, nominal)
    .word blinkEnd - blink       // +5:  code size
    .byte 0, 0, 0                // +7:  data size, ZP base, ZP len
    .word 0                      // +10: libMask = 0 (no libraries)
    .byte blinkNameEnd - blinkName  // +12: name len
blinkName:
    .text "blink"
blinkNameEnd:
    .word 0                      // fixup_count (written by the build)
    .word 0                      // fixup_offset (written by the build)
    .fill 256 - (* - blinkBinStart), 0

.import source "blink.inc"
.label blinkEnd = *
```

**What to notice**

- The header is laid out **by hand** — there is no macro. Every field is documented
  in [writing-relocatable-tasks.md](writing-relocatable-tasks.md) §4; the constants
  (`HDR_MAGIC`, `KF_*`) live in `src/kernel/task-header.inc` and are imported for
  you. Write the names, never the numbers, and never re-declare them.
- `.word blinkEnd - blink` is the **code size**, and `blinkEnd` is a label *after*
  the import. Anything you emit before the entry label falls outside this number and
  the loader rejects the file with `? bad task file`.
- `.fill 256 - (* - blinkBinStart), 0` pads the header page. The code body always
  starts at file offset 256, which is what makes the loader's maths simple.
- The two zero words are the fixup count and offset — **the build writes them**. You
  never compute a fixup by hand.
- `KF_RELOCATABLE` is on every task in the tree. The other flags are choices you
  make later (§6 and writing-relocatable-tasks §5).

**Try this.** Add `.assert` guards that fail loudly if you break the two rules that
bite: the entry label must be the first body label, and the wrapper's `origin` must
match `tools/tasks.json`. The pattern is in writing-relocatable-tasks §7.1, and
`assert` is the cheapest debugging you will ever write, because a failed assert
fails the build rather than the machine.

**A correct result looks like** `Made 12 asserts, 1 FAILED!` in the build output, and a
non-zero exit — KickAssembler prints that message and *still exits 0*, which is why every
invocation goes through `tools/kick.ps1`. Call the assembler directly and a broken assert
builds "successfully".

---

## 3. Your first command: parsing arguments

`src/tasks/cmd/blink.inc` sets the cursor blink rate. It is the smallest complete
program in the tree, and it shows the argument convention:

```asm
blink:
    ldx #0
    lda #0
    sta blinkVal                // scratch accumulator = 0
blinkSkip:
    lda cmdArgsBuf,x
    beq blinkClamp              // end of args
    cmp #$20
    bne blinkDigit              // space -> skip
    inx
    jmp blinkSkip
blinkDigit:
    lda cmdArgsBuf,x
    sec
    sbc #$30                    // '0'
    bcc blinkClamp              // < '0' -> done
    cmp #10
    bcs blinkClamp              // > '9' -> done
    pha                         // save digit
    lda blinkVal
    asl                         // *2
    sta blinkVal
    asl                         // *4
    asl                         // *8
    clc
    adc blinkVal                // *8 + *2 = *10
    sta blinkVal
    pla                         // digit
    clc
    adc blinkVal                // *10 + digit
    sta blinkVal
    inx
    jmp blinkDigit
blinkClamp:
    lda blinkVal
    bne blinkSet
    lda #1                      // 0 -> minimum 1
blinkSet:
    sta blinkRate               // write final value to the kernel byte
    lda #SYS_EXIT
    jsr syscall                 // exit

blinkVal:
    .byte 0                     // parse scratch (not kernel state)
```

**What to notice**

- **The shell copies everything after the command word into `cmdArgsBuf`** before it
  spawns you. You parse it directly — index in X, or a ZP pointer. It is
  null-terminated, and it is the shell's buffer, so treat it as read-only unless you
  mean to rewrite it in place (which is how commands turn a filename argument into a
  name the filesystem calls can take).
- The parse is deliberately **permissive**: a stray space is skipped, a non-digit
  ends the number, and no argument at all leaves the accumulator at 0, which is then
  clamped. A command should never crash on bad input — it prints a usage line or
  does something sane.
- `blinkVal` is **scratch in the code body**, not kernel state, and the kernel byte
  is written once with the final value. That is a habit worth copying: compute in
  your own memory, publish once.
- It writes `blinkRate` — a **kernel global** at ZP `$F0` — by name, through the
  alias in `src/tasks/kernel-data.inc`. That file is how a task reads kernel data
  (task states, `frameCount`, `cmdArgsBuf`, `syscalls`' scratch); it is imported for
  every task by the pipeline, so you never `import` it yourself.
- `data_size` is 0 here, so there is no instance buffer. `format` (§4) sets it to 3
  and uses `dataPtr` for its own slot number plus a 2-byte input buffer
  (`kReadString` writes the character and its terminator).

**Numbers in arguments.** There is no `atoi` in the kernel and no decimal printer
missing from it either: `kByteToDec` and `kByteToHex` are resident
(`string.lib` has the string side). Most commands do what `blink` does — accumulate
`*10 + digit` in a byte — and clamp afterwards.

**Try this.** Write `count.com`: print the argument string back with its length, then
exit. Then add a second word to the input and echo only the second one. You will
have used every argument skill the shipped commands use.

**A correct result looks like** `count hello` → `hello length 5`, and `count one two` →
`two length 3`, each followed by a blank line with the prompt back on the next one. The
whole program is [Appendix A](#appendix-a-reference-solution) — try to reach it yourself
first, because the skip loop is the exercise.

---

## 4. A command that talks to the user

`format` is the smallest command that prompts, reads a key, and acts. Its sequence —
with the string printing elided — is the canonical command protocol:

```asm
format:
    lda #SYS_GETTID
    jsr syscall                 // gettid -> A = own slot
    ldy #FORMAT_SLOT
    sta (dataPtr),y             // save own slot
    tax
    lda taskParent,x            // shell slot
    tax
    jsr kShareScreen            // X = shell (preserved); C=0 ok
    bcc formatScr
    lda #SYS_EXIT
    jsr syscall                 // no screen -- exit
formatScr:
    // grab kbFocus -- kReadString returns empty when curTask != kbFocus
    ldy #FORMAT_SLOT
    lda (dataPtr),y
    tax
    jsr kSwitchView             // kbFocus = self (display unchanged: shared)
    jsr kLockScreen
    ...
    lda dataPtr; clc; adc #FORMAT_BUF; sta kPtr
    lda dataPtr+1; adc #0; sta kPtr+1
    ldx #1
    jsr kReadString             // Y = length (0 = empty)
    tya
    pha                         // save length (kNewline clobbers Y)
    jsr kNewline
    pla
    tay
```

**What to notice**

- **`gettid` → `taskParent` → `kShareScreen` is how a command gets a screen.** A
  command has no surface of its own; if you allocate one with `kAllocScreen` your
  output goes somewhere the user is not looking. Every printing `.com` in the tree
  opens with this sequence — some, like `format`, park a byte of their own state in
  the middle of it.
- **`kSwitchView` is about the keyboard, not the picture.** `kReadString` returns an
  empty line when `curTask != kbFocus`, so a command that shares the shell's surface
  must still take focus before it can read. Because the surface is shared, the
  display does not change hands — you only take the focus. This is the single most
  common "my command reads nothing" bug.
- **`kLockScreen` / `kUnlockScreen`** bracket the output. The lock is semaphore 0,
  the one every kernel output routine takes; holding it across a prompt keeps another
  task's output from landing in the middle of yours.
- **Save `Y` around `kNewline`.** `kReadString` returns the length in `Y`, and
  `kNewline` clobbers it. The `tya`/`pha`/`pla`/`tay` dance looks fussy until you
  have debugged the version without it.
- **Exit on every path, including the error path.** The shell is blocked in
  `pcFgWait` until your `taskState` goes to 0. A command that returns with `rts`, or
  loops, hangs the prompt.
- `format` declares `filesys.lib` (`libMask = (1 << LIB_FILESYS)`) because it calls
  `kReuFormat`. **Declare every library you call** or you will `jsr` into a trap stub.

**Try this.** Add a usage line to your `count.com` that prints
`? count <text>` when there is no argument — and note that you must print two
newlines on the way out so the shell's prompt starts on a fresh line.

**A correct result looks like** `count` alone printing `? count <text>` and then a blank
line, with the prompt on the line after it. Take one `kNewline` out and the prompt comes
back on the same line as your output — which is what the two-newline rule is for.

---

## 5. Your first task: owning a screen

A `.tsk` allocates its own surface, draws on it, and is only visible while it is
displayed. The boilerplate and a complete `hello` task are in
[writing-relocatable-tasks.md](writing-relocatable-tasks.md) §8 — read it now, then
come back. The shape is:

```asm
hello:                           // ENTRY -- first label in the body
    lda #$0b; sta kArg           // border
    lda #$00; sta kArg+1         // bg0
    lda #$00; sta kArg+2         // bg1
    lda #$00; sta kArg+3         // bg2
    lda #0                       // 0 = hires-text surface
    jsr kAllocScreen             // C=1: no free surface slot
    bcs helloNoScreen
    ...
    lda #SYS_EXIT
    jsr syscall                  // exit -- never returns
```

**What to notice**

- Colours go in **`kArg..kArg+3`**, the mode goes in `A` (0 = hires-text,
  1 = mc-graphics). `kAllocScreen` clobbers A/X/Y/`kPtr`, so leave nothing live
  across it.
- **Your surface is not shown just because you drew on it.** Either the shell
  displays it (`view <id>`) or you take the display yourself with `kSwitchView`.
  A task that takes the display also takes the keyboard focus — and until it gives
  it back, the user has no prompt.
- **A task that takes the display must be leaveable.** Call `SYS_EXIT` on a key
  (`q` is the house convention) and say so on screen. A task that never ends can
  leave the shell swapped out and unreachable, because the shell is evictable and
  only a task *exiting* triggers a restore. This is not a style point — see
  writing-relocatable-tasks §7.
- `kAllocScreen` is **idempotent for a restored task**: if your task is evicted and
  swapped back in, the entry path runs again and re-uses the surface you already
  own. Do not `kFreeScreen` on the way in.

---

## 6. The loop: waiting, frames and quitting

Four ways to spend time, and the choice matters:

| Mechanism | Use it for |
|---|---|
| `SYS_YIELD` (3) | you have nothing to do this instant; hand the timeslice over |
| `SYS_SLEEP` (13) | a real delay; `kArg+1` = ticks (1-255), so ~17 ms granularity |
| `frameCount` | **anything animated or game-paced** — this is the display's own clock |
| `kReadKey` / `kScanKeyboard` | keyboard, non-blocking |

The reference animation loop is `sprdemo`'s:

```asm
sprdLoop:
    jsr kReadKey                 // non-blocking: A = screen code, 0 = none
    cmp #'q'
    beq sprdExit
    lda frameCount
    cmp SPRD_LAST
    beq sprdNoStep               // same frame as last time -> nothing to do
    sta SPRD_LAST
    jsr sprdTick                 // integrate, bounce, collide
sprdNoStep:
    lda #SYS_YIELD
    jsr syscall                  // never starve the scheduler
    jmp sprdLoop
sprdExit:
    lda #SYS_EXIT
    jsr syscall
```

**What to notice**

- **Compare `frameCount` for *change*, never for elapsed time.** It is an 8-bit
  counter that wraps; store the last value you saw and act when it differs.
- **Never animate on the scheduler tick.** The tick runs at 59.2 Hz and the display
  samples at 50.1 Hz, so a per-tick animation gets 1.18 updates per frame — some
  frames show two steps, the next none, and it reads as a stutter no matter how good
  the arithmetic is.
- **`kReadKey` pops one buffered key**, returns 0 for "none" (and for a key
  *release*, which is queued too), and only sees keys while you hold focus.
  **`kScanKeyboard`** is the safer poll for a background task: it answers `$FF` when
  there is no key *and* when you are not focused, so it cannot swallow another task's
  keystrokes.
- **`SYS_YIELD` returns `A = 0` and `Y = syscall#*2`.** Never keep a live value in A
  or Y across a yield or a sleep; `SYS_SLEEP` also clobbers X.
- If you must block on a line of input, remember `kReadString` needs focus and has no
  timeout; a task that reads lines owns the keyboard while it does.

---

## 7. Where state lives

Three places, in order of preference:

1. **Instance buffer** — set `data_size` in the header and address it through
   `dataPtr` (`$F1/$F2`). Private per instance, survives preemption, costs no ZP.
   This is the default answer.
2. **Declared ZP** — `zp_base`/`zp_len` in the header, inside `$02-$EF`. Private per
   instance like the buffer, but the scheduler DMAs the window to a per-task REU
   shadow **on every context switch**, so declare the narrow window you actually
   need (and note `$F0` is the kernel's blink interval; `$F1-$FF` is kernel-owned).
3. **Never, if the task might ever be reentrant** — a writable label inside the code
   image. With `KF_RE_RUNNABLE` each instance gets a fresh copy so it *happens* to be
   private, which is exactly why the bug stays hidden until someone adds
   `KF_REENTRANT`. See writing-relocatable-tasks §5.1.

`spirog` shows the argument-side of an instance buffer — the loader puts
`run spirog <args>` at `dataPtr`, null-terminated, capped at 64 bytes:

```asm
    lda dataPtr
    ora dataPtr+1
    beq sgClamp                  // no buffer at all
    ldy #0
    lda (dataPtr),y
    beq sgClamp                  // empty args
    jsr sgNum                    // -> A = number, C=1 if one was there
    bcc sgClamp
    sta SG_R
```

Two things to copy here: **guard the pointer before you use it** (`dataPtr` is 0
when `data_size` is 0), and **treat a missing argument as a default**, not an error.

---

## 8. Drawing: text, glyphs and pixels

Every screen is a bitmap. "Text" is a glyph layer over it, so text and graphics mix
freely — which also means a pixel's colour does not come from the draw call.

- **Text**: `kPrintChar`, `kPrintString`, `kNewline`, `kPrintAt`, and
  `kPrintGlyph`/`kPrintGlyphAt` for your own 8-byte glyphs.
- **The cursor**: `kSetCursor` is the only routine that preserves X and Y;
  everything else destroys them. `kGetCursor` returns col in X, row in Y.
- **Scroll regions**: `kSetScrollRegion` gives you a band that scrolls on its own —
  the way to build a HUD, a status line or a multi-pane console. Two warnings: never
  write the last cell of the last row of a region (the wrap scrolls it as it writes),
  and `kSetScrollRegion` clobbers `kArg..kArg+6`.
- **Pixels**: `gfx.lib` — `kPlot`, `kLine`, `kBox`, `kFillBox`, `kCircle`,
  `kEllipse`, `kFloodFill`, `kGetPixel`, `kClearBitmap`, `kSetGfxColor`,
  `kFillMatrix`, and pixel-positioned text (`kGfxChar`, `kGfxString`).
- **The matrix rule.** The drawing routines write *pixel bits only*; the colour comes
  from the cell's video matrix nibbles (and colour RAM in MC). A fresh surface has a
  zeroed matrix, so your first plot is black on black. **Fill the matrix first**:
  `kFillMatrix` with `$10` gives white-on-black hires, and `gfxdemo` opens with
  exactly that.
- **`kPlot` takes the X high bit in the carry**, not in a register: X = column low
  byte, Y = row 0-199, `CLC` for x < 256 and `SEC` with `X = x-256` above that.
- **Reading text back is not free.** There is no character memory to inspect;
  `kCharAt` decodes a cell, and a task that needs to know what is on a surface it is
  not displaying can opt in to a **char shadow** (`kSetCharShadow`, 1 KB per surface).

Reading order for the drawing side: `gfxdemo.inc` (primitives and the matrix fill),
`spirog.inc` (a full-screen render on `frameCount`), `clock.inc` (an overlay that
shares its parent's surface and allocates none).

---

## 9. Sprites

All eight VIC sprites are yours while your surface is displayed. You write a
**shadow**; the kernel publishes it to `$D000-$D02E` once per frame in the vertical
blank, so there is no wrong moment to write and nothing to poll.

The macros are in `src/tasks/sprite-shadow.inc`, imported for every task:

```asm
    sprColour(2, WHITE)          ; sprite 2's own colour   -> $D027+2
    sprOn(%00000101)             ; enable sprites 0 and 2   -> $D015
    ldx #SPR_ID                  ; kSpritePos: X = sprite, A = x lo, Y = y,
    lda xPix                     ;            C = x high bit (x >= 256)
    ldy yPix
    clc
    jsr kSpritePos
    lda #SPR_ID                  ; kSpriteFrame: A = slot, X = frame
    ldx frameIdx
    jsr kSpriteFrame
    jsr kSpriteCollide           ; -> A = sprite-sprite, X = sprite-background
```

Three rules, from the top of that file:

1. **Every accessor is focus-guarded.** Only the task whose surface is displayed may
   write the shadow; a rejected call returns `C=1` having written nothing. Losing the
   display hides your sprites but does not forget them — get it back and the kernel
   re-installs your state, art included.
2. **Nothing to clean up.** A new task starts with an all-zero sprite block, so it
   inherits no enable, no sheet, no mode from the task that had your slot before.
3. **Several sprite tasks coexist.** The kernel keeps exactly one task's sprite state
   live — the displayed one — and swaps in the rest, so there is nothing to allocate
   and nothing to guard.

`kSpriteSheet` binds an FS file to a slot as a flat sequence of 64-byte frames. It
costs ~1,000-3,000 cycles and runs `SEI`'d, so **resolve once at startup, never in the
frame loop** — but note it is **per slot**, because the record is indexed by slot:

```asm
sprdLSheet:
    lda SPRD_SLOT                // A = this ball's slot = its index
    jsr kSpriteSheet
    inc SPRD_SLOT
    lda SPRD_SLOT
    cmp #SPRD_BALLS
    bcc sprdLSheet
```

The art has to be in the image: add your `.spr` to the `$assets` array in
`tools/build-reu.ps1` (see [development.md](development.md) §8). Full reference:
[lib-sprite.md](lib-sprite.md).

---

## 10. Sound

`sid.lib` plays a COMPUTE!'s Sidplayer `.mus` file with one call.

| Call | Input | Notes |
|---|---|---|
| `kSidPlay` | `kPtr` = tune buffer, `kArg` = ticks per jiffy (delay), `kArg+1` = repeats (0 = forever) | **blocks** for the length of the tune |
| `kSidHush` | — | silences the chip; the only reliable way out of a blocking play |

**What to notice**

- **The caller owns the tune buffer** and declares **ZP `$02-$0A`** — a library
  cannot declare ZP, so `sid.lib`'s scratch is your obligation. `sidplay.tsk`'s header
  is the smallest example (`libMask` bit 5 | filesys bit 1, `zp_base` 2, `zp_len` 9).
- **`kSidPlay` blocks**, so it cannot run in the task that owns the display. The
  shipped pattern is a **thread child**: the parent drives the game, the child owns
  the tune, and the parent hushes it when the display is lost. `godzi`, `gortris` and
  `grknoid` all do this.
- **The SID is a claimed resource.** A second player is refused, `kill` silences the
  chip for a task that declared `sid.lib`, and `sidrst` is the manual fallback.
- **Reap the thread child before you exit.** A thread child runs *your* code pages, so
  a survivor is not a tidy-up detail — `exit` does not cascade (only `kill` does), and
  a held child is never reclaimed. See writing-relocatable-tasks §5.

Full reference: [lib-sid.md](lib-sid.md).

---

## 11. Talking to other tasks

**Semaphores.** Four counting semaphores; **index 0 is the screen lock** that every
kernel output routine takes, so `1-3` are yours. Use them for mutual exclusion, and
note they are owner-tracked: a task that dies holding one has it released.
[programmers-guide.md](programmers-guide.md) has mutex, throttle and
producer-consumer examples.

**IPC channels.** `ipc.lib` gives four fixed, anonymous, 128-byte byte rings:
**single-producer / single-consumer**, no framing, no caller zero page.
`kIpcPost` blocks while the ring is full; `kIpcPick` never blocks (`C=1` means empty),
so a consumer polls. `ipctest.com` is the runtime self-test and the best example —
including the range guard:

```asm
    ldx #ITC_CH_END             // 4 -- out of range
    lda #$5a
    jsr kIpcPost                // must be refused: C=1, and the byte thrown away
    bcc itcGuardBad
```

**Thread children.** `SYS_THREADSPAWN` creates a child that shares the parent's code
pages but has its own TCB, stack and zero page. Cheap, named `parent.N`, cascade-killed
with the parent — and it must not outlive the parent, because it runs the parent's
code. Spawn one for a second concurrent activity (music, a producer, a watchdog); reap
it before you exit.

**Spawning by name.** `kDynLoad` is a plain kernel call: point `kPtr` at a
null-terminated FS name followed by the argument string (`"sidplay.tsk\0commodo 2\0"`)
and `jsr kDynLoad`; on success **X is the new slot**. Use it when the user asked for
something by name, and prefer a library when it is code you can hold — a library costs
one `libMask` bit and no slot to watch. `exit` does not cascade, so a task that spawns
must clean up itself.

Full references: [lib-ipc.md](lib-ipc.md), [syscall.md](syscall.md),
writing-relocatable-tasks §5.

---

## 12. Storing data

**Two heaps, both page-granular:**

- **`kMalloc`/`kFree`** — `A` = page count, returns the block address in `kPtr`
  (`C=1` = no space). Blocks are yours until you free them or your task ends, they
  survive pool eviction via a per-slot REU shadow, and they are capped per task at
  64 pages (16 KB). Remember that `kMalloc` can *evict* a neighbouring task to make
  room, and that it clobbers `kArg..kArg+7` — hold no kernel state across the call.
- **Program RAM** — `KF_MALLOC_RAM` in the header makes the loader `kMalloc` a block
  for you at spawn (`basic`, `edit`, `copy`, `banner` use it).

**The REU filesystem** is where bulk data belongs. For fixed-size records, prefer the
in-place I/O set over reading a whole file:

| Call | Use |
|---|---|
| `kReuCreate` | create and zero a fixed-size file |
| `kReuOpen` | resolve a name to a file record (kept in `kArg`) |
| `kReuReadAt` / `kReuWriteAt` | read or write at a 16-bit offset (EOF-clamped; past-EOF writes rejected) |
| `kReuSave` / `kReuLoad` / `kReuDelete` / `kReuRename` / `kReuDirEntry` | whole-block and directory operations |
| `kReuFormat` | an empty filesystem |

That is how the hi-score tables work, and how BASIC keeps its whole program,
variables and strings in a 64 KB working file rather than in the pool. Names are
1-11 characters, screen codes, and a file is at most 65535 bytes. See
[lib-filesys.md](lib-filesys.md) and, for what not to expect,
[limitations.md](limitations.md) §7.

---

## 13. Shipping it

1. **Write the wrapper and the body** (§2). Give every label a unique prefix — the
   whole pipeline shares one KickAssembler namespace, so a bare `start:` collides
   with another task.
2. **Add one manifest entry** to `tools/tasks.json`: `name`, `source`, `origin`,
   `fsName`, `kind`. Never edit `tools/assemble-tasks.asm` — it is generated, and the
   next build reverts your edit.
3. **Build**: the **Build dynamic tasks + REU** task, or F5 →
   *Build & Launch with fresh REU*. A task change never needs a kernel rebuild.
4. **Run it**: `run <name>`, then `dir` / `ps` / `pool` to see it, `view <id>` to look
   at its screen if you did not take the display.
5. **Read the gates, not just the build.** The pipeline verifies relocation for you,
   checks every header, and lints offset arithmetic — but only if you *look* at its
   output. [development.md](development.md) §6 lists all of them.

### The traps that cost the most time

In the order they usually bite. If your symptom is not here,
[§14](#14-finding-out-what-went-wrong) asks the same question from the other end: what
to check, in what order.

| Symptom | Cause |
|---|---|
| `? bad task file` | a label before your entry point (code size too small), or the wrong `HDR_MAGIC` |
| output goes nowhere | a `.com` without the `gettid` → `taskParent` → `kShareScreen` prologue |
| `kReadString` returns empty | you do not hold `kbFocus` — call `kSwitchView` first |
| the shell hangs | a `.com` that returned with `rts` instead of `SYS_EXIT` |
| "worked alone, corrupt in pairs" | writable state in the code image, plus `KF_REENTRANT` |
| garbage from a library call | you called a lib routine without declaring its `libMask` bit |
| nothing on screen | a fresh surface's matrix is zero — `kFillMatrix` first |
| jerky animation | pacing on the scheduler tick instead of `frameCount` |
| a value changes behind your back | a kernel call clobbered X, Y or `kArg` — check [kernel.md](kernel.md) |

**Reading order through the shipped sources** — each one teaches a different layer:

| Read | To learn |
|---|---|
| `src/tasks/cmd/blink.inc` | the smallest command: argument parsing, publishing one value |
| `src/tasks/cmd/format.inc` | the command protocol: share, focus, lock, prompt, read, exit |
| the `hello` example in writing-relocatable-tasks §8 | surface allocation and a leaveable loop |
| `src/tasks/dynamic/clock.inc` | an overlay that allocates no surface and shares its parent's |
| `src/tasks/dynamic/sprdemo.inc` | sprites, the `frameCount` gate, collision |
| `src/tasks/dynamic/gfxdemo.inc` | gfx.lib primitives and the matrix fill |
| `src/tasks/dynamic/spirog.inc` | instance-buffer arguments, maths, full-screen drawing, presets |
| `src/tasks/dynamic/gortris.inc` | a large game: modes, hi scores in the FS, a music thread — see [gortris.md](gortris.md) |
| `src/tasks/dynamic/shell.inc` | a reentrant, argument-taking, long-lived task |

**Where to go next**

| Topic | Document |
|---|---|
| The binary format, flags and the manifest | [writing-relocatable-tasks.md](writing-relocatable-tasks.md) |
| The runtime model: lifecycle, screens, semaphores, sprites | [programmers-guide.md](programmers-guide.md) |
| Every kernel call and its clobbers | [kernel.md](kernel.md) |
| The syscalls | [syscall.md](syscall.md) |
| Libraries: gfx, fp, string, sid, ipc, sprite, filesys, time | [features.md](features.md) §5, then each `lib-*.md` |
| The pool's placement and fragmentation rules | [programmers-guide.md](programmers-guide.md) § *Pool fragmentation* |
| Building, running and debugging | [development.md](development.md) |
| What the system cannot do, and the way around it | [limitations.md](limitations.md) |

---

## 14. Finding out what went wrong

After a while this becomes reflex; until then, work through the four questions in
order. Between them they cover nearly everything, and each one names the tool that
answers it.

### Question 1: is the binary that is running the one I just built?

The task binaries live **inside** `reu/REU.bin`, and VICE writes that image back on
exit — so a rebuild that was not reseeded leaves the previous copy in place, and it
survives restarts.

- `dir` — is the file in the image at all?
- `ps` — is it running, and at which pool address?
- `pwsh tools/check-reu-current.ps1` — are `tasks-out/*.bin` byte-identical **inside**
  the image, and was `tasks-out/` built from the sources you have now? This is the
  answer to "why is my change not there?", and it exists because that question costs
everyone an hour at least once.

Two ways to get here: the wrong F5 flow (**Build & Launch with REU** builds the kernel
**only** — a task change needs *…with fresh REU*), or a reseed that never ran.

### Question 2: is it running at all?

`ps` shows the row (`id pri addr name`, with `(swp)`/`(shr)`/`(pau)`/`(slp)` markers),
and `pool` lists every live owner of a page. If your task is absent the loader refused
it, and the message is on the screen you were on — `? bad task file`, `? no space in
pool`, `? already running` and the rest, with what each one means, are in
[writing-relocatable-tasks.md](writing-relocatable-tasks.md) §12.

The commonest refusal is a label **before** your entry point: the code size field is
`end - entry`, so anything above the entry falls outside it, and the loader rejects the
file rather than loading it with wrong addresses.

### Question 3: it runs, and the screen is wrong

| You see | Because |
|---|---|
| a black screen with the right border colour | a fresh surface's video matrix is zero, so every pixel you plot is colour 0 — `kFillMatrix` first (§8) |
| nothing at all, but the machine answers | your surface is not the displayed one: the shell shows it with `view <id>`, or you take the display with `kSwitchView` (§5) |
| text that flickers, or a phantom cursor | two writers in one surface without `kLockScreen`/`kUnlockScreen` (§4) |
| the colours are right but the glyphs are not | a screen code, not a PETSCII code: the letters are `$01-$1A` (`$41-$5A` shifted), so "printable" is not `>= $20` |

### Question 4: it hangs, or the machine reboots

With no memory protection a bad pointer is a machine-wide fault, and the scheduler's
fallback when the last live task dies is a warm reboot to a fresh shell — so "it
rebooted" usually means "something wrote where it should not".

| Symptom | Cause |
|---|---|
| the prompt never comes back | a `.com` that left with `rts` instead of `SYS_EXIT`: the shell is blocked in its wait until your `taskState` goes to 0 (§4) |
| the shell disappears for good | a task that took the display and never exits — the shell is evictable, and only an *exit* triggers the restore (§5) |
| it stops after a fixed moment | a blocking call you did not expect: `SYS_SLEEP`, `kSidPlay`, `kIpcPost` on a full ring, `kReadString`, `kWaitKey` |
| it corrupts only when run twice | writable state in the code image plus `KF_REENTRANT` — state belongs in the instance buffer (§7) |

### The tools, once the four questions are not enough

| Tool | Use |
|---|---|
| a **failed `.assert`** | the cheapest debugger in the tree: it fails the *build*, not the machine. Assert every address, size and offset you rely on |
| the **gates** | they name most mistakes that would otherwise be silent — [development.md](development.md) §6 |
| VICE's **monitor** | `build/main.sym` is the symbol map, in the line format the monitor loads to name addresses; breakpoints, memory dumps and single-stepping live there |
| **VS64's 6502 debugger** | `.vscode/launch.json` carries the configuration — source-level breakpoints on the built `.prg` |
| `tools/dis6502.py --entry XXXX` | what your *built* binary actually does, with a hardware-touch report; `tools/scan-prg.py` for the bytes the walk cannot reach |
| a **freeze trace** | paint `$D020`, then `sei` and `jmp *`: the machine stops where you doubt it and the colour stays on screen. A bare `$D020` write alone is useless — the scheduler repaints the border every tick — and if your task is re-runnable, guard the trace so it skips the first instance |
| `pwsh tools/audit-clobbers.py` | checks the kernel's "preserves X" claims against the *emitted* code. A clobber list is a contract the assembler cannot see |

**Bisect with the shipped code.** Every layer has a working example: `blink.inc` for
arguments, `format.inc` for the command protocol, `clock.inc` for an overlay that
owns no surface, `sprdemo.inc` for sprites and the frame gate. When your version
misbehaves, delete half of it until the behaviour changes — or start from the shipped
file and add your code to it, which is usually quicker the other way round.

---

## Appendix A. Reference solution

The exercises in §3 and §4 ask for one program, and this is it, complete: `count <text>`
echoes `<text>` and its length, echoes from the second word on when there is one, and
prints a usage line when there is no argument.

**It was built as written.** These two files and the manifest line were registered in
`tools/tasks.json` and assembled by the real pipeline — `count: 142 bytes of code, 7
fixups`, relocation verification OK, header check OK, one pool page — and the
registration was then removed. This is an answer key, not a shipped command.

### `src/tasks/cmd/count.asm` — the wrapper

```asm
// ==========================================
//  count.asm -- "count" command task (relocatable)
// ==========================================
//  Counts and echoes an argument: "count <text>" prints <text>, then its length in
//  decimal, then two newlines so the shell's prompt starts on a fresh line. With a
//  second word it prints from that word on. With no argument at all it prints a
//  usage line.
//  This is the tutorial's reference command (docs/tutorial.md, Appendix A).
//  Scratch: a 4-byte decimal buffer in the instance buffer -- three digits and the
//  terminator kPrintString needs.

.encoding "screencode_mixed"

// (syscall alias + dataPtr/kPtr/kArg + kernel-data aliases are defined
//  in tools/assemble-tasks.asm)

countBinStart:
    .word HDR_MAGIC              // +0:  magic 'G','O' (LE)
    .byte KF_RELOCATABLE        // +2:  flags
    .word $5000                  // +3:  origin (page-aligned, nominal)
    .word countEnd - count       // +5:  code size
    .byte 4, 0, 0                // +7:  data size (4B decimal buffer), ZP base/len
    .word (1 << LIB_STRING)      // +10: libMask -- kStrlen is a string.lib call
    .byte countNameEnd - countName  // +12: name len
countName:
    .text "count"
countNameEnd:
    .word 0                      // fixup_count (16-bit -- written by the build)
    .word 0                      // fixup_offset (written by the build)
    .fill 256 - (* - countBinStart), 0

.import source "count.inc"
.label countEnd = *
```

### `src/tasks/cmd/count.inc` — the body

```asm
// ==========================================
//  count.inc -- "count": echo an argument and its length
// ==========================================
//  The tutorial's reference command (docs/tutorial.md, Appendix A).
//  `count <text>` echoes <text>, then " length " and its length in decimal, then two
//  newlines; from the second word on when there is one, and a usage line when there
//  is no argument.
//  Two habits it shows: kStrlen is a string.lib call (the wrapper's libMask declares
//  it) while kByteToDec is resident, and kByteToDec does NOT terminate its digits --
//  the printer needs a 0 written after them.

.const COUNT_BUF = 0             // 4: the decimal buffer the digit writer fills

count:                           // ENTRY -- the first label in the body
    //  --- no argument: the usage line ---
    lda cmdArgsBuf
    bne countEcho
    lda #<countUseStr
    ldx #>countUseStr
    jsr countSay
    jmp countOut
countEcho:
    //  --- from the second word on (or the whole argument), then its length ---
    jsr countPick                // kPtr = what to echo
    jsr kPrintString
    lda #<countLenStr
    ldx #>countLenStr
    jsr countSay                 // " length "
    jsr countPick                // kPrintString moved kPtr: point it again
    jsr kStrlen                  // string.lib: A = the length (0-255)
    pha                          // park it across the pointer arithmetic
    lda dataPtr
    clc
    adc #COUNT_BUF
    sta kPtr
    lda dataPtr+1
    adc #0
    sta kPtr+1
    pla                          // A = the length again
    jsr kByteToDec               // digits at (kPtr), Y = how many (1-3)
    lda #0
    sta (kPtr),y                 // ...and the terminator the printer needs
    jsr kPrintString
countOut:
    //  --- two newlines: the shell's prompt starts on a fresh line only if the
    //      cursor is at the left of one ---
    jsr kNewline
    jsr kNewline
    lda #SYS_EXIT
    jsr syscall                  // a command that returns with rts hangs the prompt

// --- countSay -- print the string in A/X (lo/hi) ---
//  Entered by `jsr` and ended by `jmp`: kPrintString's `rts` returns to countSay's
//  caller, so this is a call, not a jump into the printer.
countSay:
    sta kPtr
    stx kPtr+1
    jmp kPrintString

// --- countPick -- kPtr = the argument from its second word on ---
//  Skip the first word, then the run of spaces after it. A single word (or none)
//  leaves kPtr at the start of the argument, so one word echoes whole.
countPick:
    lda #<cmdArgsBuf
    sta kPtr
    lda #>cmdArgsBuf
    sta kPtr+1
    ldy #0
countPkW1:
    lda (kPtr),y
    beq countPkRts               // end of line: there is no second word
    cmp #$20
    beq countPkSkip
    iny
    bne countPkW1
countPkSkip:
    lda (kPtr),y                 // ...and the spaces that follow the word
    cmp #$20
    bne countPkFold
    iny
    bne countPkSkip
countPkFold:
    tya                          // fold the walk's offset into the pointer, so the
    clc                          //   printer and kStrlen both start at the word
    adc kPtr
    sta kPtr
    bcc countPkRts
    inc kPtr+1
countPkRts:
    rts

countUseStr:  .text "? count <text>"
              .byte 0
countLenStr:  .text " length "
              .byte 0
```

### The manifest line, added to `tools/tasks.json`

```json
{ "name": "count", "source": "src/tasks/cmd/count.asm", "origin": "$5000",
  "fsName": "count.com", "kind": "com" }
```

Then the **Build dynamic tasks + REU** task, and `count hello` at the prompt.

### What you should see

| You type | The screen shows | Why |
|---|---|---|
| `count hello` | `hello length 5` | one word: `countPick` finds no space and leaves `kPtr` at the start |
| `count one two` | `two length 3` | `countPick` steps over the first word and the spaces after it |
| `count one two three` | `two three length 9` | it prints from the second word **on**, so a third word comes with it |
| `count` | `? count <text>` | the first byte of `cmdArgsBuf` is 0, so the usage path runs |

Every path then prints a blank line with the prompt on the next one.

### Three things worth stealing

- **`countSay` is entered by `jsr` and ends in `jmp`**, so `kPrintString`'s `rts`
  returns to `countSay`'s caller. That is the only shape a tail call may take — a label
  reached by a `jmp` that itself ends in `rts` pops the wrong frame (the §13 trap table
  has that symptom, and it looks like your task re-running its init on every key).
- **The digits need a terminator.** `kByteToDec` writes one to three digits and does
  *not* write a 0 after them, so `sta (kPtr),y` with the count it returns in `Y` is not
  optional: without it the printer runs on into whatever is next in the buffer.
- **`countPick` folds its walk's `Y` into `kPtr`** rather than recomputing the address,
  which is how the rest of the tree walks a buffer at a computed offset.
