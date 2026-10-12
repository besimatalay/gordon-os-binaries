# GordonOS — Kernel API Reference

> Complete reference for all kernel utility library calls. Jump table at `$E000`.

> ⚠️ **Dynamic kernel libraries:** some cold calls are **lib-backed** — the
> jump-table entry is an eager `jmp libTrap` or a lazy cold stub that loads a
> shared `.lib` binary (`time.lib`, `filesys.lib`, `gfx.lib`, `fp.lib`,
> `string.lib`, `sid.lib`, `ipc.lib`, `sprite.lib`, `mouse.lib`) and is
> patched in place to the lib routine's real address. The behavior is
> identical; only the implementation location differs. A load that **fails**
> does not return into the command: after reporting `? could not load
> <name>.lib` the calling task ends -- except the system shell, which stays
> alive, abandons the command it was running and comes back to its prompt. See
> [dynamic-libraries.md](dynamic-libraries.md). Per-library call references:
> [lib-time.md](lib-time.md), [lib-filesys.md](lib-filesys.md),
> [lib-gfx.md](lib-gfx.md), [lib-fp.md](lib-fp.md),
> [lib-string.md](lib-string.md), [lib-sid.md](lib-sid.md),
> [lib-ipc.md](lib-ipc.md), [lib-sprite.md](lib-sprite.md), [lib-mouse.md](lib-mouse.md).

All calls are invoked via `JSR` to the fixed jump table address. The kernel owns ZP `$F0-$FF` — `$F0` is `blinkRate` (cursor blink interval, set at runtime via `blink.com` and re-derived for the machine by `speed.com`) and `$F1-$FF` is scheduler/IRQ scratch; save any registers you need across calls (see **Clobbers** column). `$F1-$F2` (`dataPtr`) is a task-private data pointer saved/restored per-task by the scheduler — re-entrant tasks use it for per-instance state via `(dataPtr),y`. Per-surface state (cursor position, enable, saved glyph) lives in the surface slot's matrix tail at `slot+$23E8` (mirrored in the framebuffer matrix tail `$07E8+` while displayed). See [`memory-map.md`](memory-map.md) for the layout.

> **How a task refers to these:** the task pipeline imports `kernel/jumptable.inc`
> (the `k*` names below) once for every task, so task code just writes
> `jsr kPrintChar` — with **no** `.import` in the task source, since symbols are
> global across the assembly and re-importing them is a duplicate-symbol error.
> Inside the kernel these same names are real labels in `kernel.asm`. For the
> complete picture — kernel calls, syscall numbers, kernel data, pool geometry
> and library constants — see
> [writing-relocatable-tasks.md](writing-relocatable-tasks.md) §2.2.

---

## Screen I/O

### `kClearScreen` — `$E000`

Fill screen with spaces. Cursor moves to home `(0,0)`.

