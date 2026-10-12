# How the SID Player Routine Works
## Prerequisites
The following books will be very useful to reference while reading this document:  
["COMPUTE!'s Music System for the C64 and C128" (1986)](https://archive.org/details/Computes_Music_System_for_the_Commodore_128_and_64)  
[Mappings the C64 and C64c  (1987)](https://archive.org/details/Compute_s_Mapping_the_64_and_64C)  
[C64 Programmers Reference  (1982)](https://pickledlight.blogspot.com/p/commodore-64-guides.html)  
[Kick Assembler](https://theweb.dk/KickAssembler)  


## Installation of the IRQ Routine
On powerup, the memory address at $0314 points to a routine in the Kernal at $EA31 which handles background tasks such as scanning the keyboard and flashing the cursor.  
The SID Player is installed as a User Defined IRQ Routine by placing it's memory address at $0314 (The address that was there is preserved).  
The routine is called 60 times a second based on Interrupts fired from Timer A of the CIA 1 chip.  
At the end of the routine, it will perform an indirect jump to the address that was previously at $0314 (which is normally the Kernal routine).  
The SID Player will play music at the same speed on PAL and NTSC machines.  
1/60 of a second is called a **jiffy**.

## IRQ Routine
Below is an example of a really short song.  The numbers in the columns are the index into a list of commands to execute per voice.

| Voice | 0 | 1 | 2 | 3 |
| :-: | :-: | :-: | :-: | :-: |
|  **1**  | ATK <br/>10 | SUS <br/>6 | C-4 <br/>Quarter <br/>Note | HLT |
| **2** | D-4<br/>Quarter<br/>Note | HLT | | |
| **3** | HLT | | | |

Voice 1 contains 2 commands to setup the sound for voice 1 by changing the Attack and Sustain in the ADSR envelope.  It is followed by a C Quarter Note played on the 4th octave.    
Voice 2 will play a D Quarter Note on the 4th octave using the default values for the ADSR envelope.  
Voice 3 does nothing at all.
All 3 voices have a HLT command, which signals to the player that there are no more commands to process, and to silence that voice.

### Working Memory
There are many variables that are indexed per voice or globally that maintain the current state of the song.  These include the current ADSR, waveform, and any special effects per voice.  
One of these variables controls how many jiffys are left in the current playing note on each voice.   This value is set to 1 on each voice when the song starts playing.  

### IRQ Routine
The IRQ routine is run 60 times a second.  When it runs, the following tasks occur:  
If all 3 voices are halted, the routine exits.  
For each voice:
* Skip this voice if it has been halted.
* Decrement one Jiffy from the count of remaining jiffys.
* If a note is still playing (The count of remaining Jiffys > 0), apply any needed effects and let the note continue to ring out
* If a note is not playing (The count of remaining Jiffys = 0): 
  - Process all *non-note commands* for the current voice.  
  - If the voice was not Halted, start playing the next note.  This involves looking up the duration in Jiffys from a tempo table using a combination of the current tempo for the song, note length (Quarter, Whole etc..) and any effects applied to the note (Ties, Dot etc..).  The number of jiffys to play the note is stored in working memory.  The SID Chip is programmed with all of the effects from the commands that were executed before including the frequency of the current note.  The voice is then set to start playing the note.

Based on the text above, the chart below is re-written to show which commands will execute on each iteration of the IRQ Routine:

| Voice |  |  | 1 | 2 |
| :-: | :-: | :-: | :-: | :-: |
| **1** | ATK <br/>10 | SUS <br/>6 | C-4 <br/>Quarter <br/>Note | HLT |
| **2** | | | D-4<br/>Quarter<br/>Note | HLT |
| **3** | | |  HLT |  |

The first time the IRQ Routine is run:  
Voice 1 will process the ATK and SUS command and then start playing the C-4 Quarter Note.  
Voice 2 will start playing the D-4 Quarter Note.  
Voice 3 will Halt and silence itself. 


1/60 of a second later, the IRQ handler will be called again, and the process will continue from column 2 where:  
Voice 1 will halt and silence itself.  
Voice 2 will halt and silence itself.  
Voice 3 will not be processed as it was halted in the first iteration of the IRQ Routine.

All future iterations of the IRQ Handler will not do anything, until a new song is initialized and commanded to start playing.  

## How commands are decoded in the source code
As described in the musFileFormat.md document, each command is comprised of 2 bytes.  A command byte, and an option byte. The process starts at label "DecodeCommand" in the source code (sidobj.asm).  
The command byte is ANDed with 00000011 to determine if bits 0 and 1 are 0.   If they are non zero (01,10 or 11), the code will jump to the ProcessCmdLoop label which will look for and process the next non-note command.  It will continue to do this until a note command is found.  
Once a note is found, the process of setting up and starting the note is performed.

### How non-note commands are routed to their routine
Non-note Commands (where the command byte bits 0-1 are 10, 01 or 11) are analyzed bit by bit to locate the routine to process it.  

Let's follow the logic of a simple command (POR Portamento) to see how the SID Player gets to the routine to process it.  The POR command takes a value between 0 and 16383, which is a 14 bit value.  In the SID Editor, the command is shown like this:  
*POR*  
*12000*

It is encoded into two bytes:  
| Byte    | Hex | Binary   |
| -       | -   | -        |
| Command:| $BB | 10111011 |
| Option: | $E0 | 11100000 |

The routine starts by loading the command byte into the Accumulator and pushing the option byte on the stack.  
LSR is used to shift the bits in the accumulator to the right by 1 resulting in bit 0 being moved to the carry flag.  
10111011 LSRed becomes 01011101 with Carry=1  
Because the carry flag is set, the routine will proceed to label rc________1.  The label represents a Routing of Command where we know bit 0 is a 1.  
The code rc________1 will then perform another LSR on the accumulator where:  
01011101 becomes 00101110 with Carry = 1  
Because the carry is set, the code will proceed into the rc_______11_POR label.  This label is named to show that bits 0 and 1 are known to be 1, and the _POR portion shows that this is the routine that will handle the POR Command.  

The accumulator conveniently now contains the hi byte of our value:   00101110 (Decimal: 46).  
The stack has the option byte which is the lo byte of our value: $E0 11100000 (Decimal: 225)  
The routine simply copies the Accumulator to WorkPortamentoHi and the stack to WorkPortamentoLo.  
You can test that the lo/hi bytes = 12000 by using the standard lo/hi formula: lo + (256*hi) = value.  224 + (256 * 46) = 12,000.  
These routines typically copy their decoded values into the work memory area.  
The Work memory area is applied to a voice either when a note is about to be played, or when a note is already playing (applying a special effect to a note that is playing).  








