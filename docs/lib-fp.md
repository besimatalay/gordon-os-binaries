# `fp.lib` — Library Reference

The EhBASIC floating-point core as a shared library: 40-bit floats,
26 opcodes through a single dispatcher. This is the reference for writing
tasks that compute with `fp.lib` (see `fpdemo` for a complete consumer).

| | |
|---|---|
| Lib ID | 3 |
| Entries | 1 (`fpExec` dispatcher) |
| Load policy | **eager** — declare `libMask` bit 3 (value `$0008`) in your task header |
| Call entry | `kFpCall = $E113` (jump table, patched to `fpExec`) |
| Source | `src/libs/fp.asm`, opcodes in `src/libs/fp.inc` |
| Error contract | C = 1 + A = error code (see below) |

## Calling

`fpExec` is a single-entry opcode dispatcher:

```asm
fpCall:                 // local label in your task
    jmp kFpCall

    ...
    lda #FP_SIN         // opcode in A
    jsr fpCall          // C=0 result in fac1, C=1 + A = error
```

> Pick a unique label — task binaries share one global KickAssembler
> namespace, and `basic.asm` already defines `fpGo`.

- **Dispatch preserves Y** (it is the argument carrier for `BYTEF`).
  A and X are stashed into the lib's ZP window on entry (needed by
  `AYFC`), so they are clobbered by every call.
- Every opcode returns through a trampoline with **C = 0**. Error exits
  pop the trampoline and return **C = 1, A = error code** directly to
  your `jsr`.
- **Stack footprint:** trampoline (4 bytes) + the handlers' internal
  `jsr` levels ≈ 14–18 bytes — fine on a normal task stack.
- No SEI/CLI, no kernel state touched: all mutable state lives in the
  **ZP window `$90`–`$C5`** (54 bytes).

## ZP window requirement (important)

The lib keeps `fac1`/`fac2` and scratch **only** in ZP `$90`–`$C5`. Your
task must include this range in its declared ZP region (header
`zp_base`/`zp_len`) so the scheduler's ZP DMA preserves FP state across
preemption:

```asm
.const MY_ZP     = $02
.const MY_ZPLEN  = $C4        // covers $02..$C5: task state + fp window
:fpZpDeclared(MY_ZP, MY_ZPLEN) // build-time assert from fp.inc
```

## Float format

- **Registers:** 5-byte floats in ZP — `fac1` at `$AC`–`$B0`
  (exponent, mantissa 1, 2, 3, sign byte) and `fac2` at `$B3`–`$B7`.
  Only `fac1` is a result; `fac2` is the LEFT operand of binary ops.
- **External storage** (`FLOAD`/`FSTORE`, BASIC variables): 4 bytes
  `exp, m1, m2, m3`; the sign is bit 7 of `m1`.

$$value = \left(0.5 + \frac{m1}{256} + \frac{m2}{65536} + \frac{m3}{2^{24}}\right) \times 2^{\,exp-\$80}$$

Handy constants: `1.0 = $81 $00 $00 $00`, `0.5 = $80 $00 $00 $00`,
`10.0 = $84 $20 $00 $00`, `99.5 = $87 $47 $00 $00`,
`π/160 = $7B $20 $D9 $7C`.

## Opcodes

Binary-op convention (EhBASIC evaluator): **`fac2` = LEFT, `fac1` =
RIGHT, result → `fac1`.**

