# Gordon Basic

> **Gordon Basic v1.5** — the built-in BASIC interpreter for GordonOS.

Gordon Basic is a full floating-point Microsoft BASIC 2.0-compatible
interpreter that runs as a **task** on GordonOS. It is loaded on demand
from the REU filesystem with `run basic` and runs on its own
screen with case-preserving input, RUN/STOP-to-break, and C64
screen-editor-style line editing. Programs live in a persistent REU-backed
working file (`basicwrk`) — reused if present, created if absent, and
deleted when BASIC exits normally.

## Provenance

Gordon Basic is **derived from EhBASIC v2.22p5** by Lee Davison
(© 2001–2016), with GordonOS I/O and screen integration plus a small set
of command changes. See [`NOTICE`](../NOTICE) for the full attribution and
license terms.

> EhBASIC is free but not copyright free. For non-commercial use there is
> only one restriction: any derivative work must include the string
> "Derived from EhBASIC" in any distributed binary image. For commercial
> use, contact Lee Davison.

## Differences from stock EhBASIC

This reference is based on the
[EhBASIC language reference](http://retro.hansotten.nl/6502-sbc/lee-davison-web-site/enhanced-6502-basic/ehbasic-language-reference/),
with the following changes:

**Removed** (hardware/OS-specific or unsafe features not applicable on
GordonOS):

- `irq`, `nmi`, `retirq`, `retnmi`, `on irq`, `on nmi`, `off`, `null` —
  interrupt-handler plumbing. GordonOS owns all interrupts; BASIC never
  touches them. (`on <expr> goto|gosub` is kept — see `on`.)
- `usr(<expr>)` — user-routine call vector.
- `bitclr`, `bitset`, `bittst` — bit-manipulation commands/function.
- `twopi` — the constant `2*pi`.

**Added** (GordonOS integration):

- `dir` — list the REU filesystem.
- `exit` — leave BASIC and return to the shell.
- A full **bitmap graphics** command set: `mode`, `pen0`–`pen3`, `cls`,
  `plot`, `line`, `box`, `fillbox`, `circle`, `ellipse`, `flood`,
  `gchar`, `gtext`, `printat`, `locate`, `colour`, `border`, `scroll`,
  `scrollby`, `shadow`, `gdef`, `glyph`, `setfont`, and the
  `getpixel()` function — documented in [Graphics](#graphics).

**Changed:**

- `save` / `load` — stock EhBASIC left these as no-op vectors. Gordon Basic
  implements them against the REU filesystem (see below).

Everything else is the same as EhBASIC: numbers, strings, variables,
operators, functions, and the error model.

---

# Language Reference

## Numbers

Numbers may range from zero to ±1.70141173×10^38 with an accuracy of just
under 1 part in 1.68×10^7.

Numbers can be preceded by a sign, `+` or `-`, and are written as a string
of numeric digits with or without a decimal point and an optional positive
or negative exponent, e.g.

```
-14296.3     0.25     -136.42E-3     -1.3E71
```

Integer numbers (no fraction or exponent) can also be written in
**hexadecimal** with a `$` prefix or **binary** with a `%` prefix, e.g.

```
%101010     -$FFE0     $A0127B     D-%10011001
```

## Strings

Strings are any string of printable characters enclosed in a pair of
quotation marks. Non-printing characters can be produced with `chr$()`.

```
"Hello world"     "-136.42E-3"     "+---+---+"     "Y"
```

## Variables

Both numeric and string variables are available. String variables are
distinguished by the `$` suffix. Arrays of either type are available,
indexed with bracketed indices after the name.

- Only the first **two** characters of a variable name are significant
  (`BL` and `BLANK` are the same variable).
- The first character must be `A`–`Z` or `a`–`z`; following characters may
  also include digits.
- Variable names are **case sensitive**: `AB`, `Ab`, `aB`, `ab` are four
  different variables.
- Variable names may not contain BASIC keywords (keywords are
  recognised in lower case).

## Keywords

Here is the complete list of Gordon Basic keywords. They are entered in
**lower case** — unshifted with the default lower/upper font — as shown
below. Spaces may not be included in them
(`go to` is not `goto`).

```
abs   and   asc   atn   bin$  call  chr$  clear cont  cos
data  dec   deek  def   dim   dir   do    doke  end   eor
exit  exp   fn    for   fre   get   gosub goto  hex$  if
inc   input int   lcase$ left$ len  let   list  load  log
loop  max   mid$  min   new   next  not   on    or    peek
pi    poke  pos   print read  rem   restore return right$ rnd
run   sadd  save  sgn   sin   spc  sqr   step  stop  str$
swap  tab  tan   then  to    ucase$ until val  varptr wait
while width
border box   circle cls   colour cursor ellipse fillbox flood
gchar  gdef  getpixel glyph gtext line locate mode pen0 pen1
pen2   pen3  plot  printat scroll scrollby setfont shadow
+  -  *  /  ^  <<  >>  <  <=  =  >=  >  <>
```

### Notation

- lower case — part of the command/function structure, must be present.
- `<angle bracketed>` — supplied by the user.
- `[bracketed]` — optional.
- `{a|b}` — multi-choice, one of the items.
- `…` — may be repeated any number of times.

| Placeholder | Meaning |
|---|---|
| `var` / `var$` / `var()` / `var$()` | variable / string variable / array / string array |
| `expression` / `expression$` | numeric / string expression |
| `addr` | integer ±16777215, wrapped to 0–65535 |
| `b` | byte value 0–255 |
| `n` | integer 0–63999 |
| `w` | integer −32768…32767 |
| `i` | positive integer |
| `r` | real number |

---

## Commands

### `end`

Terminates program execution and returns to direct mode. `end` may be
placed anywhere in a program — it does not have to be on the last line, and
there may be any number of them. `cont` can resume execution after an
`end`.

### `for <var> = <expression> to <expression> [step expression]` … `next [var[,var]…]`

Assigns a loop counter and optionally sets the start value, end value and
step size. If `step` is omitted, the step size defaults to +1. `next`
increments/decrements the loop variable and checks the terminating
condition.

### `data [{r|$}[,{r|$}]…]`

Defines a constant or series of constants for `read`. Real constants are
held as strings and can be read as either numeric or string values. String
constants may contain spaces; if they must contain commas, enclose them in
quotes.

### `input ["$";] <var>[,var]…`

Reads a value, or list of values, from the input stream. A `?` prompt is
always output, after the optional prompt string. If more values are
required than were entered, `??` is output until enough have been given.

### `dim <var[$](i1[,i2[,in]…])>[,var[$](…)]…`

Dimensions arrays of string or numeric variables. Arrays may have one or
more dimensions; the lower bound is always zero and the upper bound is `i`.
An array not explicitly dimensioned is created on first access with an
upper bound of 10 per dimension.

### `read <var>[,var]…`

Reads values from `data` statements and assigns them to variables.

### `let <var> = <expression>`

Assigns the value of `<expression>` to `var`. The `let` word is optional —
`var = expression` is identical.

### `dec <var>[,var]…`

Decrements each listed variable by one. `dec A` is much faster than
`A=A-1`.

### `inc <var>[,var]…`

Increments each listed variable by one. `inc A` is much faster than
`A=A+1`.

### `goto <n>`

Continues execution at line `n`. If `n` does not exist, an "undefined
statement" error is generated.

### `run [n]`

Loads and runs the program. If `n` is given, execution starts at line `n`.

### `if <expression> then {<statement(s)>|n|goto n|gosub n}` [`else …`]

Evaluates `<expression>`. If non-zero the `then` branch is taken;
otherwise execution continues with the `else` branch (if present) or the
next line.

### `restore [n]`

Resets the `data` pointer, to the start of the program or to the beginning
of line `n`.

### `gosub <n>` … `return`

Calls a subroutine at line `n`. On `return`, execution resumes at the
statement after the `gosub`.

### `rem`

Everything following `rem` on the line is ignored, even colons.

### `stop`

Halts execution and prints `break in line n`.

### `on <expression> goto <n>[,n]…` / `on <expression> gosub <n>[,n]…`

Uses the integer value of `<expression>` (0–255) to select the nth line
number after `goto`/`gosub`. Values outside 0–255 cause a "function call"
error.

### `wait <addr,b1>[,b2]`

Waits until `(peek(addr) eor b2) and b1` is non-zero. `b2` defaults to 0.

### `load "<name>"`

Imports a previously saved `.bas` program from the REU filesystem into the
current working file and warm-starts BASIC. See *Filesystem commands* below.

### `save "<name>"`

Exports the current working-file program to the REU filesystem. See
*Filesystem commands* below.

### `def fn <name>(<var>) = <statement>`

Defines `<statement>` as a function. `<name>` is any numeric variable
name; `<var>` is a simple variable used as the (local) argument.

### `poke <addr,b>`

Writes byte `b` to address `addr`. `doke <addr,w>` writes a word (low byte
at `addr`, high byte at `addr+1`).

### `call <addr>`

Calls a user subroutine at `addr`. No values are passed or returned.

### `do … loop [until <expression>|while <expression>]`

Loops. `do` marks the top and `loop` the bottom; the terminating condition
(`until` or `while`) may be at either end.

### `print [expression|$] [;|,] …`

Evaluates expressions and prints the results. `;` suppresses the
separator, `,` advances to the next tab stop. A trailing `;` or `,`
suppresses the newline. `print` alone prints a blank line. `?` is a
shorthand for `print`.

### `cont`

Continues execution after CTRL-C, a `stop`, or a null `input`.

### `list [n1][-n2]`

Lists the program. With `n1`, listing starts at (or after) line `n1`; with
`-n2` it stops at (or before) line `n2`.

### `clear`

Erases all variables and functions and resets `for`/`gosub`/`do` state.

### `new`

Deletes the current program and all variables.

### `width {b1|,b2|b1,b2}`

Sets the terminal width (`b1`, 16–255 or 0 for infinite) and tab spacing
(`b2`).

### `get <var[$]>`

Reads one key, if any, without halting. If no key is waiting, `var` is set
to 0 and `var$` to `""`.

### `swap <var1>,<var2>`

Exchanges the values of two variables (of the same type).

### `exit`

**GordonOS extension.** Ends the BASIC task: frees its screen and returns
control to the shell. Equivalent to typing `exit` in the shell.

### `dir`

**GordonOS extension.** Lists the REU filesystem — one entry per line,
name padded to 11 columns followed by the size in right-aligned decimal
bytes.

### `tab(<expression>)` / `spc(<expression>)`

Valid only within a `print`: `tab` positions the cursor at column
`<expression>`; `spc` prints that many spaces.

### `not`, `step`, `then`, `to`, `else`, `until`, `while`, `fn`

Structural keywords — see the commands they belong to (`for`, `if`, `do …
loop`, `def`).

---

## Filesystem commands (`dir`, `save`, `load`)

`save` and `load` exchange programs between BASIC's current REU working file
and normal GordonOS filesystem entries with a `.bas` extension.

```
save "prog"      ← exports the current program as prog.bas
load "prog"      ← imports prog.bas and warm-starts (prints ready)
dir              ← lists the filesystem
```

**Filename rules:**

- The name is 1–7 characters, with no `.` — the `.bas` extension is
  appended for you.
- Letters are case-sensitive (`"Prog"` and `"prog"` are different files).
- `save` errors: `? bad name`, `? exists` (duplicate), `? no space`,
  `? dir full`.
- `load` errors: `? bad name`, `? not found`.
- `save ""` and names with a `.` or more than 7 characters print
  `? bad name`.

Files persist across reboots; you can also see and manage them from the
shell with `dir`, `del`, `save`, and `load`.

---

## Graphics

Gordon Basic adds a bitmap-graphics command set that draws straight into
the task's screen. Every surface is a 320×200 bitmap; the commands below
select the drawing mode, set the palette, or draw primitives.

### Graphics modes

`mode n` selects the pixel mode. Colours are preserved across the switch.

| Mode | Resolution | Bits/pixel | Pixel value |
|---|---|---|---|
| `mode 0` (hires) | 320 × 200 | 1 | 0 = clear, 1 = set |
| `mode 1` (multicolor) | 160 × 200 | 2 | 0–3 |

### Colour model

Every 8×8 cell has a matrix byte at `$0400`; its two 4-bit nibbles plus
`$D021` and colour RAM (`$D800`) provide the palette:

| Pixel value | Source | Set by |
|---|---|---|
| `0` | `$D021` (background 0) — multicolor only | `pen0` |
| `1` | video-matrix **high** nibble | `pen1` |
| `2` | video-matrix **low** nibble | `pen2` |
| `3` | colour RAM (`$D800`) — multicolor only | `pen3` |

- **Hires** uses only the matrix nibbles: a set pixel (`1`) shows the high
  nibble, a clear pixel (`0`) shows the low nibble.
- **Multicolor** uses all four sources; the 2-bit value written by the
  drawing commands picks one of the four.

So `pen0`…`pen3` set the colours of pixel values `0`…`3`, and the drawing
commands take that value as their final `c` argument.

### Palette commands

- `pen0 c` — colour of MC pixel value `0` (`$D021`). No effect in hires.
- `pen1 c` — colour of value `1` (matrix high nibble). In hires this is the
  foreground (set-pixel) colour.
- `pen2 c` — colour of value `2` (matrix low nibble). In hires this is the
  background (clear-pixel) colour.
- `pen3 c` — colour of value `3` (colour RAM). No effect in hires.
- `colour c` — set the text colour (also used by `cls` when refilling the
  matrix). Does not repaint the whole screen; `pen1` does.
- `border c` — set the border colour (`$D020`).

### Drawing commands

Coordinates: `x` is 0–319 in hires and 0–159 in multicolor; `y` is 0–199
in both. The final `c` argument is the colour: in hires `0` clears and any
non-zero value sets (the pixel then shows `pen1`'s colour); in multicolor
`c` is the 2-bit value `0–3`.

- `plot x,y,c` — set/clear one pixel.
- `line x1,y1,x2,y2,c` — line.
- `box x,y,w,h,c` — rectangle outline.
- `fillbox x,y,w,h,c` — filled rectangle.
- `circle x,y,r,c` — circle outline.
- `ellipse cx,cy,rx,ry,c` — ellipse outline.
- `flood x,y,c` — flood fill starting at `(x,y)`.
- `getpixel(x,y)` — function: returns `0`/`1` in hires, `0`–`3` in
  multicolor.

### Text and glyph commands

- `cls` — clear the bitmap, home the cursor, and refill the matrix with
  the `pen1`/`pen2` colours.
- `locate col,row` — move the text cursor (col 0–39, row 0–24).
- `printat col,row,c,"str"` — print a string at a fixed cell position.
- `gchar x,y,"ch",c` — draw one font glyph with its top-left corner at
  pixel `(x,y)`.
- `gtext x,y,c,"str"` — draw a string of glyphs at pixel `(x,y)`.
- `gdef n,b0,b1,…,b7` — define custom glyph `n` (0–15) from 8 rows.
- `glyph n` — print custom glyph `n` at the text cursor.
- `setfont "name"` — switch the system font to `name.fnt` from the
  REU filesystem (REU-only font: updates the kernel's font record; the
  2 KB file stays in the REU FS and the blitter DMA's glyphs on demand).

### Cursor and scrolling

- `cursor 0|1` — hide/show the text cursor.
- `shadow 0|1` — disable/enable the char-shadow mirror (used by the line
  editor).
- `scroll top,bottom` — set the scroll region (inclusive rows) and move
  the cursor to its top-left corner.
- `scrollby n` — scroll the current region by `n` rows.

### Example

```
mode 1
pen0 0                 ' value 0 = black
pen1 5                 ' value 1 = green
pen2 7                 ' value 2 = yellow
pen3 1                 ' value 3 = white
cls
circle 40,100,30,1     ' green
circle 80,100,30,2     ' yellow
circle 120,100,30,3    ' white
```

---

## Operators

| Operator | Meaning |
|---|---|
| `+` | Add |
| `-` | Subtract |
| `*` | Multiply |
| `/` | Divide |
| `^` | Raise to the power of |
| `and` | Logical and |
| `eor` | Logical exclusive or |
| `or` | Logical or |
| `<<` | Shift left |
| `>>` | Shift right |
| `=` | Equals |
| `>` | Greater than |
| `<` | Less than |
| `>=` / `=>` | Greater than or equal to |
| `<=` / `=<` | Less than or equal to |
| `<>` / `><` | Not equal to |
| `<=>` | Any order (always true) |

---

## Functions

| Function | Result |
|---|---|
| `sgn(expr)` | Sign: +1, 0 or −1 |
| `int(expr)` | Integer part |
| `abs(expr)` | Absolute value |
| `fre(expr)` | Free memory |
| `pos(expr)` | Current cursor column |
| `sqr(expr)` | Square root |
| `rnd(expr)` | Random number |
| `log(expr)` | Natural logarithm |
| `exp(expr)` | e to the power |
| `cos(expr)` / `sin(expr)` / `tan(expr)` | Trig functions (radians) |
| `atn(expr)` | Arc tangent |
| `peek(addr)` | Byte at `addr` |
| `deek(addr)` | Word at `addr` |
| `sadd(expr$)` | Pointer to the string data |
| `varptr(var[$])` | Pointer to the variable (numeric value or string descriptor) |
| `len(expr$)` | String length |
| `str$(expr)` | Numeric value as a string |
| `val(expr$)` | String as a numeric value |
| `asc(expr$)` | ASCII value of the first character |
| `ucase$(expr$)` / `lcase$(expr$)` | Upper / lower case |
| `chr$(b)` | Single-character string |
| `hex$(expr[,b])` | Hex string (optional fixed width `b`) |
| `bin$(expr[,b])` | Binary string (optional fixed width `b`) |
| `max(expr[,…])` / `min(expr[,…])` | Largest / smallest of the list |
| `pi` | 3.14159274 |
| `left$(expr$,b)` / `right$(expr$,b)` | Leftmost / rightmost `b` characters |
| `mid$(expr$,b1[,b2])` | Substring from character `b1`, length `b2` |

---

## Error messages

| Message | Meaning |
|---|---|
| `next without for` | `next` with no matching `for` |
| `syntax` | Generally wrong |
| `return without gosub` | `return` with no matching `gosub` |
| `out of data` | `read` beyond the last `data` item |
| `function call` | A function parameter was out of range |
| `overflow` | Calculation exceeded ±1.7014117E+38 |
| `out of memory` | Program/variables exhausted memory |
| `undefined statement` | `goto`/`gosub`/`run`/`restore` to a non-existent line |
| `type mismatch` | String/number type mismatch |
| `string too long` | String longer than 255 characters |
| `string too complex` | Descriptor stack overflow — split the expression |
| `can't continue` | `cont` not possible (edited, `new`, or error since stop) |
| `undefined function` | `fn <var>` called but not defined |
| `loop without do` | `loop` with no matching `do` |

Errors that occur while running a program are followed by `in line n`,
where `n` is the line number.

---

## Using Gordon Basic

From the shell:

```
run basic          ← launch BASIC using the REU working file basicwrk
```

- Program text, variables, arrays, and strings live in BASIC's REU working
  file `basicwrk`. `fre(0)` runs garbage collection and reports the free
  gap in that working file.
- `run basic` reuses `basicwrk` when it exists, otherwise creates it; the
  file is deleted when BASIC exits, so a crashed session's program survives
  into the next run.
- BASIC is single-instance (`run basic` twice → `? already running`).
- **`pool`** (shell command) lists pool allocations and their owners.

- **`RUN/STOP`** breaks a running program (CTRL-C equivalent).
- **`DEL`** is backspace during line input.
- **`exit`** leaves BASIC; the loader restores any tasks that were evicted
  to make room for it.
- **`dir`**, **`save`**, and **`load`** use the REU filesystem; saved
  programs persist across reboots.

Related documentation: [`quick-start.md`](quick-start.md) (example
sessions), [`programmers-guide.md`](programmers-guide.md) (task writing),
[`plans/ehbasic-port-plan.md`](plans/ehbasic-port-plan.md) (port history).
