# Gordon Basic

> **Gordon Basic v1.5** — the built-in BASIC interpreter for GordonOS.

Gordon Basic is a full floating-point Microsoft BASIC 2.0-compatible
interpreter that runs as a **task** on GordonOS. It is loaded on demand
from the REU filesystem with `run basic` and runs on its own screen with
case-preserving input, RUN/STOP-to-break, and C64 screen-editor-style line
editing. Programs live in 10 KB of RAM at `$8000–$A7FF`.

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

- `IRQ`, `NMI`, `RETIRQ`, `RETNMI`, `ON IRQ`, `ON NMI`, `OFF`, `NULL` —
  interrupt-handler plumbing. GordonOS owns all interrupts; BASIC never
  touches them. (`ON <expr> GOTO|GOSUB` is kept — see `ON`.)
- `USR(<expr>)` — user-routine call vector.
- `BITCLR`, `BITSET`, `BITTST` — bit-manipulation commands/function.
- `TWOPI` — the constant `2*pi`.

**Added** (GordonOS integration):

- `DIR` — list the REU filesystem.
- `EXIT` — leave BASIC and return to the shell.

**Changed:**

- `SAVE` / `LOAD` — stock EhBASIC left these as no-op vectors. Gordon Basic
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
quotation marks. Non-printing characters can be produced with `CHR$()`.

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
- Variable names may not contain BASIC keywords (keywords are only
  recognised in upper case).

## Keywords

Here is the complete list of Gordon Basic keywords. They are only valid
when entered in upper case as shown, and spaces may not be included in
them (`GO TO` is not `GOTO`).

```
ABS   AND   ASC   ATN   BIN$  CALL  CHR$  CLEAR CONT  COS
DATA  DEC   DEEK  DEF   DIM   DIR   DO    DOKE  END   EOR
EXIT  EXP   FN    FOR   FRE   GET   GOSUB GOTO  HEX$  IF
INC   INPUT INT   LCASE$ LEFT$ LEN  LET   LIST  LOAD  LOG
LOOP  MAX   MID$  MIN   NEW   NEXT  NOT   ON    OR    PEEK
PI    POKE  POS   PRINT READ  REM   RESTORE RETURN RIGHT$ RND
RUN   SADD  SAVE  SGN   SIN   SPC(  SQR   STEP  STOP  STR$
SWAP  TAB(  TAN   THEN  TO    UCASE$ UNTIL VAL  VARPTR WAIT
WHILE WIDTH
+  -  *  /  ^  <<  >>  <  <=  =  >=  >  <>
```

### Notation

- UPPER CASE — part of the command/function structure, must be present.
- `<lower case>` — supplied by the user.
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

### `END`

Terminates program execution and returns to direct mode. `END` may be
placed anywhere in a program — it does not have to be on the last line, and
there may be any number of them. `CONT` can resume execution after an
`END`.

### `FOR <var> = <expression> TO <expression> [STEP expression]` … `NEXT [var[,var]…]`

Assigns a loop counter and optionally sets the start value, end value and
step size. If `STEP` is omitted, the step size defaults to +1. `NEXT`
increments/decrements the loop variable and checks the terminating
condition.

### `DATA [{r|$}[,{r|$}]…]`

Defines a constant or series of constants for `READ`. Real constants are
held as strings and can be read as either numeric or string values. String
constants may contain spaces; if they must contain commas, enclose them in
quotes.

### `INPUT ["$";] <var>[,var]…`

Reads a value, or list of values, from the input stream. A `?` prompt is
always output, after the optional prompt string. If more values are
required than were entered, `??` is output until enough have been given.

### `DIM <var[$](i1[,i2[,in]…])>[,var[$](…)]…`

Dimensions arrays of string or numeric variables. Arrays may have one or
more dimensions; the lower bound is always zero and the upper bound is `i`.
An array not explicitly dimensioned is created on first access with an
upper bound of 10 per dimension.

### `READ <var>[,var]…`

Reads values from `DATA` statements and assigns them to variables.

### `LET <var> = <expression>`

Assigns the value of `<expression>` to `var`. The `LET` word is optional —
`var = expression` is identical.

### `DEC <var>[,var]…`

Decrements each listed variable by one. `DEC A` is much faster than
`A=A-1`.

### `INC <var>[,var]…`

Increments each listed variable by one. `INC A` is much faster than
`A=A+1`.

### `GOTO <n>`