| Opcode | Value | Operation | Notes |
|---|---|---|---|
| `FP_ADD` | `$00` | `fac1 = fac2 + fac1` | |
| `FP_SUB` | `$01` | `fac1 = fac2 − fac1` | |
| `FP_MUL` | `$02` | `fac1 = fac2 × fac1` | |
| `FP_DIV` | `$03` | `fac1 = fac2 ÷ fac1` | ÷0 → error 0 |
| `FP_POW` | `$04` | `fac1 = fac2 ^ fac1` | base = fac2, exponent = fac1 |
| `FP_NEG` | `$05` | `fac1 = −fac1` | |
| `FP_ABS` | `$06` | `fac1 = \|fac1\|` | |
| `FP_INT` | `$07` | `fac1 = trunc(fac1)` | toward zero |
| `FP_SGN` | `$08` | `fac1 = sign(fac1)` | −1 / 0 / +1 |
| `FP_SQR` | `$09` | `fac1 = √fac1` | fac1 < 0 → error 2 |
| `FP_EXP` | `$0A` | `fac1 = e^fac1` | overflow → error 1 |
| `FP_LOG` | `$0B` | `fac1 = ln(fac1)` | fac1 ≤ 0 → error 2 |
| `FP_SIN` | `$0C` | `fac1 = sin(fac1)` | radians |
| `FP_COS` | `$0D` | `fac1 = cos(fac1)` | radians |
| `FP_TAN` | `$0E` | `fac1 = tan(fac1)` | radians |
| `FP_ATN` | `$0F` | `fac1 = atan(fac1)` | radians |
| `FP_RND` | `$10` | `fac1 = random in [0,1)` | fac1 = 0 → next in sequence; fac1 ≠ 0 → **seed** from fac1 first, then next |
| `FP_CMP` | `$11` | compare | `A = $01` fac1 > fac2, `$FF` fac1 < fac2, `$00` equal. **Mutates `fac2_1`** (sign merge) — re-`FLOAD` fac2 before reuse |
| `FP_F2FX` | `$12` | fac1 → 16-bit integer | returns **A = high byte, Y = low byte** (also stored at window `$90`/`$91`); truncates toward zero; \|fac1\| ≥ 2^24 → error 3 |
| `FP_AYFC` | `$13` | unsigned int → fac1 | **X = high byte, Y = low byte** (set them before the call) |
| `FP_MUL10` | `$14` | `fac1 = fac1 × 10` | |
| `FP_DIV10` | `$15` | `fac1 = fac1 ÷ 10` | |
| `FP_FLOAD` | `$16` | 4-byte float at `(kPtr)` → **fac2** | the only fac2 filler |
| `FP_FSTORE` | `$17` | fac1 → 4 bytes at `(kPtr)` | rounds + merges sign into `m1` |
| `FP_PI` | `$18` | `fac1 = π` | |
| `FP_BYTEF` | `$19` | byte → fac1 | **Y = byte** before the call |

## Error codes (C = 1, value in A)

| A | Meaning | Raised by |
|---|---|---|
| 0 | divide by zero | `FP_DIV`, `FP_POW` |
| 1 | overflow | `FP_EXP`, `FP_POW`, multiply/divide overflow |
| 2 | illegal argument | `FP_SQR`(<0), `FP_LOG`(≤0), `FP_POW` range |
| 3 | conversion range | `FP_F2FX` with \|fac1\| ≥ 2^24 |
| 4 | unimplemented opcode | only for A ≥ 26 (all 26 opcodes exist) |

## Register contract (summary)

- **Clobbered:** A, X on every call; Y on almost every handler (only the
  dispatch itself preserves Y, for `BYTEF`'s argument).
- **Read, not clobbered:** `kPtr` (`$F5/$F6`) by `FLOAD`/`FSTORE`;
  the pointer value survives.
- **No other kernel state is touched** — no `kArg` use, no SEI/CLI, no
  self-modifying code.

## Examples

Load a constant and compute `y = c − c·sin(θ)` (`fpdemo` style):

```asm
// fac1 already holds theta
    lda #FP_SIN
    jsr fpGo                // fac1 = sin(theta)
    lda #<fpCen             // constant 99.5 = $87 $47 $00 $00
    sta kPtr
    lda #>fpCen
    sta kPtr+1
    lda #FP_FLOAD
    jsr fpGo                // fac2 = c
    lda #FP_MUL
    jsr fpGo                // fac1 = c*sin
    lda #<fpCen
    sta kPtr
    lda #>fpCen
    sta kPtr+1
    lda #FP_FLOAD
    jsr fpGo                // fac2 = c
    lda #FP_SUB
    jsr fpGo                // fac1 = c - c*sin
    lda #FP_F2FX
    jsr fpGo                // A = hi, Y = lo  (0..199)
```

Integer into `fac1`:

```asm
    ldx #$01                // 260
    ldy #$04
    lda #FP_AYFC
    jsr fpGo                // fac1 = 260
```

`fac2` only takes `FLOAD` — to copy a constant into `fac1` use the
copy trick: `FLOAD` the constant (→ fac2), `AYFC` 0,0 (→ fac1 = 0),
`FADD` (→ fac1 = constant).

See [`dynamic-libraries.md`](dynamic-libraries.md) for the loader side
and [`fpdemo.asm`](../src/tasks/dynamic/fpdemo.asm) for a full consumer.
