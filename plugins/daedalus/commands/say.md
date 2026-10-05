---
description: Read your last reply aloud, or speak the words you give it
allowed-tools: Bash(daedalus say:*)
---

Text the user asked for: $ARGUMENTS

Run `daedalus say "<text>"` once.

**If there is text above, `<text>` is exactly that.** Speak what was asked for,
word for word — do not summarise it, rephrase it or add to it.

**Otherwise** `<text>` is your own previous reply, reduced to the one sentence
that carries the outcome:

- One sentence, under about twenty words.
- No code, no markdown, no file paths beyond a bare filename — it is being read
  by a speech synthesiser, not displayed.
- Lead with the outcome, not the process.
- If your previous reply asked the user a question, speak the question and
  nothing else.

Then report what the command printed:

- `speaking` — confirm in a few words and stop.
- Anything else — **say what it printed, verbatim.** `nothing was said -- ...`
  means no speech backend resolved and the text was discarded; the message names
  what to install. `daemon not running` means the daemon is down. Never report
  this as spoken: the user heard nothing, and a bare confirmation would send
  them looking at their speakers instead of at the real cause.