Continues execution at line `n`. If `n` does not exist, an "Undefined
statement" error is generated.

### `RUN [n]`

Loads and runs the program. If `n` is given, execution starts at line `n`.

### `IF <expression> THEN {<statement(s)>|n|GOTO n|GOSUB n}` [`ELSE …`]

Evaluates `<expression>`. If non-zero the `THEN` branch is taken;
otherwise execution continues with the `ELSE` branch (if present) or the
next line.

### `RESTORE [n]`

Resets the `DATA` pointer, to the start of the program or to the beginning
of line `n`.

### `GOSUB <n>` … `RETURN`

Calls a subroutine at line `n`. On `RETURN`, execution resumes at the
statement after the `GOSUB`.

### `REM`

Everything following `REM` on the line is ignored, even colons.

### `STOP`

Halts execution and prints `Break in line n`.

### `ON <expression> GOTO <n>[,n]…` / `ON <expression> GOSUB <n>[,n]…`

Uses the integer value of `<expression>` (0–255) to select the nth line
number after `GOTO`/`GOSUB`. Values outside 0–255 cause a "Function call"
error.

### `WAIT <addr,b1>[,b2]`

Waits until `(PEEK(addr) EOR b2) AND b1` is non-zero. `b2` defaults to 0.

### `LOAD "<name>"`

Loads a previously saved program from the REU filesystem and warm-starts
BASIC. See *Filesystem commands* below.

### `SAVE "<name>"`

Saves the current program to the REU filesystem. See *Filesystem
commands* below.

### `DEF FN <name>(<var>) = <statement>`

Defines `<statement>` as a function. `<name>` is any numeric variable
name; `<var>` is a simple variable used as the (local) argument.

### `POKE <addr,b>`

Writes byte `b` to address `addr`. `DOKE <addr,w>` writes a word (low byte
at `addr`, high byte at `addr+1`).

### `CALL <addr>`

Calls a user subroutine at `addr`. No values are passed or returned.

### `DO … LOOP [UNTIL <expression>|WHILE <expression>]`

Loops. `DO` marks the top and `LOOP` the bottom; the terminating condition
(`UNTIL` or `WHILE`) may be at either end.

### `PRINT [expression|$] [;|,] …`

Evaluates expressions and prints the results. `;` suppresses the
separator, `,` advances to the next tab stop. A trailing `;` or `,`
suppresses the newline. `PRINT` alone prints a blank line. `?` is a
shorthand for `PRINT`.

### `CONT`

Continues execution after CTRL-C, a `STOP`, or a null `INPUT`.

### `LIST [n1][-n2]`

Lists the program. With `n1`, listing starts at (or after) line `n1`; with
`-n2` it stops at (or before) line `n2`.

### `CLEAR`

Erases all variables and functions and resets `FOR`/`GOSUB`/`DO` state.

### `NEW`

Deletes the current program and all variables.

### `WIDTH {b1|,b2|b1,b2}`

Sets the terminal width (`b1`, 16–255 or 0 for infinite) and tab spacing
(`b2`).

### `GET <var[$]>`

Reads one key, if any, without halting. If no key is waiting, `var` is set
to 0 and `var$` to `""`.

### `SWAP <var1>,<var2>`

Exchanges the values of two variables (of the same type).

### `EXIT`

**GordonOS extension.** Ends the BASIC task: frees its screen and returns
control to the shell. Equivalent to typing `exit` in the shell.

### `DIR`

**GordonOS extension.** Lists the REU filesystem — one entry per line,
name padded to 11 columns followed by the size in right-aligned decimal
bytes.

### `TAB(<expression>)` / `SPC(<expression>)`

Valid only within a `PRINT`: `TAB` positions the cursor at column
`<expression>`; `SPC` prints that many spaces.

### `NOT`, `STEP`, `THEN`, `TO`, `ELSE`, `UNTIL`, `WHILE`, `FN`

Structural keywords — see the commands they belong to (`FOR`, `IF`, `DO …
LOOP`, `DEF`).

---

## Filesystem commands (`DIR`, `SAVE`, `LOAD`)

`SAVE` and `LOAD` store programs in the GordonOS REU filesystem as files
with a `.bas` extension.

```
SAVE "prog"      ← saves the program as prog.bas
LOAD "prog"      ← loads prog.bas and warm-starts (prints ready)
DIR              ← lists the filesystem
```

**Filename rules:**

