# Configuration

Everything has a default and the file is optional. To change anything, create
`~/.daedalus.toml`:

```toml
pack = "default"          # "default", "soft", or your own
min_turn_seconds = 3.0    # turns shorter than this make no sound at all
speak = true              # false keeps every tone and drops the speech
escalate_after = 30.0     # seconds before an unanswered prompt repeats, once
debounce_seconds = 0.3    # ignore a repeat of the same event inside this window
```

Changes apply when the daemon next starts — that is, your next Claude Code
session. To apply them now, stop the daemon (see
[troubleshooting](troubleshooting.md)) and it will come back with the new config.

Reading this file needs Python 3.11+ for `tomllib`. On 3.10 Daedalus still runs,
on defaults, and ignores the file.

## `min_turn_seconds` — the dial that matters

This is the one setting worth tuning from real use, and the main defence against
Daedalus becoming an annoyance.

A turn shorter than this makes **no sound at all**, on the reasoning that you
never looked away during it. Short turns are the majority of a session, so this
threshold decides how often you hear anything.

The default of 3 seconds is conservative. If Daedalus ever feels chatty, raise
this before changing anything else — 10 or more is a perfectly sensible setting
for a busy day, and some people will want 30.

It only applies to turns that *complete normally*. A turn that ends by asking
you a question, a permission prompt, and a failure are all "waiting on you" and
always make a sound, however fast they arrived.

## `speak`

Set `speak = false` to keep the tones and drop the speech entirely. Useful in a
shared office, or if you'd rather glance at the screen than be told. Blocked
states still get their tone, so you don't lose the signal — only the detail.

## `pack`

Which sound pack to use. Two ship:

- `default` — struck marimba-like tones
- `soft` — the same gestures an octave down, quieter and mellower

See [sound-packs.md](sound-packs.md) to add your own.

## `escalate_after`

An unanswered permission prompt repeats once after this long, then never again.
Daedalus will not nag a third time regardless of how long you're away.

Answering it, typing a new prompt, or the turn ending all cancel the repeat.

## `debounce_seconds`

Suppresses a duplicate of the same event kind for the same session inside this
window. It exists as a safety net in case two hooks ever describe the same
underlying moment; you shouldn't need to change it.

## What is *not* configurable

Some behaviour is deliberately fixed, because making it optional would mean
shipping a worse default and letting people find out the hard way:

- **A focused terminal never speaks.** If you can see the screen, a tone is
  enough. Use the `say` command when you want a reply read out.
- **Replies are never narrated.** Your screen renders them better than a speech
  synthesiser can, and compressing them would need a model, latency and money.
- **Tool calls make no sound.** Reading out every `Read` and `Edit` is noise;
  the screen already shows them.