The matrix fill stops short of the framebuffer cursor tail (`$07E8`-`$07F7`),
and the tail's saved cursor position is reset to home — so the cursor keeps
blinking at `(0,0)` afterwards even if the clearing task exits before the
next scheduler cursor save (the tail is the only cursor state a shared
screen's owner restores from).

| | |
|---|---|
| **Input** | — |
| **Output** | — |
| **Clobbers** | A, X, Y, kPtr, kArg |
| **Modifies** | kPtr |

```asm
    jsr kClearScreen        ; blank screen, cursor at (0,0)
```

---

### `kPrintChar` — `$E003`

Print a single screen-code character at the current cursor position, then advance the cursor. Auto-scrolls the current surface's scroll region if the cursor wraps past the region bottom (default row 24).

> ⚠️ **The scroll happens AT THE WRAP, and only when the row EXCEEDS the bottom.**
> `wrapClamp` (`src/kernel/scroll-region.inc`) tests `cursorRow > taskScrollBottom`:
> a wrap that lands exactly on the bottom row clamps the cursor and does nothing,
> while a wrap past it scrolls the whole region one row — *while the character is
> being written*. So **do not print into the last cell of the last row of a region**
> (column 39 of row 24 by default): the surface scrolls as you draw it and the top
> row is lost, with no way to reposition afterwards. Draw full-width rows one row
> higher, or stop one cell short. `printChar`, `printGlyph` and `newline` all share
> this path.

| | |
|---|---|
| **Input** | A = screen code (e.g., `#$01` = 'A', `#$20` = space) |
| **Output** | — |
| **Clobbers** | A, X, Y |
| **Modifies** | `kPtr` |

```asm
    lda #$01                ; screen code for 'A'
    jsr kPrintChar          ; prints 'A', advances cursor (X clobbered)
```

---

### `kPrintString` — `$E006`

Print a null-terminated screen-code string starting at `(kPtr)`. The cursor advances through each character. `kPtr` is advanced past the null terminator on return.

| | |
|---|---|
| **Input** | `kPtr` = pointer to null-terminated screen-code string |
| **Output** | — |
| **Clobbers** | A, X, Y |
| **Modifies** | `kPtr` (advanced past terminator) |

```asm
    lda #<myString
    sta kPtr
    lda #>myString
    sta kPtr+1
    jsr kPrintString        ; prints string (X clobbered)

.encoding "screencode_mixed"
myString:
    .text "hello world"
    .byte 0
```

---

### `kSetCursor` — `$E009`

Set the kernel cursor position. This is the only screen routine that preserves all registers.

| | |
|---|---|
| **Input** | X = column (0–39), Y = row (0–24) |
| **Output** | — |
| **Clobbers** | — |
| **Modifies** | — |

```asm
    ldx #10
    ldy #5
    jsr kSetCursor          ; cursor at column 10, row 5
```

---

### `kGetCursor` — `$E03F`

Read the current kernel cursor position. Note: X and Y are outputs (the caller's X/Y values are lost).

| | |
|---|---|
| **Input** | — |
| **Output** | X = column, Y = row |
| **Clobbers** | X, Y (output) |
| **Modifies** | — |

```asm
    jsr kGetCursor          ; X = col, Y = row
    stx savedCol            ; save for later restore
    sty savedRow
```

---

### `kGetCursorOn` — `$E099`

Read the current cursor-enable state. Unlike `kGetCursor`, this preserves X and Y.

| | |
|---|---|
| **Input** | — |
| **Output** | A = `cursorOn` (0 = off, non-zero = on) |
| **Clobbers** | A only |
| **Modifies** | — |

```asm
    jsr kGetCursorOn        ; A = cursorOn, X/Y preserved
    tax                     ; snapshot for later restore
```

---

### `kCursorAddr` — `$E042`

Compute the screen RAM address at the current cursor position. Stores result in `kPtr`. Does not move the cursor. Added for EhBASIC integration (cursor block erasure).

| | |
|---|---|
| **Input** | — |
| **Output** | `kPtr` = screen RAM address at `(cursorCol, cursorRow)` |
| **Clobbers** | A, kPtr |
| **Modifies** | kPtr |

```asm
    jsr kCursorAddr         ; kPtr = screen address at cursor
    ldy #0
    lda #$20                ; space
    sta (kPtr),y            ; erase character at cursor
```

---

### `kNewline` — `$E00C`

Move cursor to column 0 on the next row. If already on the scroll-region bottom row (default 24), scrolls the region up.

| | |
|---|---|
| **Input** | — |
| **Output** | — |
| **Clobbers** | A, X, Y |
| **Modifies** | `kPtr`, `srcPtr` |

```asm
    jsr kNewline            ; carriage return + line feed
```

---

### `kScrollScreen` — `$E00F`

Scroll the current surface's **scroll region** up by one row (default the whole screen, rows 0–24): row T+1→T, …, row B→B-1, then blanks row B. The region is per-surface, set with `kSetScrollRegion`.

| | |
|---|---|
| **Input** | — |
| **Output** | — |
| **Clobbers** | A, X, Y |
| **Modifies** | `kPtr`, `srcPtr` |

```asm
    jsr kScrollScreen       ; scroll the surface's region up one line
```

> **All-bitmap model:** scrolls via the REU bounce (pixels + matrix).
> Works for the displayed surface (framebuffer region) **and** for
> background surfaces (their REU slot, per-row via `scrollScreenSlot`),
> so a background task scrolling its own slot can never corrupt the
> displayed surface. A single-row region (`top == bottom`) just blanks
> that row. See `kSetScrollRegion`.

---

### `kEnableCursor` — `$E012`

Enable the blinking block cursor. The IRQ handler toggles visibility every `BLINK_RATE` ticks. Sets `cursorOn` for the running task; the scheduler persists it to the surface matrix tail, so state survives context switches and view changes. The blink code reads cursor state from the DISPLAYED surface's tail — correct on all surfaces.

> **All-bitmap model:** `cursorOn` is per-task (like the
> cursor position): the scheduler syncs it with the slot tail (`+$23EA`,
> background) or the framebuffer tail `$07EA` (focused), and `kbDoBlink`
> reads `$07EA` — the DISPLAYED surface's enable (≤1 tick stale).
> `kbDoBlink` uses **save/restore**: ON saves the cell's 8 glyph bytes
> + matrix nibble into the framebuffer matrix tail (`$07F0-$07F7`,
> `$07EB` — travels with the surface via surfSave/surfLoad), XORs the
> cell and writes `(taskCursorColor<<4) | (old&$0F)`; OFF restores the
> saved bytes at the saved cell. Moving the cursor between phases can
> therefore never strand phantom blocks or recolor characters. `kPrintChar`
> erases a live XOR block before moving the cursor (the blink is frozen
> while `cursorOn=0` during output). No cursor is drawn when
> `kbFocus = $FF`. Per-task cursor position lives in the slot's matrix
> tail (background) or `$07E8`/`$07E9` (focused), synced by the
> scheduler.

| | |
|---|---|
| **Input** | — |
| **Output** | — |
| **Clobbers** | A, Y |
| **Modifies** | `kPtr`, `cursorOn`, surface matrix tail |

```asm
    jsr kEnableCursor       ; cursor blinks at current position
```

> **As a text-field cursor — the usual reason a task calls this.** The blink
> follows the **live** cursor of whichever task owns the display, so a task that
> reads keys itself (`kReadKey` + `SYS_YIELD`; see the `kReadString` warning in the
> programmer's guide) gets a blinking cursor for free: `kSetCursor` to the field,
> `kEnableCursor`, and every `kPrintChar` echo leaves the block one cell along.
> `kPrintChar` saves and clears `cursorOn` while it prints, so the block can never
> be baked into a character. On the way out **disable BEFORE erasing** —
> `kDisableCursor` then `kBlinkReset`: with `cursorOn` still set, an IRQ tick could
> redraw the block in the window between the two calls. `gortris`'s hi-score name
> editor (`gtHiNameScreen`) is the worked example.

---

### `kDisableCursor` — `$E015`

Disable the blinking block cursor. Screen output routines disable it internally — call this to keep it off. Sets `cursorOn` for the running task; the scheduler persists it to the surface matrix tail.

| | |
|---|---|
| **Input** | — |
| **Output** | — |
| **Clobbers** | A, Y |
| **Modifies** | `kPtr`, `cursorOn`, surface matrix tail |

```asm
    jsr kDisableCursor      ; cursor hidden
```

---

### `kBlinkReset` — `$E0C0`

Erase a live blink block at its **saved** position and force the next blink to be
an ON draw at the current cursor. A no-op when no block is currently drawn.
Called after moving the cursor so the block follows it instead of leaving a
restored cell behind — and it is the call that guarantees no block is left drawn
on a surface that is about to be copied or handed over: the framebuffer copy is
verbatim, so a live block would be baked into the outgoing surface.

The kernel's own switch path already does this for the running task
(`gfxSurfPrep`, called from `doGfxSwitch` immediately before `surfSave`), so a
task does not have to protect an F-key switch itself.

| | |
|---|---|
| **Input** | — |
| **Output** | — |
| **Clobbers** | A, X, Y, `kPtr`, `kArg+7` |
| **Modifies** | framebuffer-tail saved glyph bytes, `cursorVisible`, `blinkTick` |

```asm
    jsr kDisableCursor      ; blink off FIRST — nothing can redraw it now
    jsr kBlinkReset         ; then un-draw the block at its saved position
```

---

## Keyboard

> **Note:** F1/F3/F5/F7 and Shift+F1/F3/F5/F7 are intercepted by the IRQ handler (`kbPoll`) for surface switching (28 REU slots, all-bitmap model) and are **never** placed in the keyboard buffer. The scan only records which screen was asked for (`kbScreenReq`); the scheduler's switch path applies it on the same tick, so the switch can never write a running task's `kArg` — see `kSwitchView`.
>
> **Repeat timing** (`KEYB_INITIAL` delay before repeat, `KEYB_REPEAT` interval) is runtime-settable via the `keyrpt` command (`keyrpt <delay> <repeat>`) — it patches the two `lda #` immediates in `kbPoll` (self-modifying; the kernel runs from RAM). Both are **real-time values** (~500 ms and ~100 ms at 100%), so the `speed` command re-derives all three timings (`BLINK_RATE` too) from the machine's speed — see the *VICE speed* section of `quick-start.md`.

### `kScanKeyboard` — `$E01E`

Pop one key from the IRQ-filled ring buffer. Non-blocking.

| | |
|---|---|
| **Input** | — |
| **Output** | A = screen code, or `$FF` if buffer empty |
| **Clobbers** | A, X, Y |
| **Modifies** | — |

```asm
    jsr kScanKeyboard
    cmp #$ff
    beq noKey               ; buffer empty
    ; A contains screen code of pressed key
```

---

### `kReadKey` — `$E018`

Pop one key from the buffer. Returns 0 for empty buffer or key release events. Use `kScanKeyboard` if you need to distinguish "no key" from '@' (screen code `$00`).

| | |
|---|---|
| **Input** | — |
| **Output** | A = screen code, or `0` if empty/release |
| **Clobbers** | A, X, Y |
| **Modifies** | — |

```asm
    jsr kReadKey
    beq noKey               ; nothing pressed
    jsr kPrintChar          ; echo the key
```

---

### `kWaitKey` — `$E01B`

Block until a key is pressed. Spins reading `kScanKeyboard` until a non-`$FF` value returns.

| | |
|---|---|
| **Input** | — |
| **Output** | A = screen code of pressed key |
| **Clobbers** | A, X, Y |
| **Modifies** | — |

```asm
    jsr kWaitKey            ; waits forever until keypress
    cmp #$81                ; RETURN key?
    beq handleReturn
```

---

### `kReadString` — `$E060`

Read a line of keyboard input into a caller-provided buffer. Characters are echoed to the screen as they are typed. Supports **cursor keys** (← → HOME for navigation, mid-line editing), **backspace** (DEL key, including mid-line delete with redraw), and a **blinking white reverse-video cursor**. Once the buffer reaches max length, further characters are silently ignored — the routine continues waiting for RETURN. The buffer is always null-terminated.

| | |
|---|---|
| **Input** | `kPtr` = buffer address, X = max length (1–255) |
| **Output** | Y = actual length (0 to maxLen), buffer null-terminated |
| **Clobbers** | A, X, Y |
| **Modifies** | `kPtr` (advanced past terminator), `kArg` (clobbered by internal `kPrintChar`) |

```asm
    lda #<myBuffer
    sta kPtr
    lda #>myBuffer
    sta kPtr+1
    ldx #20                 ; max 20 characters
    jsr kReadString         ; Y = length typed
    ; myBuffer is now null-terminated
    ; kPtr points past the terminator
```

> **Note:** The caller must provide a buffer with at least `maxLen + 1` bytes (for the null terminator). The routine blocks the caller until RETURN is pressed — it returns only when a complete line is available.

> **Keyboard focus:** This routine only reads input when the calling task owns keyboard focus (i.e., the user is viewing its screen via F-keys or `kSwitchView`). If the caller does not own focus, `kReadString` returns immediately with `Y = 0` and an empty buffer. Callers that loop on `kReadString` should handle this gracefully.

---

## String Utilities

> **Lazy `string.lib` (lib 4):** `kStrlen`, `kStrcpy`, `kStrcmp`,
> `kSkipSpaces`, `kByteToHex`, `kHexDigit`, `kNibbleToHex` — each jump-table
> entry is a lazy stub that cold-loads `string.lib` on first use, then `jmp`s
> through the resolved vector. `kByteToDec` stays resident (the kernel uses it
> for `"parent.N"` thread names). See
> [lib-string.md](lib-string.md).

---

## IPC (`ipc.lib`)

> **Lazy `ipc.lib` (lib 6):** `kIpcPost` (`$FF84`) and `kIpcPick` (`$FF87`) are
> **lazy `ipc.lib`** calls, living in the same `$FF7E` block as
> `sid.lib`'s — neither is in the `$E000` table, which is full. The library is
> **four** independent one-producer / one-consumer byte channels, each with its
> own 128-byte ring in the library's **own data** (`X` selects the channel):
> the kernel pays nothing for IPC at all, because there is no syscall, no kernel
> buffer and no resident code beyond the two 3-byte stubs, and the rings sit in
> the pool with the library (it is 638 bytes / 18 fixups, so **3 pool pages**).
>
> ⚠️ **One producer and one consumer *per channel*, by contract.** `kIpcPost` is
> the only writer of that channel's `ipcHead` and `kIpcPick` the only writer of
> its `ipcTail`; that single-writer property is the whole reason a channel needs
> no lock, and a second producer on the *same* channel would corrupt its ring
> (the two indices could not then be kept consistent). A second task pair simply
> takes another channel. `kIpcPost` takes the byte in `A` and **blocks by
> yielding** (`SYS_SLEEP`, one tick) while that channel's ring is full, so a slow
> consumer applies backpressure instead of the producer dropping data or
> spinning; `kIpcPick` is deliberately non-blocking and returns `C=1` when that
> channel is empty. An `X` of 4 or more is refused with `C=1` rather than being
> allowed to write into a neighbouring ring — the same rule the sprite API uses.
> Neither call needs any caller ZP. `kPtr`/`kPtr+1` *is* clobbered (it holds the
> channel's ring pointer for the duration), which is safe precisely because
> `switchTask` saves and restores it per task; a patched absolute store operand
> would not have been. See [lib-ipc.md](lib-ipc.md).

## Keeping one library, releasing the rest — `kLibHold`

> **`kLibHold` (`$FFE6`)** is *not* a library call but the library
> system's one task-facing operation: it releases every library the calling task
> declared **except those in the mask in A**, so those pages go back to the pool now rather
> than at task exit.
>
> ```
> Input:  A = MASK of lib ids to KEEP -- bit n keeps library n (0 releases all)
> Output: C = 0 always (there is no failure path: every 8-bit value is a mask)
> ```
>
> A `libMask` is a lifetime declaration, so a task that needs a big library for a
> moment — `sidplay` reads its tune with `filesys.lib` and then plays for minutes
> out of `sid.lib` — otherwise holds ~11 idle pages for the whole song, and on a
> loaded system that is enough to make the loader evict and restore other tasks
> around it (audible gaps in the music).
>
> It works by clearing the kept bits in the task's stored 16-bit declaration
> mask (`dynTaskLibMaskLo/Hi`), running the loader's own release path,
> `dlLibRelease` (which reads that stored mask), and then storing the keep mask
> alone as the mask — no second refcount implementation. A library another task
> also declares is safe: its refcount does not reach zero.
>
> ⚠️ **That order is the whole routine.** Storing the kept bit as the mask *first*
> makes the release walk "keep sid" — releasing sid itself, freeing the library it
> was told to keep while never releasing filesys.
>
> ⚠️ **Keep what you still call.** A released library stops serving the task
> that gave it back: a task that drives sprites every frame must keep the sprite
> library in the mask, or nothing it writes takes effect.
>
> ⚠️ **One-way.** Do not use a released library again: the code still works (the
> entry is restored to its cold stub, so the next call reloads it), but refcounts
> are taken once at spawn from the binary's `libMask`, so the reload is owned by
> nobody — and a refcount-0 library can never be freed again by the release path,
> leaking its pages until a reboot (a *warm* reboot reclaims them — see
> *A warm reboot reclaims the libraries* below). See [dynamic-libraries.md](dynamic-libraries.md)
> § *Giving a library back early*.
>
> The routine lives in the `$1D16-$1D3F` pocket (42B, below the data heap — filled
> exactly) because the kernel's code band has no slack; the 3-byte stub is at the
> far end of the `$FF7E` block. Both ends are pinned by asserts in `main.asm`.

---

## A warm reboot reclaims the libraries — `warmBootReset`

> **`warmBootReset` (`$181D`, 28B)** is the warm-reboot entry point: the
> scheduler's "no alive tasks" path `jmp`s here, and the routine releases
> **every** library before falling through to `start`.
>
> `start:` re-initialises the pool bitmap, the dyn tables, the residency records
> and the surfaces — but kernel data otherwise survives `jmp start`, and the
> library tables are kernel data. Leaving them alone breaks two things: a library
> the reboot should have swept up (e.g. one stranded at refcount 0 by a cold-stub
> reload) stays loaded *and* listed in `pool`; and, worse, the patched
> `libJumpLo/Hi` call entries still pointed into pool pages the fresh bitmap calls
> free, so the next task loaded there would be entered through a library entry —
> into the wrong code, with no cold stub left to trap it.
>
> It does not reimplement "unload": it calls the loader's own `libFree` (pages
> back, entries re-pointed at their cold stubs, `libStartPage = $FF`) for **every**
> id and clears the refcount. The walk is count-agnostic on purpose — the case it
> must repair is a *loaded* library with refcount 0 — and it is safe because
> `libFree` returns immediately for a library that was never loaded. It runs with
> IRQs off (the scheduler is an IRQ context, which is what `libFree` wants) and
> no task can be scheduled mid-walk.
>
> It lives at `$181D-$1838`, between `spawnCore`'s relocated half and
> `sprite.lib`'s name string at `$1839` — **not** in the kernel core's growth headroom, which is
> reserved for core growth (`$13C5-$13D3`). Reached by one re-pointed `jmp`,
> so it is free to live anywhere and this pocket costs the core band nothing.
> Bounded by asserts in `main.asm` and by `tools/verify-map.ps1`.

---

## Music (`sid.lib`)

> **Lazy `sid.lib` (lib 5):** `kSidPlay` (`$FF7E`) and `kSidHush` (`$FF81`) are
> two of the entries that are **not** in the `$E000` table (it is full; `ipc.lib`'s
> two share the block, and `sprite.lib`'s five sit in the `$CDDE` pocket): their 3-byte stubs sit in the free block at
> `$FF7E`, and `libNameSid` lives there too, because `lib.inc`'s string block
> ends at `$FF7D`. The player body is COMPUTE!'s Enhanced Sidplayer.
>
> ⚠️ **A caller must declare ZP `$02-$0A`** (base 2, length 9): the player's
> scratch is remapped into that range and a library cannot declare ZP, so the
> task header is the only place the contract can be expressed. `kSidPlay` takes
> the tune image in `kPtr` (including its 2-byte load address), the ticks-per-
> jiffy delay in `kArg` and the repeat count in `kArg+1` (`0` = forever), blocks
> by yielding each jiffy, and returns with `C=1` if another task already owns the
> chip. See [lib-sid.md](lib-sid.md).

### `kStrlen` — `$E021`

Count characters in a null-terminated string.

| | |
|---|---|
| **Input** | `kPtr` = pointer to null-terminated string |
| **Output** | A = length (0–255) |
| **Clobbers** | A, Y |
| **Modifies** | — |

```asm
    lda #<myString
    sta kPtr
    lda #>myString
    sta kPtr+1
    jsr kStrlen             ; A = string length
```

---

### `kStrcpy` — `$E024`

Copy a null-terminated string from `(kPtr)` to `(srcPtr)`. Stops after copying the null terminator.

| | |
|---|---|
| **Input** | `kPtr` = source, `srcPtr` = destination |
| **Output** | — |
| **Clobbers** | A, Y |
| **Modifies** | — (pointers NOT advanced) |

```asm
    lda #<srcString
    sta kPtr
    lda #>srcString
    sta kPtr+1
    lda #<destBuf
    sta srcPtr
    lda #>destBuf
    sta srcPtr+1
    jsr kStrcpy             ; destBuf now contains copy of srcString
```

---

### `kStrcmp` — `$E107`

Dual-mode: `kArg` selects exact compare (0) or wildcard match (1). **`kArg`
must be set before every call** — a stale non-zero value silently switches an
intended exact compare into a wildcard match.

Exact (`kArg=0`): compare the null-terminated strings at `(kPtr)` and
`(srcPtr)`. `Z=1` when equal, `Z=0` when they differ.

Wildcard (`kArg=1`): `kPtr` = name, `srcPtr` = pattern. `*` matches any run
(including empty), `?` matches any single character. `Z=1` match, `Z=0` no
match.

| | |
|---|---|
| **Input** | `kPtr`, `srcPtr` = strings to compare, `kArg` = mode (0=exact, 1=wildcard) |
| **Output** | Z=1 equal/match; Z=0 differ/no match |
| **Clobbers** | Exact: A, Y. Wildcard: A, Y, `kPtr`, `srcPtr`, `kArg+2`..`kArg+7` |
| **Modifies** | — (exact); `kPtr`, `srcPtr` (wildcard) |
| **Preserves** | X (both modes) |

```asm
    lda #<strA; sta kPtr; lda #>strA; sta kPtr+1
    lda #<strB; sta srcPtr; lda #>strB; sta srcPtr+1
    lda #0; sta kArg        ; exact mode
    jsr kStrcmp             ; Z=1 if equal
    beq equal
```

---

### `kSkipSpaces` — `$E075`

| | |
|---|---|
| **Input** | `kPtr` = string pointer |
| **Output** | `kPtr` advanced past leading spaces; A = first non-space char (0 if end); C=0 = found, C=1 = end of string |
| **Clobbers** | A, Y |
| **Modifies** | `kPtr` |

```asm
    lda #<str; sta kPtr
    lda #>str; sta kPtr+1
    jsr kSkipSpaces         ; skip leading spaces
    bcs endOfString         ; C=1 → hit null
    ; A = first non-space char, kPtr points to it
```

---

### `kByteToHex` — `$E027`

Convert a byte to 2 hex digit characters written at `(kPtr)`. The pointer is NOT advanced — digits go at `(kPtr),0` and `(kPtr),1`.

| | |
|---|---|
| **Input** | A = byte value, `kPtr` = destination (2 bytes needed) |
| **Output** | — |
| **Clobbers** | A, X, Y |
| **Modifies** | — |

```asm
    lda #$ab
    lda #<hexBuf
    sta kPtr
    lda #>hexBuf
    sta kPtr+1
    jsr kByteToHex          ; hexBuf now contains "ab"
```

---

### `kByteToDec` — `$E02A`

> ⚠️ **It converts, it does not print.** The digits are written to `(kPtr)` as a
> decimal string — left-aligned, **not** null-terminated — and the digit count
> comes back in `Y`. Printing takes a second step: write a 0 after the digits (or
> pre-zero the buffer) and hand `(kPtr)` to `kPrintString`. Calling it and
> expecting output on screen prints nothing at all.

Convert a byte (0–255) to 1–3 decimal digit characters written at `(kPtr)`. **Does not null-terminate.** Returns digit count in Y.

| | |
|---|---|
| **Input** | A = byte value (0–255), `kPtr` = destination (3 bytes needed) |
| **Output** | Y = number of digits written (1–3) |
| **Clobbers** | A, X, Y |
| **Modifies** | — |

```asm
    lda #200
    lda #<decBuf
    sta kPtr
    lda #>decBuf
    sta kPtr+1
    jsr kByteToDec          ; Y = 3, decBuf contains "200"
    tya
    tay
    lda #0
    sta (kPtr),y            ; null-terminate it yourself
```

---

### `kHexDigit` — `$E078`

Convert a screen-code hex digit to its nibble value (0–15). Recognizes '0'–'9' ($30–$39) and 'a'–'f' ($01–$06).

| | |
|---|---|
| **Input** | A = screen code |
| **Output** | C=0 success, A = nibble value (0–15); C=1 failure, A = 0 |
| **Clobbers** | A |
| **Modifies** | — |

```asm
    lda #$35                ; screen code for '5'
    jsr kHexDigit           ; C=0, A = 5
    lda #$01                ; screen code for 'a'
    jsr kHexDigit           ; C=0, A = 10
    lda #'g'                ; not a hex digit
    jsr kHexDigit           ; C=1, A = 0
```

---

### `kNibbleToHex` — `$E07B`

Convert a nibble (0–15) to its screen-code hex character. The upper nibble of A is ignored.

| | |
|---|---|
| **Input** | A = nibble value (0–15) |
| **Output** | A = screen code ('0'–'9' = $30–$39, 'a'–'f' = $01–$06) |
| **Clobbers** | A |
| **Modifies** | — |

```asm
    lda #10
    jsr kNibbleToHex        ; A = $01 ('a')
    lda #15
    jsr kNibbleToHex        ; A = $06 ('f')
```

---

## Math

### `kMul16` — `$E02D`

16-bit × 16-bit unsigned multiply. Result is 32-bit.

| | |
|---|---|
| **Input** | `kArg[0..1]` = multiplicand (lo, hi), `kArg[2..3]` = multiplier (lo, hi) |
| **Output** | `kResult[0..3]` = 32-bit product (lo..hi) |
| **Clobbers** | A, X |
| **Modifies** | `kArg`, `kResult` |

```asm
    lda #$e8
    sta kArg                ; multiplicand lo = 232
    lda #$03
    sta kArg+1              ; multiplicand hi = 3   → 1000
    lda #$64
    sta kArg+2              ; multiplier lo = 100
    lda #$00
    sta kArg+3              ; multiplier hi = 0
    jsr kMul16              ; kResult = 100,000 ($000186A0)
```

---

### `kDiv16` — `$E030`

16-bit ÷ 16-bit unsigned divide. Quotient and remainder are both 16-bit.

| | |
|---|---|
| **Input** | `kArg[0..1]` = dividend (lo, hi), `kArg[2..3]` = divisor (lo, hi) |
| **Output** | `kResult[0..1]` = quotient, `kResult[2..3]` = remainder |
| **Clobbers** | A, X, Y |
| **Modifies** | `kArg`, `kResult` |

```asm
    lda #$e8
    sta kArg                ; dividend lo
    lda #$03
    sta kArg+1              ; dividend hi  → 1000
    lda #$07
    sta kArg+2              ; divisor lo
    lda #$00
    sta kArg+3              ; divisor hi   → 7
    jsr kDiv16              ; quotient = 142, remainder = 6
```

---

### `kRandom` — `$E033`

Generate a pseudo-random byte using a Galois LFSR. State is in `randomSeed`.

| | |
|---|---|
| **Input** | — |
| **Output** | A = random byte (0–255) |
| **Clobbers** | A |
| **Modifies** | — |

```asm
    jsr kRandom
    sta $d020               ; random border color
```

---

## Floating Point (`fp.lib`)

> ⚠️ **Eager lib call** — `fpExec` lives in `fp.lib` (lib 3), loaded
> eagerly at spawn (tasks declare `libMask` bit 3) and reached via
> `jmp kFpCall` (`kFpCall = $E113`, a jump-table entry patched to
> `jmp fpExec`). The implementation is
> `src/libs/fp.asm`. See [dynamic-libraries.md](dynamic-libraries.md)
> for the mechanism and **[lib-fp.md](lib-fp.md)** for the full 26-opcode
> table (inputs, outputs, clobbers, error codes) and the ZP-window contract.

### `fpExec` — `jmp kFpCall`, call index 25

Single-entry floating-point dispatcher, reached through the fixed
`kFpCall` jump entry (patched when `fp.lib` loads).

| | |
|---|---|
| **Input** | A = opcode (see the lib table in dynamic-libraries.md); operands in `fac1`/`fac2` ($AC-$B7, per-task ZP preserved by the scheduler) |
| **Output** | C=0: result in `fac1` (FCMP returns A=$01/$FF/$00). C=1: A = error code (0 ÷0, 1 overflow, 2 range, 3 conversion, 4 unimplemented) |
| **Clobbers** | A, X, Y, and the ZP window `$90-$C5` (caller's own state there must be saved — BASIC's wrappers save `$98-$9E`/`$BC-$C5`) |

```asm
    lda #FP_ADD             ; opcode (from fp.inc)
    jmp kFpCall             ; fac1 = fac2 + fac1
```

---

## Time

> ⚠️ **Lazy lib calls** — `kGetTime`/`kSetTime`/`kPrintTime` are jump-table
> cold stubs that load `time.lib` (lib 0) on first use, then patch the entry
> to the routine's real address (warm calls are a 3-cycle direct `jmp`).
> The implementation lives in `src/libs/time.asm`. See
> [dynamic-libraries.md](dynamic-libraries.md) and the per-call reference
> [lib-time.md](lib-time.md).

### `kGetTime` — `$E036`

Read the CIA #1 Time-of-Day clock. The clock uses BCD format; hours bit 7 is the AM/PM flag.

| | |
|---|---|
| **Input** | — |
| **Output** | `kArg+0` = 1/10 seconds (BCD), `kArg+1` = seconds (BCD), `kArg+2` = minutes (BCD), `kArg+3` = hours (BCD, bit 7 = PM) |
| **Clobbers** | A |
| **Modifies** | `kArg[0..3]` |

```asm
    jsr kGetTime
    lda kArg+2              ; minutes in BCD
    lda kArg+3              ; hours (bit 7 = PM flag)
```

---

### `kSetTime` — `$E039`

Write BCD bytes to the CIA #1 TOD clock. Writing hours stops the clock; it restarts on the next read of `$DC08`.

| | |
|---|---|
| **Input** | `kArg[0..3]` = 1/10s, sec, min, hrs (all BCD; hrs bit 7 = PM) |
| **Output** | — |
| **Clobbers** | A |
| **Modifies** | — |

```asm
    lda #$00; sta kArg      ; 0 tenths
    lda #$00; sta kArg+1    ; 0 seconds
    lda #$30; sta kArg+2    ; 30 minutes (BCD)
    lda #$12; sta kArg+3    ; 12 hours (BCD, bit 7 clear = AM)
    jsr kSetTime            ; set clock to 12:30:00 AM
```

---

### `kPrintTime` — `$E03C`

Read the TOD clock and blit the current time at `(X, Y)` in `"hh:mm:ss AM"` or `"hh:mm:ss PM"` format (11 chars, no newline). Uses `kBlitChar` — no cursor advance and no char-shadow mirror; **displayed surface only** (gate on `kSurfDisplayed` when sharing a screen).

| | |
|---|---|
| **Input** | `X` = column, `Y` = row (blit position) |
| **Output** | — |
| **Clobbers** | A, X, Y, `kPtr`, `srcPtr` |
| **Modifies** | `kArg` |

```asm
    ldx #0
    ldy #0
    jsr kPrintTime          ; blits "12:34:56 AM" at (0,0)
```

---

## Screen Lock

Screen I/O is protected by semaphore 0 (`semCount`). Only one task can hold the lock at a time — other callers yield their timeslice and retry. Unlike raw `SEI`/`CLI`, non-screen tasks continue running while a screen lock is held.

### `kLockScreen` — `$E045`

Acquire screen semaphore (0). Saves `kPtr` and `kArg` to per-task arrays (safe across yields). If another task holds the lock, yields via `syscall` (3) and retries on the next schedule.

**Must be paired with `kUnlockScreen`.**

| | |
|---|---|
| **Input** | — |
| **Output** | — |
| **Clobbers** | A, X |
| **Modifies** | `screenLockKPtrLo/Hi[curTask]`, `screenLockKArg[curTask]` |

```asm
    jsr kLockScreen         ; acquire screen, save kPtr/kArg
    ; ... multi-step screen operations ...
    jsr kUnlockScreen       ; restore kPtr/kArg, release screen
```

---

### `kUnlockScreen` — `$E048`

Release screen semaphore. Restores `kPtr` and `kArg` from per-task arrays, then signals semaphore 0 so waiting tasks can proceed.

| | |
|---|---|
| **Input** | — |
| **Output** | — |
| **Clobbers** | A, X |
| **Modifies** | `semCount[0]` |

```asm
    jsr kUnlockScreen       ; restore state, release lock
```

### Screen Lock Pattern

```asm
    jsr kLockScreen             ; 1. acquire screen lock
    jsr kGetCursor              ; 2. save cursor
    txa; pha; tya; pha
    ldx #0; ldy #0              ; 3. move cursor where needed
    jsr kSetCursor
    ; ... your screen output ... ; 4. do the work
    pla; tay; pla; tax           ; 5. restore cursor
    jsr kSetCursor
    jsr kUnlockScreen           ; 6. release lock
```

---

## Semaphores

GordonOS provides a pool of `MAX_SEMAPHORES` (4) **counting** semaphores for task synchronisation. Each semaphore is a byte: 0 = unavailable, 1-255 = available slots. Semaphore 0 is reserved for screen locking (`kLockScreen`/`kUnlockScreen`). Semaphores 1-3 are free for task use via syscalls.

**Ownership tracking:** Each semaphore has an owner byte (`semOwner[x]`) set only on the 1→0 transition — when the semaphore becomes unavailable. This makes ownership well-defined for mutex-style usage (initialised to 1) but best-effort for counting semaphores (N>1), where a single byte cannot represent multiple concurrent holders. On task death, only semaphores with `semCount == 0` and matching owner are released. This prevents deadlocks (a dead task can't release its mutex) without corrupting counting semaphore state — but tasks using counting semaphores for producer-consumer patterns should not rely on ownership-based cleanup for correctness.

`semWait` atomically checks and decrements the count — if already 0, the caller yields and retries. `semSignal` increments (caps at 255). Both preserve X.

> ✅ **A two-instance proof (8 rounds each) covers this path:** acquire → check
> `semCount+1 == 0` and `semOwner+1 == myTid` → hold across 3 yielding ticks →
> check both again → release, with both instances reporting `ok=8 bad=0` and a
> non-zero wait, so exclusion holds and `semWait` really blocks instead of
> returning.

Callers can use the internal routines directly (from kernel code) or via syscalls 10/11 (from tasks).

### `semWait` (internal; syscall 10)

Acquire semaphore X. Decrements the count if >0 and returns. Ownership is recorded in `semOwner[x]` **only** when the count was 1 before decrementing (becoming unavailable — the mutex acquire). When count > 1, ownership is left unchanged — counting semaphore decrements don't set the owner. If count is 0, yields via `syscall` (3) and retries on the next schedule. Only the calling task blocks — other tasks continue running.

| | |
|---|---|
| **Input** | X = semaphore index (0 to `MAX_SEMAPHORES`-1) |
| **Output** | — |

```asm
    ldx #1
    jsr semWait             ; or: lda #SYS_SEMWAIT; jsr syscall (from a task)
    ; ... critical section ...
```

> ⚠️ **Call with interrupts enabled** (the normal task state): the routines bracket
their critical section with `sei`/`cli` and return with IRQs enabled, so they are
not for use inside an SEI'd region. They also always `cli` on exit — a caller that
entered with IRQs disabled gets them enabled.

### `semSignal` (internal) / syscall 11

Release semaphore X. Increments the count (caps at 255). When the count transitions 0→1 (becomes available again), clears `semOwner[x]` to `$FF` — an available semaphore has no single holder. For counting semaphores (N>1), subsequent signals increment past 1 without touching the owner byte.

| | |
|---|---|
| **Input** | X = semaphore index |
| **Output** | — |

```asm
    ldx #1
    jsr semSignal           ; or: lda #11; jsr syscall
```

### Mutex Pattern (binary)

Initialise semaphore to 1 for mutual exclusion:

```asm
    ; In boot/init: lda #1; sta semCount+2  ; semaphore 2 = 1 slot (mutex)

; Task A and Task B share a buffer
    ldx #2                  ; semaphore 2 = buffer lock
    lda #10
    jsr syscall             ; semWait — blocks until available
    ; ... read/write shared buffer ...
    ldx #2
    lda #11
    jsr syscall             ; semSignal — release
```

### Producer-Consumer Pattern (counting)

Initialise semaphore to N > 1 for a bounded buffer with N slots:

```asm
    ; In boot/init: lda #8; sta semCount+1  ; semaphore 1 = 8 buffer slots

; Producer — fills a slot
    ldx #1
    lda #10; jsr syscall    ; semWait — wait for empty slot
    ; ... write one item to buffer ...
    ldx #1
    lda #11; jsr syscall    ; semSignal — slot now filled (counts up)

; Consumer — empties a slot
    ldx #1
    lda #10; jsr syscall    ; semWait — wait for filled slot
    ; ... read one item from buffer ...
    ldx #1
    lda #11; jsr syscall    ; semSignal — slot now empty (counts up)
```

> **Do:** Use a second semaphore (initialised to 0) for the consumer to signal the producer that items are available. Counting semaphores implement the "empty slots" side; use a second one for "filled slots".

> **Don't:** Hold a semaphore across a `yield` or long-running operation. Semaphores are for brief critical sections and buffer slot management.

> **Don't:** Rely on `semOwner` for application logic. Ownership is an internal cleanup mechanism — the owner byte is set to the *last* acquirer and is best-effort for counting semaphores with count > 1.

---

## Task Info

### `kGetTaskName` — `$E04B`

Look up a task's name string by index. Returns a pointer to the null-terminated
screen-code name (no copy — points directly into the kernel's `taskNameLo/Hi` arrays).

| | |
|---|---|
| **Input** | X = task index (0 to `MAX_TASKS`-1) |
| **Output** | `kPtr` = pointer to null-terminated screen-code name |
| **Clobbers** | A |
| **Modifies** | `kPtr` |

```asm
    lda #7
    jsr syscall             ; A = my task index
    tax
    jsr kGetTaskName        ; kPtr → "clock"
    jsr kPrintString        ; prints the task's name
```

---

## Screen Management

### `kAllocScreen` — `$E04E`

Allocate a REU surface slot (10 KB, banks 1+, 28 max) for the current
task. The slot is cleared (pixels = 0, matrix bg nibble = bg0).
Surface colors come from `kArg` (border, bg0, bg1, bg2). Tasks write to
their surface via the standard `kPrint*` routines; the surface reaches
the framebuffer only when the task is focused (`doGfxSwitch`).

**Idempotent for restored tasks:** when the calling task already owns
or shares a surface (`screenAlloc` set — the pool-eviction restore case
where the task's entry code re-runs), the existing REU slot is kept
(slot, `screenKind` and content preserved) and only the caller's colors
are refreshed. No new slot is consumed, so repeated eviction/restore
cycles don't leak surface slots.

| | |
|---|---|
| **Input** | A = mode (0 = hires-text, 1 = mc-graphics); kArg = border, bg0, bg1, bg2 |
| **Output** | Carry set = no free slot or bad mode |
| **Clobbers** | A, X, Y, kPtr |
| **Modifies** | `taskGfxReu*`, `screenKind`, `screenAlloc`, colors |

```asm
    lda #$0b; sta kArg       ; border = dark grey
    lda #$00; sta kArg+1     ; bg0 = black
    lda #$00; sta kArg+2     ; bg1
    lda #$00; sta kArg+3     ; bg2
    lda #0                   ; hires-text surface
    jsr kAllocScreen
    bcs noScreen             ; all 28 slots taken
```

> **All-bitmap note:** `$D018` is fixed (`GFX_D018`) — no per-screen
> charset anymore. Surface colors live in `taskGfxBorder/Bg0/Bg1/Bg2`
> and are applied by `doGfxSwitch` when the surface is displayed.
> There is a single lowercase/uppercase font (no glyph-set switching).

### `kFreeScreen` — `$E051`

Release the current task's surface. The REU slot is returned to the free pool. If this was the last allocated surface, the system falls back to the shared `$2000` framebuffer display.

| | |
|---|---|
| **Input** | — |
| **Output** | — |
| **Clobbers** | A, X |
| **Modifies** | `screenAlloc` array |

```asm
    jsr kFreeScreen         ; release this task's screen
```

### `kSetScrollRegion` — `$E0E7`

Set the current surface's scroll region — the rows that auto-scroll when
`kPrintChar`/`kPrintString`/`kPrintGlyph`/`kNewline` run past the bottom.
The region is **per-surface**: it is stored in the slot's matrix tail
(`+$23EE`/`+$23EF`) and so survives view switches, pool eviction and
surface sharing. Default 0–24.

| | |
|---|---|
| **Input** | A = top row (inclusive), X = bottom row (inclusive) |
| **Output** | Carry clear = valid; Carry set = invalid, region unchanged |
| **Clobbers** | A, X, Y, kPtr |
| **Modifies** | `kArg`..`kArg+6`, `taskScrollTop/Bottom[curTask]`, slot tail |

```asm
    lda #8                  ; top
    ldx #16                 ; bottom (0–24)
    jsr kSetScrollRegion    ; rows 8..16 scroll; C=1 if invalid
```

Invalid (C=1, state unchanged): bottom ≥ 25, or top > bottom.
`top == bottom` is a valid single-row region (only that row scrolls/blanks).

### `kGetScrollRegion` — `$E0EA`

Read the current surface's scroll region.

| | |
|---|---|
| **Input** | — |
| **Output** | A = top, X = bottom, Carry clear |
| **Clobbers** | A, X (outputs) |
| **Modifies** | — |

```asm
    jsr kGetScrollRegion    ; A = top, X = bottom
```

### `kSwitchView` — `$E054`

Switch the VIC-II display to another task's screen. Does NOT affect where the current task writes — only changes what the user sees. Falls back to the default `$2000` display if the target has no screen. Always returns carry clear.

> **The display blanks for the hand-over.** The switch saves the outgoing
> framebuffer and loads the incoming one — about 20 KB of REU traffic, one whole
> frame — with interrupts off, so `doGfxSwitch` clears `DEN` (`$D011` bit 4)
> across that window and restores it together with the incoming surface's mode
> bits. Two things follow: the beam cannot sample a half-restored screen, and with
> no Bad Lines there are no `c`-accesses — which are the only thing in the machine
> that reads colour RAM — so the VIC leaves colour RAM to the transfer.

> **`kSwitchView` writes the `kArg` block, so the IRQ applies it late.**
> `doGfxSwitch` stores `fromTask` in `kArg` and parameterises its `kReu*` calls
> through `kArg+0..+5`, and `kbPoll` runs *before* `switchTask` in the same tick —
> so an F-key switch issued from the key scan would write into whatever a running
> task had live in the block. `kbPoll` therefore only **records** the requested
> screen (`kbScreenReq`, `$FF` = none) and `kbScreenGate` applies it from the
> scheduler's switch path, at the one point in the tick where the outgoing task's
> block has already been saved to `REU_KARG_BASE + slot x 8` and the incoming
> task's has not yet been restored. Two consequences for callers: a task may keep
> `kArg` marshalled across an F-key press, and the F-key response still lands in
> the same tick. An ordinary preemption never touched the block either —
> `switchTask` saves and restores all 8 bytes per task. `kArg` remains scratch
> *within* a call: any kernel call writes it, so a value must not be held across
> a competing call.

| | |
|---|---|
| **Input** | X = task index (preserved) |
| **Output** | Carry always clear |
| **Clobbers** | A, Y |

```asm
    ldx #2                  ; task index
    jsr kSwitchView         ; show task 2's screen (or $2000 if none)
```

---

### `kViewScreen` — `$E057`

Switch the VIC-II display to another task's screen **without** changing keyboard focus. The current task keeps keyboard ownership — only the visual display changes. Use this when you want to peek at another screen without giving up input. Falls back to the default `$2000` display if the target has no screen.

| | |
|---|---|
| **Input** | X = task index (preserved) |
| **Output** | Carry always clear |
| **Clobbers** | A, Y |

```asm
    ldx #3                  ; task index
    jsr kViewScreen         ; show task 3's screen (keyboard focus unchanged)
```

---

### `kShareScreen` — `$E05A`

> ⚠️ **The target must OWN a surface.** `taskParent[me]` gives the task that
> *spawned* you, which is the surface owner only one level deep — every `.com`
> works because the shell spawned it, but a task spawned by a task gets an
> intermediate that owns nothing, `C=1`, and (with the usual "no surface ⇒ exit"
> path) no output whatsoever. Walk up the chain to the first ancestor that owns
> one.

Attach the current task to another task's surface. Both tasks write to the same
memory — useful for overlay displays (e.g., clock on shell). If the current task
owned a private screen, it is freed. Only the owner can free the buffer.

| | |
|---|---|
| **Input** | X = target task index |
| **Output** | Carry set = target has no screen |
| **Clobbers** | A, Y |
| **Modifies** | `screenBase` arrays, `screenOwner` |

```asm
    ldx #1                  ; shell's task index
    jsr kShareScreen        ; now shares shell's $2000
    bcs noScreen
```

---

### `kTakeScreenOwnership` — `$E05D`

Transfer full ownership of a screen from a source task to the current task. The source
slot is completely cleaned (`screenAlloc=0`, `screenOwner=0`). The current task becomes
the sole owner. Atomic — uses `SEI`/`CLI` to protect `curTask`.

Use this when a parent task allocates a screen and a child task should inherit it
(e.g., boot allocates, shell takes ownership).

| | |
|---|---|
| **Input** | X = source task index (must have `screenAlloc=1`, `screenOwner=$FF`) |
| **Output** | Carry set = source has no owned screen |
| **Clobbers** | A, Y |
| **Modifies** | `screenBase` arrays, `screenAlloc`, `screenOwner` |

```asm
    ldx #0                  ; boot's task index
    jsr kTakeScreenOwnership ; shell now owns boot's screen
    bcs noScreen
```

---

### `kSetTextColor` — `$E063`

Set the text color for the current task's surface. Writes to the per-task `taskTextColor`;
`kPrintChar` picks it up on the next character printed. Does not retroactively change
already-printed text.

| | |
|---|---|
| **Input** | A = color (0–15) |
| **Output** | — |
| **Clobbers** | A, Y, kPtr |

```asm
    lda #$05                ; green text
    jsr kSetTextColor
```

---

### `kSetCursorColor` — `$E066`

Set the cursor color for the current task's surface. Writes to the per-task `taskCursorColor`;
the blink handler picks it up on the next toggle.

| | |
|---|---|
| **Input** | A = color (0–15) |
| **Output** | — |
| **Clobbers** | A, Y, kPtr |

```asm
    lda #$02                ; red cursor
    jsr kSetCursorColor
```

---

### `kSetCharShadow` — `$E09C`

Enable or disable the **char shadow** for the current task's surface.
When enabled, every character printed by this task (via `kPrintChar`,
`kPrintString`, `kReadString` echo) is additionally mirrored
into a 1 KB REU region — `SHADOW_BASE ($2000) + gfxSlot×$400` in bank 0 —
so the surface's screen codes can be read back exactly (no glyph OCR).
`kClearScreen` and `kScrollScreen` keep the shadow in sync (fill with
`$20`, row shift). Disabled tasks pay one flag check per printed char.

The flag and the cached shadow address survive pool eviction: the
surface slot is preserved (`allocScreen`'s restore path keeps it), and
the shadow region in bank 0 survives with it. Restoring re-spawns the
task, which clears the flag — the entry must call `kSetCharShadow(1)`
**before drawing** (idempotent). A *fresh* surface allocation blanks the
shadow region, so a reused slot can't expose the previous owner's text
through `kCharAt`. `kFreeScreen`/`sysKill`/spawn/sharing clear the flag.

| | |
|---|---|
| **Input** | A = 1 enable, 0 disable (current task) |
| **Output** | C=0; no-op (flag off) if the task has no surface |
| **Clobbers** | A, X, Y |
| **Modifies** | `taskShadowFlag/Hi[curTask]`, the shadow region in REU bank 0 |

```asm
    lda #1
    jsr kSetCharShadow      ; mirror this surface's text from now on
    ; ...print as usual; the shadow follows...
```

---

### `kCharAt` — `$E09F`

Read a screen code back from the current task's **char shadow** — exact
text read-back, no glyph OCR. The shadow must be enabled via
`kSetCharShadow`; `kClearScreen`/`kScrollScreen` keep it in sync, so the
read reflects the displayed text. Without a surface or an enabled
shadow the call returns `A=$20` with `C=1` (graceful fallback).

| | |
|---|---|
| **Input** | A = col (0-39), Y = row (0-24) — matches `kGetCursor`'s X/Y |
| **Output** | A = screen code; C=1 + A=$20 if unavailable |
| **Clobbers** | A, X, kArg+6/+7 |
| **Modifies** | — (Y preserved) |

```asm
    jsr kGetCursor          ; X=col, Y=row
    txa
    jsr kCharAt             ; A = screen code at the cursor
    bcs noText              ; no shadow — A=$20
```

---

### `kReadRow` — `$E0A2`

Read a full 40-char screen row back from the current task's **char
shadow** in one DMA — the row variant of `kCharAt`, used by the EhBASIC
line editor's `elScanRow`. The shadow must be enabled via
`kSetCharShadow`; without a surface or an enabled shadow the call fills
the destination with 40 spaces and returns `C=1`.

| | |
|---|---|
| **Input** | A = row (0-24); `kPtr` = caller's 40-byte dest buffer (not advanced) |
| **Output** | C=0 row copied; C=1 + 40 spaces if unavailable |
| **Clobbers** | A, X, Y, kArg..kArg+5 |
| **Modifies** | — (`kPtr` preserved) |

```asm
    lda #<rowBuf; sta kPtr
    lda #>rowBuf; sta kPtr+1
    lda cursorRow
    jsr kReadRow            ; rowBuf = screen codes (40 bytes)
```

---

### `kPrintCharAt` — `$E0A5`

Write one glyph (plus its matrix colour nibble) at an explicit cell,
**without** advancing the cursor, wrapping, or scrolling. It routes on
the task's **surface** exactly as `kPrintChar` does: displayed -> the
framebuffer path, which erases a live blink block first (restoring at the
blink's *saved* position) and writes the foreground nibble from
`taskTextColor`; background -> the glyph and the nibble go into the task's
own REU slot, so a background task's fixed row cannot land on the
displayed screen. Either way it mirrors the char into the char shadow (if
enabled), leaves the live cursor untouched, and never fires the region
wrap-scroll. Used by the EhBASIC line editor so a line may sit on the
bottom row.

| | |
|---|---|
| **Input** | A = char (screencode), X = col (0-39), Y = row (0-24) |
| **Output** | — |
| **Clobbers** | A, X, Y, kPtr, srcPtr, kArg..kArg+7 |
| **Modifies** | framebuffer or REU-slot cell + matrix nibble; char shadow cell (if enabled); resets `cursorVisible` on the displayed path |

```asm
    lda #$20
    ldx #39
    ldy #24
    jsr kPrintCharAt        ; blank (39,24) — no scroll
```

---

### `kPrintGlyph` — `$E0A8`

Print a custom 8-byte glyph at the current cursor position, then advance
the cursor — identical to `kPrintChar` (colour, wrap, scroll, cursor
handling) except the glyph comes from an arbitrary C64 buffer instead of
the font.

| | |
|---|---|
| **Input** | `kPtr` = pointer to the 8 glyph bytes |
| **Output** | — |
| **Clobbers** | A, X, Y, kPtr, srcPtr, kArg..kArg+6 |
| **Modifies** | framebuffer/REU-slot cell + matrix nibble; char shadow cell = space (`$20`) if enabled |

```asm
    lda #<myGlyph; sta kPtr
    lda #>myGlyph; sta kPtr+1
    jsr kPrintGlyph         ; blit myGlyph at the cursor
```

The char shadow (if enabled) is mirrored with a **space** (`$20`) rather
than a screen code, so shadow read-back (`kCharAt`/`kReadRow`) shows a
blank instead of a stale glyph.

---

### `kPrintGlyphAt` — `$E0F3`

Write a custom 8-byte glyph (plus its matrix colour nibble) at an explicit
cell — `kPrintCharAt`'s fixed-cell write with the glyph taken from a C64
buffer instead of the font. It advances, wraps and scrolls **nothing**, so the
last cell of the last row (`39,24`) is as safe as any other cell: `kPrintGlyph`
would wrap on the cell it has just written, and `wrapClamp` would then scroll
the whole surface while the cell is being written.

| | |
|---|---|
| **Input** | `srcPtr` = pointer to the 8 glyph bytes, `X` = col (0-39), `Y` = row (0-24) |
| **Output** | — (the cursor is preserved) |
| **Clobbers** | A, X, Y, kPtr, kArg..kArg+6 (`srcPtr` is read, never written) |
| **Modifies** | framebuffer/REU-slot cell + matrix nibble; char shadow cell = space (`$20`) if enabled |

```asm
    lda #<myGlyph; sta srcPtr
    lda #>myGlyph; sta srcPtr+1
    ldx #39
    ldy #24
    jsr kPrintGlyphAt      ; blit myGlyph at (39,24) -- no cursor move, no scroll
```

Routing is `kPrintCharAt`'s: a displayed surface blits the framebuffer, a
background one writes the task's own REU slot, and the char shadow mirrors a
space (`$20`) so read-back shows a blank. The colour is
`taskTextColor[curTask]`. SEI-guarded, and a live blink block is un-drawn first
at the block's saved position, so a cell written under the cursor cannot leave
the block's stale glyph behind.

---

### `kBlitChar` — `$E0ED`

Blit one font glyph (plus its matrix colour nibble) at an explicit cell
**without** advancing the cursor and **without** mirroring the char
shadow. The fixed-position primitive for UI (status bars) that must not
disturb the editing cursor or the document shadow. Displays only — it
writes the framebuffer; `kPrintCharAt` is the sibling that also routes to
a background task's own REU slot.

The cursor is left alone unless the blit cell is exactly the live blink
block's cell — in that case the block is un-drawn first so the next
blink OFF cannot restore a stale glyph over the fresh char (same
discipline as `printChar`). Blits elsewhere (e.g. the clock's time at
`(0,0)`) never touch the cursor, so the cursor keeps blinking normally.

The background nibble is always **bg0**, read from `taskGfxBg0` — it is *not*
taken from the cell already on screen. That matters whenever the same cell is
repainted in a different video mode: blitting a normal glyph over a cell that
`kBlitCharRev` drew yields a plain cell, because the old reverse-video bar
nibble cannot leak into the new one. This is what makes mark/un-mark cycles in
the editor's selection highlight idempotent.

| | |
|---|---|
| **Input** | A = char (screencode), X = col (0-39), Y = row (0-24) |
| **Output** | — |
| **Clobbers** | A, X, Y, kPtr, srcPtr, kArg..kArg+7 |
| **Modifies** | framebuffer cell + matrix nibble `(taskTextColor<<4)\|bg0` |

```asm
    lda #'a'
    ldx #10
    ldy #24
    jsr kBlitChar           ; draw 'a' at (10,24); no cursor advance, no shadow
```

### `kBlitCharRev` — `$E0F0`

Same as `kBlitChar` but **reverse video**: the matrix nibble is
`(bg0<<4)|taskTextColor`, so the cell shows a solid bar in the text
colour with the glyph in bg0. Idempotent — re-drawing does not fade the
text (the glyph colour is read from `taskGfxBg0`, not the cell nibble).

```asm
    lda #' '; ldx #0; ldy #24
    jsr kBlitCharRev        ; blank cell → solid text-colour bar segment
```

---

## REU DMA (Hardware-Accelerated)

All REU routines preserve the caller's interrupt state via `php`/`plp`. They poll `$DF00` until the transfer completes.

**Common parameter block** for `kReuToC64`, `kReuFromC64`:

| Register | Content |
|---|---|
| `kPtr`/`kPtr+1` | C64 address |
| `kArg`/`kArg+1` | REU address (16-bit within bank) |
| `kArg+2` | REU bank |
| `kArg+3`/`kArg+4` | Length (16-bit; `$0000` = 64KB) |

### `kReuToC64` — `$E069`

Copy from REU to C64 memory. Both addresses increment (normal block copy).

| | |
|---|---|
| **Input** | See common parameter block above |
| **Output** | — |
| **Clobbers** | A |
| **Modifies** | `$DF00`–`$DF0A`, C64 memory at `kPtr` |

```asm
    ; copy 256 bytes REU bank 0:$1000 → C64 $4000
    lda #<$4000; sta kPtr
    lda #>$4000; sta kPtr+1
    lda #<$1000; sta kArg
    lda #>$1000; sta kArg+1
    lda #0; sta kArg+2          ; bank 0
    lda #0; sta kArg+3
    lda #1; sta kArg+4          ; 256 bytes
    jsr kReuToC64
```

---

### `kReuFromC64` — `$E06C`

Copy from C64 memory to REU. Both addresses increment.

| | |
|---|---|
| **Input** | See common parameter block above |
| **Output** | — |
| **Clobbers** | A |
| **Modifies** | `$DF00`–`$DF0A`, REU memory at `kArg` |

```asm
    ; copy 1024 bytes C64 $2000 → REU bank 0:$2000
    lda #<$2000; sta kPtr
    lda #>$2000; sta kPtr+1
    lda #<$2000; sta kArg
    lda #>$2000; sta kArg+1
    lda #0; sta kArg+2
    lda #0; sta kArg+3
    lda #4; sta kArg+4          ; 1024 bytes
    jsr kReuFromC64
```

---

### `kReuFillC64` — `$E06F`

Fill a C64 memory region with a constant byte. Uses the REU's fixed-REU-address mode: the fill byte is stored in REU at the bounce buffer, then DMA'd to C64 with the REU address held constant.

| | |
|---|---|
| **Input** | `kPtr`/`kPtr+1` = C64 destination, A = fill byte, `kArg`/`kArg+1` = length |
| **Output** | — |
| **Clobbers** | A, Y |
| **Modifies** | `$DF00`–`$DF0A`, REU `$000800` (bounce buffer), C64 memory at `kPtr` |

```asm
    ; fill C64 $0400-$07FF with $20 (space)
    lda #<$0400; sta kPtr
    lda #>$0400; sta kPtr+1
    lda #0; sta kArg
    lda #4; sta kArg+1          ; 1024 bytes
    lda #$20                    ; fill byte last — A is clobbered by setup
    jsr kReuFillC64
```

---

### `kReuFillReu` — `$E072`

Fill a REU memory region with a constant byte. Uses the REU's fixed-C64-address mode: the fill byte is held at a kernel temp address while DMA streams it to incrementing REU addresses.

| | |
|---|---|
| **Input** | `kArg`/`kArg+1` = REU address, `kArg+2` = bank, `kArg+3`/`kArg+4` = length, A = fill byte |
| **Output** | — |
| **Clobbers** | A |
| **Modifies** | `$DF00`–`$DF0A`, REU memory at `kArg` |

```asm
    ; fill REU bank 1:$0000-$0FFF with $00
    lda #0; sta kArg
    lda #0; sta kArg+1          ; REU addr = $0000
    lda #1; sta kArg+2          ; bank 1
    lda #0; sta kArg+3
    lda #$10; sta kArg+4        ; 4096 bytes
    lda #$00                    ; fill with zeroes
    jsr kReuFillReu
```

---

## REU Filesystem (Storage)

> Flat filesystem on the REU. Files are named blocks of C64 memory saved to/persisted from REU. Root directory only (no subdirectories). **24-bit offsets:** directory = 512 × 32-byte entries at bank 5 `$9000-$CFFF` (16 KB); the data region starts at bank 5 `$D000` and spans banks 5+ with automatic bank-crossing DMA. Capacity is 24-bit — `$3000 + (totalBanks − 10) × $10000` ≈ 15.8 MB at 256 banks. File *size* stays 16-bit (≤ `$FFFF`).
>
> ⚠️ **Lazy lib calls** — `kReuFormat`/`kReuSave`/`kReuDelete`/`kReuRename`/
> `kReuDirEntry` are jump-table stubs that cold-load `filesys.lib` (lib 1)
> on first use. `kReuLoad` stays resident. See
> [dynamic-libraries.md](dynamic-libraries.md) and the per-call reference
> [lib-filesys.md](lib-filesys.md).

### `kReuFormat` — `$E07E`

Format the REU filesystem. Zeroes the directory and initialises slot 0 (allocator state). Does **not** prompt — the caller is responsible for confirmation.

| | |
|---|---|
| **Input** | (none) |
| **Output** | C=0 success |
| **Clobbers** | A, X, Y, kArg+4..kArg+7 |
| **Modifies** | REU directory (all 512 entries zeroed), slot 0 initialised |

Example:
    jsr kReuFormat           ; formats the REU filesystem

---

### `kReuDirEntry` — `$E081`

Read a single directory entry by index (0–511). For slot 0, returns the allocator's `nextFreeOffset` (24-bit). For slots 1–511, returns file name, size, flags, and 24-bit data offset. Deleted entries (b7 set) are treated as empty (C=1).

| | |
|---|---|
| **Input** | A = entry index lo, X = entry index hi (0/1), `kPtr` = C64 buffer for name (≥12 bytes) |
| **Output** | C=0 success: buffer = null-terminated name, `kArg`/`kArg+1` = size (16-bit LE), `kArg+2` = flags, `kArg+3`/`kArg+4`/`kArg+5` = data offset (24-bit LE — file entries; slot 0 returns `nextFreeOffset` there) |
| | C=1 entry ≥ 512, empty/deleted slot, or FS not enabled |
| **Clobbers** | A, X, Y, kArg+2..kArg+7 |
| **Modifies** | `kPtr` buffer, `reuDirBuf` |

```asm
    lda #<nameBuf; sta kPtr
    lda #>nameBuf; sta kPtr+1
    lda #1
    ldx #0                   ; entry hi (entries 0-255)
    jsr kReuDirEntry         ; read entry 1
    bcs empty                ; empty/deleted
    ; nameBuf = "myfile", kArg/kArg+1 = size, kArg+3/4/5 = offset
```

---

### `kReuSave` — `$E084`

Save a C64 memory block to the REU filesystem. The name must be 1–11 characters and unique (not matching any existing alive entry). Data goes to the end of the data area.

| | |
|---|---|
| **Output** | C=0 success: `kArg+4`/`kArg+5` = size saved; C=1 failure: `kArg+6` = 0 (duplicate), 1 (no space), 2 (dir full); other failures (FS disabled/bad size) may leave `kArg+6` undefined

```asm
    lda #<$0400; sta kPtr
    lda #>$0400; sta kPtr+1   ; start = $0400
    lda #<myName; sta kArg
    lda #>myName; sta kArg+1  ; name pointer
    lda #<$0500; sta kArg+2
    lda #>$0500; sta kArg+3   ; end = $0500 (256 bytes)
    jsr kReuSave
    bcs saveFailed
    ; kArg+4/kArg+5 = 256
```

---

### `kReuLoad` — `$E087`

Load a named file from REU to C64 memory. The caller is responsible for ensuring the destination buffer is large enough. Multi-bank files are handled transparently — the transfer is chunked at each bank boundary (data base is bank 5 `$D000`, so a crossing happens at `$10000 − addr-within-bank`). Internally this is `reuFindFile` (locate, no DMA) + `reuDmaRange` (range DMA); the whole find→DMA sequence is atomic — `kReuLoad` jumps to `reuLoadAtomic`, a `php/sei…plp` wrapper that preserves the caller's I flag and C result.

| | |
|---|---|
| **Input** | `kPtr`/`kPtr+1` = C64 destination, `kArg`/`kArg+1` = name pointer (null-term) |
| **Output** | C=0 success: `kArg+2`/`kArg+3` = size loaded; C=1 not found or FS disabled |
| **Clobbers** | A, X, Y, kArg+2..kArg+7, kPtr |
| **Modifies** | C64 memory at destination |

```asm
    lda #<$0600; sta kPtr
    lda #>$0600; sta kPtr+1   ; destination
    lda #<myName; sta kArg
    lda #>myName; sta kArg+1  ; name
    jsr kReuLoad
    bcs notFound
    ; data loaded to $0600
```

---

### `kReuDelete` — `$E08A`

Mark a file as deleted in the REU directory. Sets the deleted flag (b7) and clears the name to spaces. The data blocks are NOT reclaimed — they stay orphaned until the `compact.com` command packs them away.

| | |
|---|---|
| **Input** | `kArg`/`kArg+1` = name pointer (null-term) |
| **Output** | C=0 deleted; C=1 not found or FS disabled |
| **Clobbers** | A, X, Y |
| **Modifies** | REU directory entry (flags set to b7, name cleared) |

```asm
    lda #<myName; sta kArg
    lda #>myName; sta kArg+1
    jsr kReuDelete
    bcs notFound
```

---

### `kReuRename` — `$E0AB`

Rename a file (directory entry). Only the name field changes — offset, size, and flags stay as they are. The old name must exist (alive) and the new name must not exist; deleted entries don't count, so a name freed by `kReuDelete` can be reused. Both scans go through `reuFindFile`, and the whole scan+modify region (DMA page in, name overwrite, DMA out) runs as one `php/sei…plp` atomic block — the caller's I flag is preserved.

| | |
|---|---|
| **Input** | `kArg`/`kArg+1` = old name pointer (null-term), `kArg+2`/`kArg+3` = new name pointer (null-term) |
| **Output** | C=0 renamed; C=1 failure: `kArg+6` = 0 (old not found), 1 (new exists), 2 (bad name: empty or >11 chars) |
| **Clobbers** | A, X, Y, kArg+6 |
| **Modifies** | REU directory entry name field (bytes +1..+16, space-padded) |

```asm
    lda #<oldName; sta kArg
    lda #>oldName; sta kArg+1  ; old name
    lda #<newName; sta kArg+2
    lda #>newName; sta kArg+3  ; new name
    jsr kReuRename
    bcs renameFailed           ; kArg+6 = reason
```

---

### `kReuDmaRange` — `$E116`

Stream a file range from REU to C64 memory given a 24-bit FS data offset.
Resident helper (not a lazy lib call) used by `banner`, `type`, `edit`, and
the shell's `runbatch` to DMA file contents without hand-computing
multi-bank addresses.

| | |
|---|---|
| **Input** | `reuFsPtr`/`+1`/`+2` = 24-bit FS data offset (data base = bank 5 `$D000`), `kArg+6`/`kArg+7` = length (16-bit), `kPtr`/`kPtr+1` = C64 destination |
| **Output** | (none — void) |
| **Clobbers** | A, X, Y, `kArg`..`kArg+5` (REU DMA params), `reuFsFile`, `reuFsLen`, `reuFsFlags` |
| **Modifies** | C64 memory at the destination |
| **Preserves** | `reuFsPtr` (3B), `reuFsRemain`, `kArg+6`/`kArg+7`, `kPtr` (restored to the original destination) |

The offset lives in the kernel-global 3-byte `reuFsPtr` — callers must
`sei`/`cli` around the setup + call (the loader uses the same discipline).

**24-bit invariant.** `reuFsPtr` has three independent writers — `reuFindFile`
(a lookup result), the dynamic loader (its own load cursor) and `fontGlyph` (a
computed glyph offset) — so code that *holds* an offset across a lookup must
copy all three bytes, and arithmetic on it must propagate the carry into `+2`.
The bank byte is 0 only for files below FS `$10000`, and the layout is user data
(`compact` repacks the FS downward), so "the bank byte is always 0" is never
safe, and both failure modes are real: a carry dropped in a three-byte add, and
a 2-of-3-byte stash of an offset. `tools/check-fs-offsets.ps1` fails the
build on that mistake and runs from `build-kernel.ps1`/`build-tasks.ps1`.

**Write these operations with the macros in `src/kernel/fs-offset.inc`**
(`FSCopy`, `FSAdd16`, `FSAddPage`, `FSToReuAddr`) rather than spelling out the
three-byte sequences: the carry into `+2` then exists once, and
`FSToReuAddr` names the `(O + $D000)` wrap rule that is easy to get wrong by
hand (see the bank-crossing table below).

**`reuFsPtr` is shared scratch, not "the current file".** `filesys.lib` and
`gfx.lib` use it as their working offset too, so any filesystem operation can
clobber it. Treat it as an argument register: set it, then call the DMA, and
do not expect it to survive a find, a lib call or a font glyph. The dynamic
loader keeps its own copy in `dlFsSave` and installs it before each DMA it
issues (`dlInstallCursor`, see `cursor-helpers.inc`), which is why a nested
lookup inside a load cannot disturb the load.

A file **may** straddle a bank boundary — the REU address space is linear in the
offset, so the FS is one contiguous image — but the 16-bit DMA length register
means each transfer must be clamped to the end of its bank. `reuDmaRange`
(REU→C64), `fsxWriteRange`/`fsxCreateZero` (C64→REU) and `compact`'s `cmMove`
all clamp; new code must transfer FS data through one of them rather than
issuing its own 16-bit-length DMA.

---

### In-place file I/O (filesys.lib, lazy) — fixed-size data files

Four lazy `filesys.lib` calls for create/open/read/write of **fixed-size**
data files (no append/resize; size ≤ `$FFFF` = 65535 bytes). `kReuOpen`
resolves the name once and writes a 5-byte **file record** into
caller-owned memory — `[size lo, size hi, base lo, base mid, base hi]`
(16-bit size + 24-bit base). `kReuReadAt`/`kReuWriteAt` take a **pointer to
that record**, so the directory is scanned only at open — reads/writes
themselves do no directory DMA.

### `kReuCreate` — `$E0F9`

Create a fixed-size file and zero it.

| | |
|---|---|
| **Input** | `kArg`/`kArg+1` = name pointer (1–11 chars), `kArg+2`/`kArg+3` = size (16-bit, > 0) |
| **Output** | C=0 created (zeroed); C=1 error, `kArg+6` = 0 dup, 1 no space, 2 dir full, 3 name >11, 4 empty, 5 zero size |

### `kReuOpen` — `$E0FC`

Resolve a name → 5-byte file record (doubles as the existence check).

| | |
|---|---|
| **Input** | `kArg`/`kArg+1` = name pointer, `kPtr`/`kPtr+1` = 5-byte record buffer |
| **Output** | C=0: record written; C=1 not found / FS disabled (`kArg+6` = 6) |

### `kReuReadAt` — `$E0FF`

Read `len` bytes at `pos`, clamped at EOF.

| | |
|---|---|
| **Input** | `kArg`/`kArg+1` = record ptr, `kArg+2`/`kArg+3` = pos (16-bit), `kArg+6`/`kArg+7` = len (16-bit), `kPtr`/`kPtr+1` = C64 destination |
| **Output** | C=0: `kArg+6`/`kArg+7` = actual bytes read — **0 = EOF** (`pos ≥ size`), `< len` = request ran off the end |

### `kReuWriteAt` — `$E102`

Write `len` bytes at `pos`; writes past the file end are rejected.

| | |
|---|---|
| **Input** | `kArg`/`kArg+1` = record ptr, `kArg+2`/`kArg+3` = pos, `kArg+6`/`kArg+7` = len, `kPtr`/`kPtr+1` = C64 source |
| **Output** | C=0 written; C=1 error: `kArg+6` = 6 (FS disabled) or 7 (`pos+len > size`) |

---

---

## Dynamic Task Loader

> Pool allocator for dynamic task loading. **Single pool** `$5700-$C3FF` (27.25KB, page-granular — page size configurable via `pool.inc`, currently 256B = 109 pages, hard against the `$C400` loader/scroll scratch page; no C64 RAM is reserved for the font). Every FS binary is relocatable; a binary that wants program RAM sets `KF_MALLOC_RAM` and gets a runtime-sized `kMalloc` block — there is no fixed `data_size_region` field. ⚠️ KickAssembler binds `>` looser than `+` — use the `POOL_END` constant, never `#>POOL_BASE + PAGES*SIZE`.
>
> **Fragmentation is an accepted limitation.** The pool is contiguous-only: a load
> needs N **adjacent** free pages, and nothing relocates a live block, so mixed-size
> `run`/`exit` churn can refuse a load (error 4, `? no space in pool`) with plenty of
> total free space. What is already mitigated (bottom/top split, eviction+restore
> re-placement, REU-preserved `kMalloc`) and the analysis of the remaining options:
> [programmers-guide.md](programmers-guide.md) § Pool fragmentation.
>
> **Page-size single source of truth** (`src/kernel/pool.inc`): `POOL_PAGE_SIZE` is the only knob, defined once and imported by **both** the kernel build (via `kernel.inc`) and the task build (via `tools/assemble-tasks.asm`). `POOL_PAGE_SHIFT` is computed from it by a recursive `ilog2` function (`POOL_PAGE_SHIFT = ilog2(POOL_PAGE_SIZE >> 8)` — KickAssembler has no integer log2), and `POOL_PAGE_MASK`, `POOL_PAGES`, `POOL_END`, `POOL_BITMAP_BYTES` all follow. All page→byte/byte→page math in `dynload.inc`/`malloc.inc` goes through the `poolAsl`/`poolLsr` macros (emit `asl`/`lsr` `POOL_PAGE_SHIFT` times). `MAX_MALLOC_PAGES` is likewise derived — `MALLOC_SHADOW_BYTES (32 KB) / (2 × POOL_PAGE_SIZE)`, i.e. half the per-slot REU malloc shadow for program RAM and half for runtime malloc — so `2 × MAX_MALLOC_PAGES × pageSize ≤ 32 KB` always holds. `main.asm` asserts `POOL_PAGE_SIZE == $100 << POOL_PAGE_SHIFT` (catches non-power-of-2 sizes) and pins the current derived results (`POOL_PAGES`, `POOL_BITMAP_BYTES`, `MAX_MALLOC_PAGES`) so an accidental page-size change fails the build.

### `allocFromPool` — `$4310` (internal)

Allocate `pages` consecutive pages. Scans the bitmap for a run of clear bits and sets them.

| | |
|---|---|
| **Input** | X = pages needed; `dlAllocHi` = 1 → highest fit, 0 → lowest fit |
| **Output** | C=0, A = startPage; C=1 if no space |
| **Clobbers** | A, **X**, Y, kArg+4..kArg+6 |

⚠️ **X is clobbered.** The `poolBit*` helpers end in `tax`, and the search runs
one per candidate page plus one per page marked, so X cannot be promised to any
caller. **The requested count is echoed in `kArg+4`** at entry and re-installed
by every call — including the `kmEvictAlloc` retry, where `kArg` itself is
garbage — so a caller that needs the count afterwards reads `kArg+4` and never a
register. `kMallocImpl` records a block's page count from there, and that count
is what `kFree`/`freeMallocBlocks` free later.

**Two placements, one exhaustive search.** The direction only changes
which end the candidate walk starts from (`afpScan` from `POOL_PAGES-pages`
downward, or from `0` upward), so the fit test is byte-for-byte the same
decision: nothing is reserved for either kind and no page becomes unusable.

| Direction | Set by | Used for | Why |
|---|---|---|---|
| lowest (`dlAllocHi` = 0) | default | task code, program RAM, `kMalloc` | Tasks grow up from the bottom, so an exiting task's pages always rejoin the contiguous task region |
| highest (`dlAllocHi` = 1) | `dlLibCore` (a lib load), consumed by `dlAllocCode` | libraries | A library can never sit *between* two task blocks and strand the space |

Entered by `libLoad` through `dlLibCore` (a wrapper that sets the flag, calls
`dlLoadCore` and always clears it again) and chosen per code block by
`dlAllocCode` (`pool-top.inc`, `$53F2` pocket): it consumes the flag on success
so a task's program-RAM block still grows up, and leaves it set on failure so
`dlLoadCore`'s evict-and-retry keeps the same placement. Task loads never set
the flag, and the flag always returns to 0.

### `freeFromPool` — internal

Free `pages` starting at `startPage`. Clears the corresponding bits.

| | |
|---|---|
| **Input** | X = startPage, Y = pages |
| **Output** | — |
| **Clobbers** | A, X, Y, kArg+4, kArg+6 (`poolBitClear` ends in `tax`) |

### `dynRegister` — internal

Add a task to the dynamic task table. Finds the first free slot (dynTaskId[y] = $FF), stores origin, size, flags, and startPage. Sets dynTaskId to the slot index as a placeholder (replaced by real GordonOS task ID after spawn).

| | |
|---|---|
| **Input** | `kArg`/`kArg+1` = origin, `kArg+2`/`kArg+3` = size, `kArg+4` = flags, `kArg+6` = startPage |
| **Output** | C=0, A = slot index; C=1 if table full |
| **Clobbers** | A, Y |

### `dynFindByTaskId` — `$498A` (internal)

Find a dynamic task table slot by its GordonOS task ID.

| | |
|---|---|
| **Input** | A = task ID |
| **Output** | C=0, A = slot index; C=1 if not found |
| **Clobbers** | A, Y |

### `dynFree` — `$445E` (internal)

Free a dynamic task's table entry and bitmap pages by its GordonOS task ID.
If the task owns the single-instance data-region record, the region
pages are freed and the record cleared too. Then runs `dlRestore` to swap
any evicted task back in whose code now fits.

| | |
|---|---|
| **Input** | A = task ID |
| **Output** | C=0 freed, C=1 not found |
| **Clobbers** | A, X, Y, `kArg+3`..`kArg+7` |

### `dlEvict` — internal (pool eviction)

Pick + evict a resident dynamic task when the pool is full. Scans the dyn
table for the **largest** suspendable victim (skips free slots,
already-swapped, DEAD/SLEEPING, pinned `KF_NOT_EVICTABLE` tasks, and shared
reentrant code with refCount > 1), releases the victim's libraries
(`dlEvLibs`), frees its code pages (and its data region if it owns one),
tombstones + detaches a single-instance residency record, and marks it
`DYN_FLAG_SWAPPED` + `TA_SWAPPED`. A victim with live thread children is
**killed** instead — `dlEvKill`: the victim, then a `$FE`-sentinel fixpoint
over its **thread** descendants only (each victim is tested with
`taskThreadNameReuHi`, the same test `kGetTaskName` uses), then its dyn entry —
because those children share its code page and have no dyn entry of their own.
A `kDynLoad` child has both its own pages and its own dyn entry, and
`dlEvKillTask` frees neither, so it is **left running** rather than leaked —
which also matches `exit` and `kill`'s own thread-only cascade.
Returns C=0 if it freed space, C=1 if no victim — a pool-full load
then fails with error 4 (`? no space in pool`).

### `dlRestore` — internal (swap-in)

Called from `dynFree` after any free. Scans for `DYN_FLAG_SWAPPED` tasks
and re-loads **every** one whose code now fits (`reuFindFile` → header DMA
→ `dynParseHeader` → `dlLoadCore` → fixups), re-acquires its libraries
(`dlReLibs` — re-refcount and re-eager-load), then cold-restarts its
existing TCB via `initTCB_ptr` (no re-spawn: id/parent/screen/name
survive), clears the swapped flag, and re-creates a reentrant residency
record.

### `dynParseHeader` — `$44F6` (internal)

Parse a task binary header. Validates magic `"GO"` (bytes $47 $4F), then extracts all fields into `kArg`, copies the name to `(dataPtr)`, and stores the fixup count in `dlFixCountLo/Hi`.

| | |
|---|---|
| **Input** | `kPtr`/`kPtr+1` = header address |
| **Output** | C=0: `kArg`/`kArg+1` = origin, `kArg+2`/`kArg+3` = code size, `kArg+4` = flags, `kArg+5` = data size, `kArg+6` = ZP base, `kArg+7` = ZP len, `dlFixCountLo`/`dlFixCountHi` = fixup count, `dlLibMask`/`dlLibMaskHi` = the task's 16-bit `libMask`, `dlFlags` = flags copy. Name null-terminated at `(dataPtr)`. |
| | C=1: `kArg` = 1 (bad magic or bad `fixup_offset`) or 2 (not relocatable) |
| **Clobbers** | A, X, Y, `srcPtr` |

Header layout (256-byte paged header; offsets from `kPtr`):

| +0/+1 | +2 | +3/+4 | +5/+6 | +7 | +8 | +9 | +10/+11 | +12 | +13.. |
|---|---|---|---|---|---|---|---|---|---|
| Magic "GO" | Flags | Origin LE | Code size LE | Data size | ZP base | ZP len | libMask LE | Name len N | Name (N bytes), then the fixup trailer, then zero padding |

The header page is exactly 256 bytes; the code body starts at file offset 256
and is loaded to a pool page address (relocatable path).

**Fixup trailer** — at `+13+N`:

| Offset | Field |
|---|---|
| `+13+N` | fixup_count (16-bit LE) |
| `+15+N` | fixup_offset (16-bit LE) — the table's own file offset, validated by the parser as `256 + code_size` (error 1 otherwise) |
| … | zero padding to file offset 256 |

The +10/+11 field is not a size: it is the 16-bit `libMask` (see
[dynamic-libraries.md](dynamic-libraries.md)). Program RAM is a runtime-sized
`kMalloc` block requested with `KF_MALLOC_RAM`, not a fixed header region.

### Fixup Table (Tier 1 relocation)

A relocatable task binary (`flags & $01`) carries a hi-byte fixup table at file
offset `fixup_offset = 256 + code_size` (after the code body):

```
+256               code body (code_size bytes)
+256+code_size     fixup table: F × 16-bit code-body-relative offsets (LE)
+256+code_size+2F  sentinel $FFFF
```

`F` is a 16-bit count with no ceiling: the loader applies the table in
128-fixup DMA chunks under SEI, decrementing the count until zero.

At load time, for each offset `o` in the table the loader bounds-checks
`o < code_size` (else error 1) and adds `delta_hi` to `code[o]` (delta =
load_addr − origin; pools are 256-byte aligned so delta_lo is always 0).
Kernel calls (`JSR kXxx` at the fixed $E000 table), PC-relative branches,
immediates, and ZP references are position-independent and never appear in the
table.

**Generation (build time, no runtime cost):**

- `tools/assemble-tasks.asm` assembles each task at origin, origin+$100,
  and origin+$200 (`:shift=0/256/512`) into `tasks-out/temp/*.base.bin`,
  `*.shift.bin`, `*.check.bin`. Task sources set **no `.pc`** — the script
  sets it. The header ORIGIN field is a hard-coded literal and stays constant.
- `tools/gen-fixups.asm` diffs only the code body (`code_start = 256` in every
  variant): every byte where `shift[i] == base[i] + 1` is a fixup site. It then
  verifies that applying +2 at those sites reproduces `*.check.bin` and that
  every other code byte is identical, and emits `tasks-out/{name}.bin`:

  ```
  header (name + fixup_count + fixup_offset + zero padding to 256)
  + code body + fixup table + sentinel $FFFF
  ```

VS Code task **"Build dynamic tasks"** runs the four KickAssembler
invocations.

---

### `kDynLoad` — `$E08D`

Load a task binary from REU filesystem and spawn it. The 256-byte header page is DMA'd to `scratchBuf` and parsed, then the code body is streamed directly from REU to a pool page with hi-byte fixups applied (relocatable path; the post-code fixup table is applied in 128-fixup chunks). A fixed-origin (`flags=0`) binary returns error 2 — there is no fixed-origin load path. `KF_REENTRANT` binaries use name-keyed shared residency: the first load runs the full load path and creates a record (entry/size/pages/refcount keyed on the name); later loads share the resident code, skip DMA/marking, and get a fresh per-instance data buffer. The whole binary is never staged in RAM.

**Program-RAM block (`KF_MALLOC_RAM`):** a binary with `KF_MALLOC_RAM` (`$10`) requests `dlRamPages` pages (from `kArg+2`); a zero request is error 9 "pages required". The loader allocates the code pages and the program-RAM pages as **two separate `allocFromPool` blocks** (code first, then RAM anywhere it fits — a resident lib in the middle of the pool must not strand the RAM from the code), writes the block's B/N into the instance buffer after spawn, and registers it in the malloc table. `freeMallocBlocks` releases it when the owner dies. A non-reentrant binary whose name is already running is refused with error 11 "already running"; a reentrant flag with `data_size=0` is treated as a mis-flag and falls through to the relocatable path.

**Entry semantics:** the binary's `ORIGIN` field is the **header-page base** — the code was assembled at `origin + 256`; the relocatable path spawns at the allocated pool address. The `ps` command shows this code address, the task size, and a `shared` marker for resident reentrant instances.

**Task arguments:** the caller's buffer may carry an argument string
after the filename's NUL (`"name.tsk\0args\0"`). When the binary sets
`KF_TAKES_ARGS` (`$08`), `kDynLoad` copies the args (leading spaces
skipped, capped at `MAX_TASK_ARGS` = 64 bytes and `data_size` − 1 so
the terminator fits) into the new instance's data buffer at offset 0
before the task can be scheduled — race-free because the copy happens
inside the loader's SEI window. Binaries without the flag and tasks
without a data buffer are untouched. First user: the shell
(`run shell ps` spawns a second shell that executes `ps` once at
startup, then prompts).

**Pool eviction:** when the incoming task doesn't fit in the pool, `kDynLoad` evicts resident dynamic tasks to make room. **Placement:** task code / program RAM / `kMalloc` grow up from the bottom of the pool, while **libraries come down from the top** (`dlAllocHi`; `libLoad` → `dlLibCore` → `dlAllocCode` → `allocFromPoolTop`, see `allocFromPool` above) — a library can then never sit between two task blocks and strand the space. **Sufficiency tests:** the pre-evict loop stops only when the free pages are both **enough** (`free >= dlPreNeed`, a count) and **usable** (`dlProbeFit` finds a contiguous run of that size) — a page count alone cannot say, because free pages split into runs smaller than the request are free space the request cannot use, and `pool`, whose rows come from the tables rather than the bitmap, still reports them as free. **Self-eviction accounting:** sacrificing the caller is authorised only when the space left can host a run of `dlPreNeed` once the caller's pages cover the shortfall — `dlSelfEvictOk` asks `dlProbeFit` for `dlPreNeed - dlCallerPages()`. Refusing matters because the sacrifice is irreversible: the caller's code pages are freed, so a load that fails after it can never return to the caller, and the shell's own `? no space in pool` would be lost. `dlCallerPages` counts the caller's code pages **plus the libraries it is the last holder of** (`dlCallerAddLibs`/`dlCallerLibPages`), because eviction runs `dlEvLibs` and frees exactly those; under-counting them refuses loads that fit (`run basic` = 99 pages: 78 free + 19 code = 97 without the libraries, 109 with them). ⚠️ The pre-need sum counts only the **eager** libraries (`dlEagerLibPages`): a task that opens a **lazy** library at startup needs those pages on top, and nothing in the loader will notice — `basic` adds `filesys.lib` for its REU working file, so its live footprint is `99 + 10 = 109`, the whole pool. `tools/check-pool-budget.ps1` computes that sum for every task in the build, which is the only place it can be seen. It picks the **largest** suspendable task first, frees its code pages, and marks it `TA_SWAPPED` (task state `4`) — the scheduler skips it and `resume` refuses it. When the evicted task is the *calling* task itself (e.g. the shell running `run basic`), the loader reschedules instead of returning into freed code. A shared reentrant record (any refcount) is evicted **all-or-nothing**: every instance linked to it is marked swapped together, so no instance is left running freed code — `run basic` works even with several shells open. `dynFree` (exit/kill) then swaps **every** evicted task back in whose code now fits (`dlRestore`), cold-restarting each at its entry point (scrollback/program state lost — accepted). A task with live **thread children** is *killed*, not swapped: children share its code page and have no dyn entry, so a swap would leave them running freed code. Restore re-loads the binary by name, re-applies fixups at the new address, and re-creates the residency record; a swapped co-instance whose record already exists **attaches** (no code reload, refcount bump). **Restore resets instance data**: `dlRestore` re-zeroes each restored task's instance buffer, so stale state (the shell's last typed line, startup args) can never re-fire. **Display handoff**: a focus-owner exit blanks the display (transferFocusAway runs before the restore, while the victims are still swapped) — `dlRestore` hands the display back to the first restored owner-surface task (only when `kbFocus = $FF`), and `transferFocusAway` itself now also reclaims whenever `kbFocus = $FF` (any exit/kill), so a blanked display can never stick; a *live* focus holder is never stolen. The shell's restore entry prints one newline to re-park the cursor on a fresh row — the eviction froze the surface-tail cursor at the last scheduler preemption, which was mid-command (e.g. right after the typed `run basic` line, visually "right after ps").

Internal helpers (`dynParseHeader`, `allocFromPool`, `freeFromPool`, `resAddRecord`, `dlEvict`, `dlRestore`, `blitChar`) are documented in `src/kernel/dynload.inc` / `src/kernel/text-blit.inc` and are not jump-table calls.

| | |
|---|---|
| **Input** | `kPtr`/`kPtr+1` = filename (null-term screen codes; optional args string follows the NUL) |
| **Output** | C=0: task spawned and registered in `dynTaskTable` |
| | C=1: `kArg` = 0 (no free task slots), 1 (bad magic), 2 (not relocatable), 3 (address overlap), 4 (pool full), 5 (file not found), 8 (origin not page-aligned), 10 (residency table full) |
| **Clobbers** | A, X, Y, kArg block, srcPtr, kPtr, spawnPtr, taskNamePtr |
| **Interrupts** | Runs internally with SEI (protects scratchBuf); **returns with interrupts enabled on every path** (CLI before every RTS) |

Binary header format (see `dynParseHeader`):
| +0/+1 | +2 | +3/+4 | +5/+6 | +7 | +8 | +9 | +10/+11 | +12 | +13.. |
|---|---|---|---|---|---|---|---|---|---|
| Magic "GO" | Flags | Origin LE | Code size LE | Data sz | ZP base | ZP len | libMask LE | Name len N | Name + fixup trailer, zero-padded to 256 |

Header constants live in **`src/kernel/task-header.inc`**, imported by both
builds: `HDR_MAGIC` (`$4F47` — the bytes `$47 'G'` then `$4F 'O'`,
little-endian), the `KF_*` flag bits and the `LIB_*` libMask bits.

---

### REU-only font — font-help.inc (internal)

The bitmap text font lives **only** in the REU filesystem as `gordon.fnt`
(2 KB: 256 glyphs × 8 bytes, screencode order) and occupies no C64 RAM —
`$5700-$C3FF` is all pool (109 pages).

**Kernel state** (main.asm, in the 48-byte font-record block — `fontRecLo` through `taskShadowHi` — whose size is
pinned so downstream addresses stay fixed):

| Address | Size | Meaning |
|---|---|---|
| `FONT_REC_LO/MID/HI` | 3 B | Current font's 24-bit FS data-area offset (the record `fsxOpen` would produce) |
| `FONT_C2`/`FONT_C3` | 2 B | `fontGlyph` stash for `kArg+2/+3` (col/row) |
| `FONT_C6`/`FONT_C7` | 2 B | `fontGlyph` stash for `kArg+6/+7` (matrixCell) |
| `FONT_GLYPHS` | 8 B | Glyph DMA scratch |

**Flow:**

1. **Boot** — `bootFontResolve` (font-help.inc, `$5340` pocket):
   `kReuFindFile("gordon.fnt")` → verifies the size is ≥ 2048 bytes →
   stores the 3-byte offset into `FONT_REC_*`. C=1 (missing/short) halts
   the boot. No `SEI` needed: the boot task is the only task alive, so
   the record write can't be observed torn.
2. **Blitting** — `fontGlyph` (same file), called by `blitChar`,
   `blitCharSlot`, `blitGlyphSlot`: computes `reuFsPtr =
   FONT_REC_* + char*8`, `jsr reuDmaRange` (8 bytes → `FONT_GLYPHS`),
   sets `srcPtr = FONT_GLYPHS`. Contract: clobbers A, Y, `kArg..kArg+1`,
   `kArg+4/+5`, `kPtr`, `reuFsPtr`; **preserves X and `kArg+2/+3/+6/+7`**
   (callers' col/row/matrixCell survive). `gfx.lib`'s `gxChar` inlines
   the same DMA (it runs under its own `php/sei`).
3. **Font switch** — `setfont <name>`:
   `kReuFindFile("name.fnt")` → size check → the 3-byte `FONT_REC_*`
   update **inside `sei/cli`** (tasks run with IRQs on, and a torn write
   would show one garbage glyph).

**Restrictions:**

- The font must be **seeded in the REU FS** — fonts are never created at
  runtime. `tools/build-reu.ps1` seeds `gordon.fnt`, `c64uppr.fnt`,
  `c64low.fnt` and **bank-aligns** every `.fnt` (the `$noSplit` flag pads
  the file to the next 64 KB bank boundary), so a glyph never crosses a
  bank. Runtime-created files (e.g. `basicwrk`) are NOT bank-aligned —
  never treat one as a font.
- A font must be exactly **2048 bytes** (256 glyphs); `setfont`/boot
  reject anything shorter (a longer file would simply ignore the tail).
- **Performance:** every printed glyph costs one 8-byte REU DMA
  (~+80–100 cycles vs. a RAM read). Full-screen scroll (~960
  cells) is the worst case. The REU serializes with the scheduler's
  per-tick ZP/stack DMA and BASIC's per-byte REU file I/O — all
  SEI-windowed, so correctness is unaffected, only latency.
- A missing/corrupt `gordon.fnt` at boot halts the boot.

### `blitChar` — text-blit.inc (internal)

Bitmap-text glyph blitter. Draws glyph A (screencode) into the hires framebuffer cell at (X=col, Y=row): cell address = `$2000 + (row*40+col)*8` (char-cell interleaved layout — 8 contiguous bytes per cell). The font is REU-only: `fontGlyph` (font-help.inc, `$5340` pocket) DMA's the glyph from the REU FS (`fontRecLo/Mid/Hi` record at `$19D7`, set by the boot task's `bootFontResolve`) into the 8-byte `FONT_GLYPHS` scratch.

| | |
|---|---|
| **Input** | A = char (screencode), X = col (0-39), Y = row (0-24) |
| **Output** | X preserved |
| **Clobbers** | A, Y, kArg..kArg+3, srcPtr, kPtr |

`printChar` (kPrintChar's body) is the all-bitmap blitter: `blitChar`
(displayed surface → framebuffer) / `blitCharSlot` (background surface →
REU slot), matrix color-nibble write, cursor advance + wrap. The
framebuffer-vs-slot decision keys on the **surface**, not keyboard focus:
task T renders to the framebuffer iff
`resolve(T) == resolve(kbFocus)` and `kbFocus != $FF`, where
`resolve(t) = (screenOwner[t] == $FF) ? t : screenOwner[t]` (computed by
the internal `surfDisplayed` helper in `screen-io.inc`, which keeps
`resolve(kbFocus)` in its own kernel-data byte — never in the `kArg` block:
the scheduler calls it from the timer IRQ on every context switch, and
`sysExit` calls it while a parked task's `kArg` is live).

The fixed-position UI blitters `kBlitChar` / `kBlitCharRev`
(`scroll-region.inc`) share the same blink-safety rule as
`kPrintCharAt`: before either blitter draws over the cursor's saved cell,
it restores the saved glyph and matrix nibble at the saved cursor
position, so a later blink OFF phase cannot resurrect stale pixels or a
phantom block. This hardens status-bar and HUD-style redraws. It does
not replace task-level modal discipline: a task that temporarily stops
editing and repurposes part of the screen for a modal prompt should still
disable its cursor for that modal state and re-enable it on return.

Flag bits: `$01` `KF_RELOCATABLE`, `$02` `KF_NEEDS_SCREEN`, `$04`
`KF_REENTRANT` (name-keyed shared residency), `$08`
`KF_TAKES_ARGS` (loader copies args into the instance buffer at spawn),
`$10` `KF_MALLOC_RAM`, `$20` `KF_RE_RUNNABLE`, `$40` `KF_NOT_EVICTABLE`.
`$80` `DYN_FLAG_SWAPPED` is a dyn-table bit rather than a header flag: the
code was evicted from the pool.

---

### `kSyscall` — `$E090`

Stable jump-table entry for the syscall dispatcher. Dynamic tasks call this to yield, spawn, kill, etc. without hardcoding the kernel-internal `syscall` address.

| | |
|---|---|
| **Input** | A = syscall number (0=exit, 1=spawn, 3=yield, etc.) |
| **Clobbers** | Depends on syscall; see [`syscall.md`](syscall.md) |

```asm
    lda #3          ; yield
    jsr kSyscall
```

---

### `kDynFree` — `$E093`

Free a dynamic task's table entry and any bitmap pages it reserved.
Idempotent for statically-compiled tasks: if the task ID is not in
`dynTaskTable`, it returns C=1 and changes nothing.

| | |
|---|---|
| **Input** | A = GordonOS task ID |
| **Output** | C=0: entry freed (or task was static — nothing to free); C=1: not found |
| **Clobbers** | A, X, Y, kArg+3..kArg+7 |
| **Interrupts** | Caller must hold SEI (the `sysExit`/`sysKill` call paths already run SEI'd) |

```asm
    lda curTask      ; or the killed task's ID
    jsr kDynFree
```

Single-instance path only: if `dynTaskPageCount[slot] > 0`, the reserved
pages are returned to their pool; then the slot is cleared
(`dynTaskId = $FF`, origin/size/pageCount zeroed, residency = $FF) and
`dynTaskCount` is decremented. A reentrant instance takes the shared-code
path instead: it decrements its record's refcount, and the **last** instance
frees the shared code pages and the record.

Auto-invoked on task death: `sysExit` frees `curTask`; `sysKill` frees the
killed task (`kArg`), then reloads X before comparing to `curTask`.

---

### `kMalloc` — `$E0AE` / `kFree` — `$E0B1`

Page-granular pool allocation (page size configurable via `pool.inc`,
currently 256B). `kMalloc` reserves `A` contiguous pool pages and returns
the page-aligned block address in `kPtr`; `kFree` returns the block at
`kPtr` to the pool. Blocks are owned by the calling task and freed
automatically on exit/kill; on eviction a block is DMA'd to the per-dyn-slot
REU shadow (banks 252-255, 32 KB/slot) and restored on swap-in.

> **No sub-page allocation — not offered and not planned.** A pooled allocation
> is always a whole number of pages. The relocatable binary format depends on it:
> a page-aligned origin keeps the low byte of every in-image address constant, so
> a relocation is one high-byte delta per fixup. Sub-page blocks would also break
> the page→byte math (`poolAsl`/`poolLsr`), the per-task page accounting and the
> eviction shadow, which is sized `MALLOC_SHADOW_BYTES / (2 × POOL_PAGE_SIZE)` pages.

**A full pool does not mean failure: `kMalloc` evicts one resident task and
retries.** `kmEvictAlloc` (`$E201`, living in the reserved-but-unused 16-byte
`hexChars` block, so it costs no free space) calls `dlEvict` with
`dlNoSelfEvict = 1`, so **the caller is never the victim**: it is executing its
own code, and freeing that mid-call is a crash rather than a graceful failure.
C=1 therefore means "no victim could be found either". ⚠️ The eviction can swap
the victim out *or kill it* (`dlEvKill`, when it has live thread children), and
it clobbers `kArg..kArg+7` — hold no kernel state across a `kMalloc`.

| | `kMalloc` | `kFree` |
|---|---|---|
| **Input** | A = page count (1..`MAX_MALLOC_PAGES`) | `kPtr` = block addr |
| **Output** | C=0, `kPtr` = block addr; C=1 no space | C=0 freed; C=1 not found |
| **Clobbers** | A, X, Y, kPtr, kArg..kArg+7 | A, X, Y, kArg+4..kArg+7 |

```asm
    lda #16             ; 16 pages × 256B = 4 KB
    jsr kMalloc          ; kPtr = block address (C=0 ok)
    bcs noRoom
    ...
    jsr kFree            ; kPtr still holds the block address
```

⚠️ **A block's page count is recorded from `allocFromPool`'s `kArg+4` echo**, not
from a register — `allocFromPool` clobbers X. `kFree` and `freeMallocBlocks` free
exactly that many pages, so a wrong count either strands pages in the bitmap
(too small) or clears another owner's pages (too large), and the second kind is a
JAM. A count must come from the echo, never from a register.

---

### `kCsrBoth` — `$E096`

Set cursor visibility and synchronise the surface matrix tail in one call.
`A` = 0 disables the cursor, non-zero enables it. This is the low-level
primitive shared by `kEnableCursor`/`kDisableCursor`; it is exposed so a
caller can snapshot the previous state with `ldx cursorOn` and restore it
after direct screen writes. Used by EhBASIC's `vecOut` to erase the cursor
block artifact before writing.

| | |
|---|---|
| **Input** | A = new `cursorOn` value (0 = off, non-zero = on) |
| **Output** | — |
| **Clobbers** | A, Y, kPtr |
| **Modifies** | `cursorOn`, surface matrix tail (`+$23EA`/`$07EA`) |

```asm
    ldx cursorOn            ; snapshot current state
    lda #0
    jsr kCsrBoth            ; disable cursor + sync tail
    ; ... direct screen draw ...
    txa                     ; restore prior state
    jsr kCsrBoth
```

---

> Bitmap surfaces are peers to text screens within the task model.
>
> ⚠️ **Eager lib calls** — the drawing primitives (`kPlot`/`kLine`/`kBox`/
> `kFillBox`/`kCircle`/`kEllipse`/`kFloodFill`/`kGetPixel`/`kClearBitmap`/
> `kSetGfxColor`/`kGfxChar`/`kGfxString`/`kFillMatrix`) live in `gfx.lib`
> (lib 2, 13 entries), loaded eagerly at spawn (declare `libMask` bit 2) and
> reached through their `$E000` jump entries, which `libLoad` patches in place
> to the library routine. `kSetGfxMode`/`kFillColorRam` stay resident, and the
> surface calls `kAllocBitmap`/`kFreeBitmap` are names for `kAllocScreen`/
> `kFreeScreen` (see below). See
> [dynamic-libraries.md](dynamic-libraries.md).

### `kAllocBitmap`

Alias: `kAllocScreen` — `.const kAllocBitmap = kAllocScreen` in
`jumptable.inc`. The all-bitmap model means every surface *is* a bitmap, so both
names reach one routine and the name costs no jump-table slot.

Allocate a 28-slot bitmap surface. Sets `screenKind[curTask]` to `BMPMODE_STD` (2) or `BMPMODE_MC` (3).

| Input | Description |
|---|---|
| A | Mode: 0=standard hires, 1=multicolor |
| `kArg` | Border color (`$D020`) |
| `kArg+1` | Background 0 (`$D021`) |
| `kArg+2` | Background 1 (`$D022`) — stored but not read in bitmap modes |
| `kArg+3` | Background 2 (`$D023`) — stored but not read in bitmap modes |

| Output | Description |
|---|---|
| C=0 | Success — `screenAlloc=1`, `screenOwner=$FF`, REU slot assigned |
| C=1 | Failure — no free slot, or **A ≥ 2** (the mode is 0 or 1 only) |

A task that already owns a surface does **not** get a second one: the call
returns C=0 and keeps the preserved surface (slot, `screenKind` and content
unchanged), refreshing only the colours from `kArg`. The mode argument is
ignored on that path.

Clobbers: A, X, Y, kPtr, kArg, kResult.

### `kFreeBitmap`

Alias: `kFreeScreen` — `.const kFreeBitmap = kFreeScreen` in `jumptable.inc`, so
the name costs no jump-table slot.

Free the current task's bitmap slot. Resets `screenKind=0`, `screenAlloc=0`. No-op if not a bitmap task. Clobbers: A, X, Y, kArg, kResult.

### `kClearBitmap` — `$E0DB`

Fill the bitmap's pixels + video matrix via REU DMA. Pixels are filled with the byte in A (`$00`=clear, `$FF`=all pixels set); the 1 KB video matrix (and the 1 KB MC color RAM region, if applicable) are cleared to `$00`. If the caller's surface is displayed — the *surface*, not keyboard focus — the framebuffer is filled so the clear is visible immediately; otherwise the REU slot is filled. The cursor tail is preserved. Clobbers: A, X, Y, kArg, kResult, kPtr.
### `kPlot` — `$E0C3`

Plot a single pixel. If the caller's surface is displayed — the *surface*, not keyboard focus — the pixel lands in the framebuffer; otherwise it lands in the caller's REU slot via RMW DMA.

| Input | Description |
|---|---|
| X | Column low byte (0-255) |
| Y | Row (0-199) |
| C | Column high bit (CLC for 0-255, SEC for 256-319 with X=col-256) |
| A | Hires: 0 = clear pixel, non-zero = set pixel. MC: 0-3 = 2-bit pixel value. Does not write the matrix. |

Clobbers: A, X, Y, kPtr, kArg.

### `kLine` `$E0C6` / `kBox` `$E0C9` / `kFillBox` `$E0CC`

Bresenham line / rectangle outline / filled rectangle. Arguments in `kArg`
(`kLine`: x1 lo/hi, y1, x2 lo/hi, y2; `kBox`/`kFillBox`: x lo/hi, y, w lo/hi,
h), color in A (hires: 0=clear, ≠0=set; MC: 0-3 = 2-bit value). Pixels go to the
framebuffer when the surface is displayed and to the REU slot otherwise.
**Caveat:** these
routines hold SEI for the whole loop — a background `kFillBox` blocks the
scheduler for the DMA duration (2 DMAs per pixel). Clobbers: A, X, Y, kPtr,
kArg.

### `kCircle` `$E0CF`

Midpoint circle with 8-way symmetry (hires). Off-screen pixels are clipped.

| Input | Description |
|---|---|
| A | Color (0=clear, 1-15=set pixel bit) |
| `kArg`/`kArg+1` | Centre X (lo/hi) |
| `kArg+2` | Centre Y (0-199) |
| `kArg+3` | Radius R (0-255) |

- Pixels go to the framebuffer when the caller's surface is displayed, else
to its REU slot (RMW DMA) — same as `kLine`. Uses a 16-bit decision term so
all radii 0-255 are exact; `R=0` plots the single centre pixel.
- Writes the **pixel bit only** (no matrix nibble) — pre-fill the matrix as
`gfxdemo` does.
- Holds SEI for the whole loop; clobbers A, X, Y, kPtr, kArg block.

```asm
lda #160; sta kArg       // CX lo
lda #0;   sta kArg+1     // CX hi
lda #100; sta kArg+2     // CY
lda #50;  sta kArg+3     // R
lda #1                   // colour
jsr kCircle
```

### `kEllipse` `$E0D2`

Midpoint ellipse with 4-way symmetry (hires). Off-screen pixels are clipped.

| Input | Description |
|---|---|
| A | Color (0=clear, 1-15=set pixel bit) |
| `kArg`/`kArg+1` | Centre X (lo/hi) |
| `kArg+2` | Centre Y (0-199) |
| `kArg+3` | Horizontal radius RX (0-255) |
| `kArg+4` | Vertical radius RY (0-255) |

- 32-bit decision terms — exact for all radii 0-255. `ry=0` draws a
  horizontal line; `rx=0` draws a vertical line.
- Writes the **pixel bit only** (no matrix nibble) — pre-fill the matrix.
- Holds SEI for the whole loop; clobbers A, X, Y, kPtr, kArg block.

```asm
lda #160; sta kArg       // CX lo
lda #0;   sta kArg+1     // CX hi
lda #100; sta kArg+2     // CY
lda #160; sta kArg+3     // RX
lda #100; sta kArg+4     // RY
lda #1                   // colour
jsr kEllipse
```

### `kFloodFill` `$E0D5`

Scanline flood fill (hires). Fills the contiguous region whose pixels
match the seed pixel's bit, replacing them with the fill bit.

| Input | Description |
|---|---|
| A | Fill color (0=clear bit, nonzero=set bit) |
| `kArg`/`kArg+1` | Seed X (lo/hi) |
| `kArg+2` | Seed Y (0-199) |

- Boundary = pixels of the opposite bit value; fills `clear→set` or
  `set→clear` (erase) depending on the seed.
- 768 B span-seed stack (X lo, X hi, Y) in kernel data (`$190D-$1C15`);
  bounded at 255 entries (drops seeds if full — pathological comb shapes
  may under-fill).
- Writes the **pixel bit only** (no matrix nibble) — pre-fill the matrix.
- Holds SEI for the whole fill; clobbers A, X, Y, kPtr, kArg block.

```asm
lda #160; sta kArg       // seed X lo
lda #0;   sta kArg+1     // seed X hi
lda #105; sta kArg+2     // seed Y
lda #1                   // fill colour
jsr kFloodFill
```

### `kGetPixel` `$E0D8`

Read a pixel's value (hires). For collision detection / readback.

| Input | Description |
|---|---|
| X | Column low byte (0-255) |
| Y | Row (0-199) |
| Carry | Column high byte (0 = col 0-255, 1 = col 256-319) |

- Output: A = 0 (pixel clear) or non-zero (pixel set — the bit mask).
  Carry = 0 if valid, 1 if no surface / off-screen (A = 0 then).
- Holds SEI; clobbers A, X, Y, kPtr, kArg block (REU path).

```asm
ldx #160               // column lo
ldy #105               // row
clc                    // column < 256
jsr kGetPixel          // A = 0 (clear) or non-zero (set)
```

### `kSetGfxColor` — `$E0DE`

Set a per-task VIC colour register, or the pixel write op.

| Input | Description |
|---|---|
| X | Selector: 0 = border `$D020`, 1 = background 0 `$D021`, 2 = `$D022`, 3 = `$D023`, 4 = the pixel write op |
| A | Colour (0-15), or the op value for selector 4 |

- Writes the calling task's `taskGfxBorder`/`Bg0`/`Bg1`/`Bg2` entry
  (applied by `doGfxSwitch` on view switch). When `curTask == kbFocus` the
  hardware register is also written immediately.
- `X=2`/`X=3` require `screenKind[curTask] == BMPMODE_MC`; in std mode they
  are no-ops. `X >= 5` is rejected (no-op): there is no such VIC register, and
  the per-task offset `selector*24` would leave the four-array colour block.
- **Selector 4 is not a VIC register** — it is the pixel write op (`gfxOp`,
  `$ED5D`): `A=0` sets or clears on the colour, non-zero XORs the pixel. Every
  entry that writes pixels honours it — `kPlot`, `kLine`, `kBox`, `kFillBox`,
  `kCircle`, `kEllipse` — so a shape drawn twice with the op set comes off the
  picture again. It is **kernel** state, not per-task, and the scheduler clears it
  on every context switch, so set it, make the drawing call, then clear it.
- **In MC the XOR is on the pixel's 2-bit value, and the value the call carries is
  what is XORed into it** (`v xor k`). The second pass restores `v` exactly, so a
  preview, a caret and a delete are pixel-exact there as well; what the first pass
  *shows* is the cell's colour for `v xor k` — the pen's colour over background
  (`0 xor k = k`, as in hires), another of the cell's sources over drawn work, and
  nothing at all where `v xor k` is 0 or two palette entries share a colour. A call
  with `A = 0` therefore toggles nothing in MC, where the hires writer toggles
  regardless of the colour.
- Only `$D020` (border) and `$D021` (background 0) are read by the VIC in
  bitmap modes. `$D022`/`$D023` are written but never read (they belong to
  extended-colour mode, which GordonOS does not use). The multicolor pixel
  palette is `$D021` (value 0), the matrix nibbles (values 1/2) and colour
  RAM (value 3) — see `kFillMatrix` and `kFillColorRam`.
- Clobbers A, X, Y, kPtr.

```asm
lda #7                // yellow
ldx #0                // border
jsr kSetGfxColor      // border ← yellow now (if focused)
```

### `kGfxChar` — `$E0E1`

Draw an 8×8 font glyph with its top-left corner at pixel (x, y), plotting
only the glyph's set pixels (transparent background — OR, never clears).
Hires: 8×8 in the set-pixel colour. MC: 8 wide × 16 tall (height doubled to
match the double-width MC pixels) in a 2-bit colour.

| Input | Description |
|---|---|
| X | Char (screen code) |
| A | Colour (hires 1-15, MC 0-3) |
| `kArg`/`kArg+1` | X pixel coordinate (lo/hi) |
| `kArg+2` | Y pixel coordinate |

Off-screen pixels clip (hires x < 320, MC x < 160, y < 200). Reads the
REU-only font (glyph DMA'd via `fontGlyph`; `fontRec*` set by `setfont`).
Clobbers A, X, Y, kPtr, kArg block.

```asm
lda #0; sta kArg       // x lo
lda #0; sta kArg+1     // x hi
lda #50; sta kArg+2    // y
lda #1                 // colour
ldx #'A'               // screen code
jsr kGfxChar
```

### `kGfxString` — `$E0E4`

Print a null-terminated screen-coded string, each char at an 8-pixel
horizontal pitch, via `kGfxChar` (same transparent/OR + hires/MC rules).

| Input | Description |
|---|---|
| A | Colour (hires 1-15, MC 0-3) |
| `kArg`/`kArg+1` | X pixel coordinate (lo/hi) |
| `kArg+2` | Y pixel coordinate |
| `kPtr` | Null-terminated screen-coded string |

Clobbers A, X, Y, kPtr, kArg block.

```asm
    lda #<msg; sta kPtr
    lda #>msg; sta kPtr+1
    lda #0; sta kArg; sta kArg+1
    lda #0; sta kArg+2
    lda #2                 // colour
    jsr kGfxString
...
msg: .text "HELLO"; .byte 0
```

### `kFillMatrix` — `$E10A`

Fill all 1000 video-matrix slots (`$0400`) with the raw byte in A. For MC
bitmap the byte packs both nibbles — `(value-1 colour << 4) | value-2 colour`;
the VIC reads the high nibble for pixel value 1 and the low nibble for value
2. Displayed surface → framebuffer matrix; background → REU slot `+$2000`.
Clobbers A, X, Y, kPtr, kArg.

### `kSetGfxMode` — `$E10D`

Switch the current task's surface between hires and multicolor in place,
preserving the surface (pixels, matrix, colour RAM) and the per-task colours.

| Input | Description |
|---|---|
| A | 0 = hires (`BMPMODE_STD`), 1 = multicolor (`BMPMODE_MC`) |

- Sets `screenKind[curTask]` and, if the surface is displayed, updates
  `$D016` bit 4 and re-applies `$D020`-`$D023` from the preserved per-task
  colours. Colours are NOT reset by the switch.
- Output: C=0 success; C=1 no surface or bad mode. Clobbers A, X, Y.

### `kFillColorRam` — `$E110`

Fill all 1000 colour-RAM slots (`$D800`) with a colour. Colour RAM is 4-bit:
the VIC reads the LOW nibble — the MC bitmap pixel-value-3 colour. Pass the
raw colour (0-15) in A (do not shift). Displayed surface → `$D800-$DBE7`;
background → REU slot `+$2400`. Clobbers A, X, Y, kPtr, kArg.

See **[lib-gfx.md](lib-gfx.md)** for the full per-call graphics reference.

---

## Sprites

Sprites are **slot-based**: eight fixed 64-byte blocks in VIC bank 0 hold the
pixels — the hardware maximum; the art itself lives in the REU FS and a task
loads one frame at a time. **All eight are ordinary task sprites:**
`SPRITE_TASK_SLOTS = 8` and the calls reject only slot 8+ (out of range). No slot
is reserved for anything: a task that wants a mouse pointer drives a sprite like
any other.

What is *not* per task is the hardware: one register set, eight art slots, and
five control bytes that are each a bitmask over all eight sprites. So the kernel
runs the register set as a **swapped resource** — exactly one task's sprite state
is live at a time, the task whose surface is **displayed**, and everything a task
has to say about its sprites travels with the display. See *Per-task state and
the display hand-over* below.

| Slot | Address |
|---|---|
| 0-4 | `$02C0 $0300 $0340 $0380 $03C0` — sprite N reads slot N |
| 5-7 | `$0F00 $0F40 $0F80` — the same, from the high band |

⚠️ **The slots live in TWO bands, and no other address can hold them.**
`$02A1-$03FF` is the low band (below the video matrix at `$0400`) and
`$0F00-$0FBF` is the high band.
In between, **nothing** in VIC bank 0 can hold sprite data: the **character ROM
is mirrored at `$1000-$1FFF`** and the VIC reads ROM there for *every* fetch
type — sprite data included (measured: the same 64B pattern renders
correctly from `$02C0` and as font bytes from `$17C0`) — and `$2000-$3FFF` is the
framebuffer. `$0FC0` is deliberately **not** a slot: eight is the ceiling, so it
stays free as relocation slack.

**Every channel has a slot, so the `$D015` publish needs no enable-mask term.**
`sprOn(%11111111)` enables all eight, and `SPR_ENABLE_MASK` survives only
as `$FF` — a tripwire constant, asserted in `main.asm`, so that a future slot-count
change cannot silently start masking a channel again. The only term the publish
carries is the install gate, `sprPubMask` (below). Note that masks are the
**caller's** property — the shadow is a sink, and nothing reads it back.

✅ **Deadline guard — a sprite cannot be torn by a late commit.**
The raster commit runs at raster line 0, so a long `SEI` burst defers it; if it
published a new X after the beam had reached the sprite, the sprite would show
**two positions at once** for that frame. So `rasterCommit` does the opposite: if
it finds the raster already past
`SPR_COMMIT_DEADLINE` (line 30 — the last line at which a sprite at the earliest
usable Y=31 is still entirely ahead of the beam), it commits **nothing**. The
sprite holds its previous position for that one frame.

So the artifact is a **one-frame hold**, not a split, and only a burst that both
exceeds the commit's ~1,180-cycle margin *and* comes from the display owner can
cause it: another task's burst delays the commit, but what gets published is
still the display owner's state. The real cases are a task's own
`kClearScreen`, big REU transfer or FS read, while its sprites are on screen.
**A sprite that sits in the top border (Y < 31) is still exposed** — the deadline
is a fixed line, not a per-sprite scan.

**The cheapest mitigation is still task-side:** if you are about to hold `SEI`
across a long burst, do `sprOn(0)`, wait **≥2 ticks** (33.8 ms at 59.2 Hz, longer
than one frame, so a commit definitely lands), *then* burst, then re-enable.
Nothing enabled ⇒ nothing to tear ⇒ not even the held frame.

**A "sheet" is a plain file of consecutive 64-byte frames** — frame N is at
file offset `N*64`, exactly like the REU font's `glyph = fontRec + char*8`.
There is no header, no index and no cache: a slot holds one frame and is
overwritten on demand, so there is nothing to evict and no state kept between
frames. Resolve a sheet once per sprite; load a frame per animation step.

A frame is the 64-byte block the VIC fetches from a slot: **21 rows × 3 bytes =
63 bytes of pixels, plus one pad byte** (`$00`) that is never fetched and exists
only to keep every frame on a 64-byte boundary. A hires row is 24 one-bit pixels
with the leftmost in bit 7; an MC row is 12 two-bit pixels with the leftmost in
bits 7-6 (`00` transparent, `01` `$D025`, `10` `$D027`+n, `11` `$D026`). Both
packings are 504 bits, so the same sheet displays either way. Full layout and the
ASCII-art front end (`tools/gen-sprites.py` → `assets/sprites/*.spr`):
[programmers-guide.md](programmers-guide.md) → *Sprites*.

### Per-task state and the display hand-over

**One task's sprite state is live in kernel RAM, and it is the task whose
surface is displayed.** Everything a task says about its sprites is
71 bytes — `SPR_BLK_LEN`:

| Field | Size | What it is |
|---|---|---|
| `spriteSheetLo/Mid/Hi[8]` | 24B | the sheet record per sprite: the 24-bit FS offset of frame 0. `Hi = 0` = unresolved, which is safe because bank 0 is never an FS data bank |
| `sprShReg` … `sprShMc1` | 39B | the **shadow** (below) |
| `sprFrameIdx[8]` | 8B | the frame each sprite is showing |

The same 71 bytes exist **per task slot** in the REU, at
`REU_SPR_BASE + slot × 128` (`REU_SPR_BASE = $C400`, bank 0 — page-aligned, 24
blocks of 128B, `$C400-$CFFF`), in the live order, so a hand-over is one DMA in
each direction plus one per frame:

- `sprInstall` (`$52DC`) compares `kbFocus` with `sprLiveOwner` (the installed
  slot, `$FF` = none) and, when they differ, saves the live state into the old
  owner's block, loads the new owner's, re-DMAs every frame its sheet records
  name (`sprRestoreFrames` → `sprFrameDma`, `$1CC0`), sets `sprPubMask` and drops
  the collision latches. It is idempotent and costs a compare and an `rts` when
  nothing has changed.
- **It is called from two places, and both are needed.** The scheduler's
  restore path (`switchTask`/`reschedule` — so the timer tick, and every
  yield/sleep/exit/kill) covers a display change made inside an interrupt, an
  F-key switch, and the display owner dying; the
  **library** calls it at the top of every setter, so a write can never land in
  the *previous* owner's live state. The scheduler is also the only place where
  its `kPtr`/`kArg` clobber is free — the ZP is saved just above and reloaded
  just below — which is why it is called there and not earlier in the tick.
- **A task that regains the display comes back to what it left**: its art (the
  `sprFrameIdx` records are what the frame re-DMA uses), its positions, its
  colours and its control bytes. Nothing has to be re-asserted, and no sprites
  are "lost" by losing the display.
- **`sprPubMask` is the publish gate.** The commit ANDs it into the `$D015`
  write; `sprInstall` sets it to `$FF` for a valid owner and `$00` when there is
  none (`kbFocus = $FF`, a blanked display), so a surviving live state can never
  be published where it does not belong.
- **A recycled slot starts clean.** `clearSlotSprite` (`sprite.inc`, called from
  `scSetAlive` — the spawn path) zeroes the new task's block, and if that slot is
  the *installed* one it also forgets `sprLiveOwner` and unpublishes, so the
  stale live state cannot be written back over the fill. This is the sprite
  counterpart of `clearSlotShadows` for the ZP window.
- **A reboot forgets everything.** `warmBootReset` calls `warmSpriteReset`
  (`$529E`), which unpublishes, sets `sprLiveOwner = $FF` and fills the whole
  block region with zeros — and **`init.inc` calls it at cold boot too**, because
  VICE writes the REU image back: the blocks in it survive into the next session
  and the **boot task** is the one slot that never goes through the spawn path.

Because the state is saved per task and only the displayed one is installed,
**two tasks can drive sprites at once** — they are never live simultaneously, so
they cannot corrupt each other. There is no allocation, no handle, and nothing to
run out of.

### The calls — `$CDDE-$DEC`

Four of the five are **`sprite.lib`'s call entries** (eager, lib 7, declared as
`libMask` bit 7 = `$0080`); `libLoad` rewrites each in place, so the addresses
below are fixed ABI while the code behind them lives in the pool.

| Entry | Address | Role |
|---|---|---|
| `kSpriteSheet` | `$CDDE` | bind an FS file as a sprite's animation sheet |
| `kSpriteFrame` | `$CDE1` | DMA one frame into the sprite's slot (and record the index) |
| `kSpritePos` | `$CDE4` | place a sprite: X = sprite, A = x low, Y = y, C = x high bit |
| `kSpriteCollide` | `$CDE7` | **resident** — the frame-latched collision masks, then clear |
| `kSpriteReg` | `$CDEA` | any single-byte shadow field (A = value, X = offset) |

The full per-call reference — inputs, clobbers, the focus rule, the sheet and
frame contracts, collision semantics and the macros in
`src/tasks/sprite-shadow.inc` — is **[lib-sprite.md](lib-sprite.md)**. What
belongs here is the kernel side: the state above, the shadow below, and the
commit.

### Sprite data (`$CFA4-$CFFF`, 92B)

The per-task region comes first and is contiguous, in the saved block's own
order; the kernel-only bytes follow.

| Symbol | Size | Purpose |
|---|---|---|
| `spriteSheetLo/Mid/Hi[8]` | 24B | per-sprite 24-bit FS offset of frame 0 (`Hi = 0` = unresolved) |
| `sprShReg` … `sprShMc1` | 39B | the **shadow** — a RAM copy of every sprite setting (below) |
| `sprFrameIdx[8]` | 8B | the frame each sprite shows — what the hand-over re-DMAs |
| `spriteSlotLo/Hi[8]` | 16B | sprite index → 64-byte-aligned slot address |
| `sprLiveOwner` | 1B | the slot whose state is live (`$FF` = none) |
| `sprPubMask` | 1B | `$FF` = publish the live shadow, `$00` = publish nothing |
| `sprCollSs` / `sprCollBg` | 2B | the collision latch |
| `sprFrameCount` | 1B | **`frameCount`** to tasks (`$CFFF`) — the per-frame clock |
| `sprPtrBytes[8]` | 8B | slot address ÷ 64 — the VIC sprite data pointer bytes (`$CDED`) |

`main.asm` asserts that `SPR_BLK_LEN` equals the first three fields' span, so the
saved copy and the live copy cannot drift apart.

### Animating smoothly — one update per FRAME, not per tick

The scheduler ticks at **59.2 Hz** and the display samples at **50.1 Hz**, so a
task that moves a sprite on every tick gets **1.18 updates per frame**: some
frames show two steps and the next shows none. That reads as a stutter however
good the speed arithmetic is — and it is the reason per-tick animation never
quite looks right, even with a frame-locked commit (the commit decides *when* a
position is published, not how often you compute one).

`frameCount` is the display's own clock: `rasterCommit` increments it at raster
line 0, before the deadline guard, so it ticks once per frame even when a commit
skips. It is published to tasks in `src/tasks/kernel-data.inc`. Update when it
**changes**:

```asm
    lda frameCount          ; 8-bit and it WRAPS — compare for change, never
    cmp lastFrame           ; for a number of frames elapsed
    beq noStep
    sta lastFrame
    ; ... integrate, bounce, place ...
noStep:
    lda #SYS_YIELD
    jsr syscall             ; keep yielding: gating on the counter is not a
                            ; licence to spin on $D012 (Rule 13)
```

This fixes *sampling unevenness*. It does not by itself make motion smooth: a
sub-pixel speed still needs a fractional accumulator, or a slow sprite will move
in visible 1 px jumps. The two together — fractional position,
sampled once per frame — are what "smooth" means here.

### Frame commit — `rasterCommit` (internal, `$567D`)

There is no public call for this: `irqHandler` runs it once per frame, in the
vertical blank, when the VIC raster flag is set.

- **The VIC raster compare is line 0** (`$D012 = 0`, `$D01A = $01`), enabled at
  the end of `init.inc`. Line 0 is in vblank on PAL *and* NTSC and precedes the
  earliest line a sprite can be visible (PAL `Y = 31`, NTSC ≈ `Y = 20`), so the
  whole sprite register set changes between frames and a task's update is never
  half-applied. **⚠️ `$D012` is kernel-owned from here on** — writing it moves
  this interrupt.
- **The shadow is the interface.** It is a plain RAM copy of the live state's
  sprite settings (39B — see the table below). Tasks write the shadow through the
  library; `rasterCommit` is the **only** writer of `$D000-$D02E`. That is what
  makes every setter a plain store with no timing rule, at the price of up to one
  frame of latency.
- **It publishes the display owner's state, gated by `sprPubMask`.** The state
  *is* the display owner's (that is what the hand-over maintains) and the mask is
  `$00` only when there is no display owner at all, so a surviving state can
  never appear on someone else's screen. The commit itself does not compare task
  ids at all — that decision was made by `sprInstall` before the frame.

| Shadow | Size | Commits to |
|---|---|---|
| `sprShReg` — interleaved `X0,Y0,X1,Y1,…,X7,Y7` | 16B | `$D000-$D00F`, one contiguous copy |
| `sprShXHi` — per-sprite X high bit | 8B | assembled into `$D010` (see below) |
| `sprShColour` | 8B | `$D027-$D02E` |
| `sprShEnable` | 1B | `$D015`, ANDed with `sprPubMask` — the one masked publish |
| `sprShYExp` / `sprShXExp` | 2B | `$D017` / `$D01D` |
| `sprShPriority` / `sprShMc` | 2B | `$D01B` / `$D01C` |
| `sprShMc0` / `sprShMc1` | 2B | `$D025` / `$D026` |

  The order is the published ABI for `kSpriteReg`, so it is part of the
  interface; the task-side copy is `src/tasks/sprite-shadow.inc` and `main.asm`
  asserts the two agree. `$D010` is deliberately **not** a mirror byte: it is
  assembled each frame from the eight `sprShXHi` flags using the existing
  `bitMasks` table, which is what lets `kSpritePos` stay a plain store and keeps
  bit juggling off the per-frame, per-sprite path.

  ⚠️ **Those flags are persistent state — the commit must READ them, never shift
  them in place.** `lsr sprShXHi,x` is a read-modify-write on *memory*: it zeroes
  the flag and takes bit 0 into the carry, so the commit would consume the value
  it had just published. A sprite at x ≥ 256 then loses its `$D010` bit on the
  next frame and is drawn at `x - 256` until the task happens to call
  `kSpritePos` again — invisible in any mode whose x stays below 256, because
  there every flag is 0 and destroying it is a no-op. The flag byte is 0 or 1
  (`kSpritePos` stores the plain carry), so `ldy`/`beq` is the exact test and
  costs the same 5 bytes as `lsr`/`bcc`.

  The 17-byte mirror must stay contiguous (mirroring `$D000` interleaved is what
  makes the commit one loop rather than 8 unrolled register pairs) and
  `sprShColour` must stay contiguous for its copy loop. `main.asm` asserts that
  neither straddles a page.
- **It also writes `$07F8-$07FF`**, the VIC sprite data pointers: that page sits
  inside the per-surface matrix `$0400-$07FF`, which `surfLoad` DMAs on every
  view switch, so the pointers are re-applied every frame instead of being hooked
  into `gfx.inc` — which also self-heals them after any surface DMA.
- **Collisions are latched, not shadowed.** `$D01E`/`$D01F` are read-only and
  *reading clears them*, so the service is their only reader: it ORs them into
  `sprCollSs`/`sprCollBg`, which a task reads and clears via `kSpriteCollide`.
  A task cannot steal another task's evidence by reading early, and a
  task polling every Nth frame still sees every collision. The latch is dropped
  whenever the display changes hands, so a new owner cannot read the last one's.
- **Hard rules:** no `CLI`, no kernel calls, no kernel ZP / `kArg` /
  `kPtr` / `srcPtr`, no REU use. The commit runs with `I = 1` and can preempt any
  task or kernel code, including the dynamic loader's `CLI` windows.
- Cost: ~425 cycles/frame (≈2.2% of a frame), 126B of code.

### Sprite priority — `sprShPriority` (`$D01B`)

One bit per sprite: **0 = in front** of the graphics, **1 = behind the
foreground graphics** (still in front of background pixels). It is an ordinary
shadow byte, so it is set through `kSpriteReg` — `sprPriority(%00000100)` puts
sprite 2 behind — and `rasterCommit` publishes it with
`lda sprShPriority / sta $d01b` on every frame.

```text
background graphics  <  sprite (bit=1)  <  foreground graphics  <  sprite (bit=0)  <  border
```

"Foreground" is any bitmap pixel that is not background colour `$D021`
(multicolour bitmap: `01`/`10`/`11` are foreground, `00` is background).

- **Drawing order only.** Collision detection is unaffected — a sprite behind
  the graphics still sets `$D01F`, and `$D01E` still reports sprite-sprite
  contact (§3.8.2 of the VIC-II article).
- **Sprite-to-sprite order stays rigid**: sprite 0 highest priority … sprite 7
  lowest, regardless of the mask.
- The byte is a bitmask over **all eight slots**, and the shadow is a sink, never
  a query — a task that toggles one sprite's bit keeps its own copy. A task sets
  it after it takes the display, and a new task starts with every bit clear (all
  sprites in front) because its block is zeroed.

### Collision semantics

`kSpriteCollide` is the only reader of `$D01E`/`$D01F` (see *Frame commit*
above); the masks are the previous frame's, sampled at a fixed point, and
**OR-accumulated**, so polling every Nth frame still reports every collision.

- **`$D01E` does not identify the pair** — bit *i* means "sprite *i* touched
  someone". Testing `maskA & maskB` is a heuristic, exact only with two sprites
  enabled. Transparency does not collide; priority does not affect detection;
  a disabled sprite cannot collide.
- **The hardware test is per-pixel, not a bounding box.** Detection happens when
  two sprite data sequencers output a non-transparent pixel in the same pixel
  position (VIC-II article §3.8.2), so a shaped sprite collides where it is
  *drawn*, not where its 24x21 rectangle is — a ball's empty corners do not
  collide. Two consequences: the test is exact against the art actually in the
  slot (not against a task's logical coordinates), and it is **not limited to
  the display window** — the sequencers keep producing output in the border, so
  sprite-sprite collisions are reported there too. Sprite-background is
  different: it needs the graphics sequencer to emit a foreground pixel, and that
  output is suppressed in the upper/lower border, so `$D01F` cannot fire there.

### The shadow ABI

**Only the task whose surface is DISPLAYED may write the shadow.** Every entry
opens with the guard `curTask == kbFocus` and returns `C=1` having written
nothing otherwise — and each calls `sprInstall` first, so the state it is about
to write is its own. The focus rule is *policy*, not a limitation: it is what
makes "the live shadow is the displayed task's" an invariant rather than a
convention.

- **There is nothing to re-assert.** Losing the display hides your sprites —
  what is not installed is not published — but the state is saved with your slot
  and re-installed when you get the display back, art included. No claims, no
  `sprShadowInit`, no `? sprites busy`.
- **A DEAD owner leaves nothing behind.** Its block is zeroed when the slot is
  reused (`clearSlotSprite`), and if it was the installed slot the install is
  invalidated at the same moment, so a successor wearing the recycled id has
  nothing to inherit. Task ids *are* recycled (`findFreeSlot` takes the lowest
  DEAD slot) — which is exactly why the state travels by slot and is zeroed on
  reuse rather than by an id compare.
- Offsets live in `src/tasks/sprite-shadow.inc`; the kernel-side layout is the
  data block in `src/kernel/sprite.inc`, pinned by `main.asm` asserts.

---

## Best Practices

### Do

- **Check carry** after `kAllocScreen`, `kShareScreen`, `kTakeScreenOwnership` — they fail if no screen is available.
- **Share screens** for overlay tasks (clock, status bars) — avoids consuming a virtual screen slot.
- **Use `kTakeScreenOwnership`** when a parent allocates a screen for a child task. It cleans the parent's slot so it can be reused.
- **Call `kDisableCursor`** on non-interactive screens — prevents cursor blink artifacts.
- **Pair `kLockScreen` with `kUnlockScreen`** — failing to unlock freezes any task that tries to acquire the screen.
- **Use `kSetScrollRegion`** for a fixed header/status bar — narrow the region and draw the fixed rows with `kPrintCharAt`.
- **Use semaphores for shared resources** — `semWait`/`semSignal` (syscalls 10/11) let tasks coordinate without freezing the scheduler.

### Don't

- **Don't read `curTask` ($FD) without `SEI`/`CLI`** — the IRQ handler changes it asynchronously. All kernel calls that use `curTask` are already protected.
- **Don't assume slot numbers** — tasks can be at any slot. Use `kShareScreen` with `kGetTaskName` lookup, or pass the slot explicitly.
- **Don't assume `taskParent[me]` owns the screen** — it is the task that *spawned* you. That is the surface owner for a `.com` (the shell) but not for a task loaded by another task; share with the first ancestor that actually owns a surface.
- **Don't write to screen RAM directly** — use `kAllocScreen` or `kShareScreen` so the scheduler tracks your screen.
- **Don't call `kFreeScreen` on a shared screen if you're not the owner** — it only detaches you. Only `screenOwner=$FF` tasks actually free the buffer.
- **Don't write `$D000-$D02E` or `$D012`** — the sprite registers belong to `rasterCommit` (write the shadow instead), and `$D012` is the sprite raster interrupt's compare line. Writing either corrupts the frame service or moves the interrupt.

| Call | A | X | Y | kPtr | srcPtr | Notes |
|---|---|---|---|---|---|---|
| `kClearScreen` | ✗ | ✗ | ✗ | ✗ | — | |
| `kPrintChar` | ✗ | ✗ | ✗ | ✗ | ⚠️ | X=old cursorOn; scrolls region if row > bottom |
| `kPrintString` | ✗ | ✗ | ✗ | ✗† | ⚠️ | X via printChar; scrolls region if row > bottom |
| `kSetCursor` | ✓ | ✓ | ✓ | — | — | **Only call that preserves all regs** |
| `kGetCursor` | ✓ | ←col | ←row | — | — | X,Y are outputs |
| `kNewline` | ✗ | ✗ | ✗ | ⚠️ | ⚠️ | Scrolls region if at bottom row |
| `kScrollScreen` | ✗ | ✗ | ✗ | ✗ | ✗ | Scrolls the surface's region (displayed or background) |
| `kEnableCursor` | ✗ | ✗ | ✗ | ✓ | — | Sets `cursorOn` + syncs the matrix tail immediately (framebuffer or slot) |
| `kDisableCursor` | ✗ | ✗ | ✗ | ✓ | — | Same as `kEnableCursor` |
| `kScanKeyboard` | ✗ | ✗ | ✗ | — | — | Returns `$FF` if empty |
| `kReadKey` | ✗ | ✗ | ✗ | — | — | Returns `0` if empty/release |
| `kWaitKey` | ✗ | ✗ | ✗ | — | — | Blocks until keypress |
| `kReadString` | ✗ | ✗ | ✗ | ✗† | — | kPtr advanced past terminator; Y=length |
| `kSkipSpaces` | ✗ | ✓ | ✓ | ✓ | — | kPtr advanced past spaces; A=char (0 if end); C=1 if end of string |
| `kStrlen` | ✗ | ✓ | ✗ | — | — | Length → A |
| `kStrcpy` | ✗ | ✓ | ✗ | — | — | Pointers NOT advanced |
| `kStrcmp` | ✗ | ✓ | ✗ | ⚠️ | ⚠️ | `kArg`=mode (0=exact,1=wildcard); Z=1 equal/match; wildcard mode also clobbers `kPtr`/`srcPtr` |
| `kByteToHex` | ✗ | ✗ | ✗ | — | — | 2 chars at (kPtr) |
| `kByteToDec` | ✗ | ✗ | ✗ | — | — | Y = digit count; NOT null-terminated |
| `kMul16` | ✗ | ✗ | ✓ | — | — | kArg × kArg+2 → kResult |
| `kDiv16` | ✗ | ✗ | ✗ | — | — | kArg ÷ kArg+2 → kResult |
| `kHexDigit` | ✗ | ✓ | ✓ | — | — | Screen code → nibble (0-15); C=1 if not hex |
| `kNibbleToHex` | ✗ | ✓ | ✓ | — | — | Nibble (0-15) → screen code |
| `kRandom` | ✗ | ✓ | ✓ | — | — | Random byte → A |
| `kGetTime` | ✗ | ✓ | ✓ | — | — | BCD → kArg[0..3] |
| `kSetTime` | ✗ | ✓ | ✓ | — | — | BCD ← kArg[0..3] |
| `kPrintTime` | ✗ | ✗ | ✗ | ✗ | ✗ | X=col,Y=row → blit at (X,Y); displayed surface only |
| `kLockScreen` | ✗ | ✗ | ✓ | — | — | Saves kPtr/kArg to per-task arrays |
| `kUnlockScreen` | ✗ | ✗ | ✓ | ✗ | — | Restores kPtr/kArg from per-task arrays |
| `kGetTaskName` | ✗ | ✓ | ✓ | ✗ | — | X=index → kPtr = name ptr |
| `kAllocScreen` | ✗ | ✗ | ✗ | ✗ | — | A=mode, allocates REU surface slot; SEI/CLI |
| `kFreeScreen` | ✗ | ✗ | ✗ | — | — | Frees curTask's screen; SEI/CLI |
| `kSetScrollRegion` | ✗ | ✗ | ✗ | ✗ | — | A=top, X=bottom; C=1 invalid (region unchanged); SEI/CLI; clobbers kArg..+6 |
| `kGetScrollRegion` | ✗ | ✗ | ✓ | — | — | A=top, X=bottom (outputs); C=0; Y preserved |
| `kSwitchView` | ✗ | ✓ | ✗ | ⚠️ | — | X preserved (input); kPtr if private screen |
| `kViewScreen` | ✗ | ✓ | ✗ | — | — | X preserved (input); display only, kbFocus unchanged |
| `kShareScreen` | ✗ | ✓ | ✗ | — | — | X=target, C=1 if none; SEI/CLI |
| `kTakeScreenOwnership` | ✗ | ✓ | ✗ | — | — | X=source, C=1 if none; SEI/CLI |
| `kSetTextColor` | ✗ | ✓ | ✗ | ✗ | — | X preserved; writes `taskTextColor` |
| `kSetCursorColor` | ✗ | ✓ | ✗ | ✗ | — | X preserved; writes `taskCursorColor` |
| `semWait` | ✗ | ✓ | ✓ | — | — | X=sem index, yields if unavailable |
| `semSignal` | ✗ | ✓ | ✓ | — | — | X=sem index |
| `kReuToC64` | ✗ | ✓ | ✓ | ✓ | — | php/plp; kPtr read-only; X and Y preserved |
| `kReuFromC64` | ✗ | ✓ | ✓ | ✓ | — | php/plp; kPtr read-only; X and Y preserved |
| `kReuFillC64` | ✗ | ✓ | ✓ | ✓ | — | php/plp; kPtr read-only |
| `kReuFillReu` | ✗ | ✓ | ✓ | ✓ | — | php/plp; A=fill byte; kPtr preserved |
| `kReuFormat` | ✗ | ✗ | ✗ | — | — | Formats REU filesystem; uses SEI/CLI |
| `kReuDirEntry` | ✗ | ✗ | ✗ | ✗ | — | Returns entry name in kPtr buffer; uses SEI/CLI |
| `kReuSave` | ✗ | ✗ | ✗ | ✗ | — | Saves C64 block to REU; uses SEI/CLI |
| `kReuLoad` | ✗ | ✗ | ✗ | ✗ | — | Loads file from REU to C64; atomic find→dma via `reuLoadAtomic` (php/sei…plp, preserves caller I + C) |
| `kReuDelete` | ✗ | ✗ | ✗ | — | — | Marks file deleted; uses SEI/CLI |
| `kReuRename` | ✗ | ✗ | ✗ | — | — | Renames entry (name field only); whole scan+modify atomic (php/sei…plp) |
| `kDynLoad` | ✗ | ✗ | ✗ | ✗ | ✗ | Loads + spawns task from REU FS; C=0/1 with error in `kArg`; SEI, returns CLI'd |
| `kSyscall` | ✗ | ✗ | ✗ | ✗ | — | Syscall dispatcher; clobbers vary — see [`syscall.md`](syscall.md) |
| `kDynFree` | ✗ | ✗ | ✗ | — | — | Frees dynamic task pages + table slot; caller must hold SEI |
| `kCsrBoth` | ✗ | ✗ | ✗ | ✓ | — | A = `cursorOn` value + immediate tail sync (SEI/CLI, 1-byte REU DMA when background) |
| `kGetCursorOn` | ✗ | ✓ | ✓ | — | — | A = `cursorOn`; X/Y preserved |
| `kBlinkReset` | ✗ | ✗ | ✗ | ✓ | — | Erase the live blink block at its SAVED position + fresh ON; SEI'd; also clobbers `kArg+7` |
| `kSetCharShadow` | ✗ | ✗ | ✗ | — | — | A = 1/0 enable/disable for `curTask`; clobbers `kArg..kArg+3`; C=0 always |
| `kCharAt` | ✗ | ✗ | — | — | — | A=col, Y=row → A=screen code; C=1+A=$20 if no surface/shadow; Y preserved |
| `kReadRow` | ✗ | ✗ | ✗ | — | — | A=row, `kPtr`=40B dest → row of screen codes; C=1+spaces if no surface/shadow; `kPtr` preserved |
| `kPrintCharAt` | ✗ | ✗ | ✗ | ✗ | ✗ | A=char, X=col, Y=row → cell + matrix nibble + shadow mirror; routes on the task's surface (framebuffer or its own REU slot); no cursor advance/scroll |
| `kPrintGlyph` | ✗ | ✗ | ✗ | ✗ | ✗ | `kPtr`=8-byte glyph → cell at cursor, advances + colour; shadow = space; like `kPrintChar` |
| `kPrintGlyphAt` | ✗ | ✗ | ✗ | ✗ | ✓ | `srcPtr`=8-byte glyph, X=col, Y=row → cell + matrix nibble + shadow mirror; **fixed cell** (no cursor move, no advance, no scroll), so `(39,24)` is safe |
| `kBlitChar` | ✗ | ✗ | ✗ | ✗ | ✗ | A=char, X=col, Y=row → font glyph + `(textColour<<4)\|bg0`; no shadow, no cursor advance (displayed only) |
| `kBlitCharRev` | ✗ | ✗ | ✗ | ✗ | ✗ | A=char, X=col, Y=row → reverse video `(bg0<<4)\|textColour`; no shadow, no cursor advance |
| `kSpriteSheet` | ✗ | ✗ | ✗ | ✓ | ✗ | A=slot, `kPtr`=FS filename → C=1 rejected; SEI'd; ≈1,000-3,000 cycles — **resolve once per sprite, never per frame** |
| `kSpriteFrame` | ✗ | ✗ | ✗ | ✗ | ✓ | A=slot, X=frame → C=1 rejected; SEI'd; computes `sheet[slot] + frame*64` and DMAs 64B to the slot |
| `kPlot` | ✗ | ✗ | ✗ | ✗ | — | Displayed surface → framebuffer; background → REU slot (RMW DMA); SEI/CLI |
| `kLine` | ✗ | ✗ | ✗ | ✗ | — | Per-pixel via `kliPixel`; SEI held for the whole loop |
| `kBox` | ✗ | ✗ | ✗ | ✗ | — | Same as `kLine` |
| `kFillBox` | ✗ | ✗ | ✗ | ✗ | — | Same as `kLine` |
| `kClearBitmap` | ✗ | ✗ | ✗ | ✗ | — | A=fill byte; displayed → framebuffer, background → slot |

> **✗** = clobbered | **✓** = preserved | **⚠️** = conditionally clobbered | **†** = advanced past terminator
