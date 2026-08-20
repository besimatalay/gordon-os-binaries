# Quick Start

After boot you land in the shell (a blinking block cursor). Try:

| Command       | What it does                        |
|---------------|-------------------------------------|
| `help`        | List all commands                   |
| `ps`          | Show running tasks (ID, prio, name) |
| `dir`         | List REU filesystem files           |
| `run border`  | Border color flash demo             |
| `run maze`    | Animated maze renderer              |
| `run clock`   | Real-time clock                     |
| `run threads` | Thread demo (spawns `threads.N`)    |
| `run basic`   | [Gordon BASIC](gordonbasic.md) interpreter |
| `run gfxdemo` | Bitmap graphics demo                |

Task management: `kill <id>`, `pause <id>`, `resume <id>`, `prio <id> <0-5>`
(IDs are shown by `ps`). `view <id>` switches the display to a task's screen.

Screen switching: F1/F3/F5/F7 and Shift+F1/F3/F5/F7 cycle the 8 virtual
screens. Files you `save` persist across reboots.