- The name is 1–7 characters, with no `.` — the `.bas` extension is
  appended for you.
- Letters are case-sensitive (`"Prog"` and `"prog"` are different files).
- `SAVE` errors: `? bad name`, `? exists` (duplicate), `? no space`,
  `? dir full`.
- `LOAD` errors: `? bad name`, `? not found`.
- `SAVE ""` and names with a `.` or more than 7 characters print
  `? bad name`.

Files persist across reboots; you can also see and manage them from the
shell with `dir`, `del`, `save`, and `load`.

---

## Operators

| Operator | Meaning |
|---|---|
| `+` | Add |
| `-` | Subtract |
| `*` | Multiply |
| `/` | Divide |
| `^` | Raise to the power of |
| `AND` | Logical AND |
| `EOR` | Logical exclusive OR |
| `OR` | Logical OR |
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
| `SGN(expr)` | Sign: +1, 0 or −1 |
| `INT(expr)` | Integer part |
| `ABS(expr)` | Absolute value |
| `FRE(expr)` | Free memory |
| `POS(expr)` | Current cursor column |
| `SQR(expr)` | Square root |
| `RND(expr)` | Random number |
| `LOG(expr)` | Natural logarithm |
| `EXP(expr)` | e to the power |
| `COS(expr)` / `SIN(expr)` / `TAN(expr)` | Trig functions (radians) |
| `ATN(expr)` | Arc tangent |
| `PEEK(addr)` | Byte at `addr` |
| `DEEK(addr)` | Word at `addr` |
| `SADD(expr$)` | Pointer to the string data |
| `VARPTR(var[$])` | Pointer to the variable (numeric value or string descriptor) |
| `LEN(expr$)` | String length |
| `STR$(expr)` | Numeric value as a string |
| `VAL(expr$)` | String as a numeric value |
| `ASC(expr$)` | ASCII value of the first character |
| `UCASE$(expr$)` / `LCASE$(expr$)` | Upper / lower case |
| `CHR$(b)` | Single-character string |
| `HEX$(expr[,b])` | Hex string (optional fixed width `b`) |
| `BIN$(expr[,b])` | Binary string (optional fixed width `b`) |
| `MAX(expr[,…])` / `MIN(expr[,…])` | Largest / smallest of the list |
| `PI` | 3.14159274 |
| `LEFT$(expr$,b)` / `RIGHT$(expr$,b)` | Leftmost / rightmost `b` characters |
| `MID$(expr$,b1[,b2])` | Substring from character `b1`, length `b2` |

---

## Error messages

| Message | Meaning |
|---|---|
| `NEXT without FOR` | `NEXT` with no matching `FOR` |
| `Syntax` | Generally wrong |
| `RETURN without GOSUB` | `RETURN` with no matching `GOSUB` |
| `Out of DATA` | `READ` beyond the last `DATA` item |
| `Function call` | A function parameter was out of range |
| `Overflow` | Calculation exceeded ±1.7014117E+38 |
| `Out of memory` | Program/variables exhausted memory |
| `Undefined statement` | `GOTO`/`GOSUB`/`RUN`/`RESTORE` to a non-existent line |
| `Type mismatch` | String/number type mismatch |
| `String too long` | String longer than 255 characters |
| `String too complex` | Descriptor stack overflow — split the expression |
| `Can't continue` | `CONT` not possible (edited, `NEW`, or error since stop) |
| `Undefined function` | `FN <var>` called but not defined |
| `LOOP without DO` | `LOOP` with no matching `DO` |

Errors that occur while running a program are followed by `in line n`,
where `n` is the line number.

---

## Using Gordon Basic

From the shell:

```
run basic          ← launch BASIC on its own screen
view basic         ← switch back to BASIC's screen (after run basic)
```

- **`RUN/STOP`** breaks a running program (CTRL-C equivalent).
- **`DEL`** is backspace during line input.
- **F-keys** switch screens between BASIC, the shell, and other tasks —
  your session is preserved.
- **`EXIT`** leaves BASIC; the loader restores any tasks that were evicted
  to make room for it.
- **`DIR`**, **`SAVE`**, and **`LOAD`** use the REU filesystem; saved
  programs persist across reboots.

Related documentation: [`quick-start.md`](quick-start.md) (example
sessions), [`programmers-guide.md`](programmers-guide.md) (task writing),
[`plans/ehbasic-port-plan.md`](plans/ehbasic-port-plan.md) (port history).
