# Lessons Learned

## Windows 11 balloon notifications are unreliable

`pystray.Icon.notify()` uses the legacy balloon-tip API which Windows 11 silently drops. Replaced with a tkinter `showinfo` dialog spawned in a background thread — guaranteed visible regardless of OS notification settings.

## Star Citizen does not always log aUEC amounts

The `Added notification "Awarded \d+ aUEC"` line is inconsistently written by the game client. It has been observed in older sessions but was absent after mission completions during testing. The regex is correct; the game simply omits the line. No code fix possible — this is a game-side inconsistency.

## ALT-F4 fires the on-foot death pattern

`CSCActorCorpseUtils::PopulateItemPortForItemRecoveryEntitlement` triggers on client-side item recovery cleanup, which runs on ALT-F4 as well as true in-game deaths. Currently left in for data gathering; needs more real death events to determine if the patterns are distinguishable.

## pystray `notify()` argument order is `(message, title)`

Not `(title, message)` as might be expected. Both arguments were initially swapped, causing silent failures.

## tkinter dialogs must be created on their own thread with a fresh `Tk()` root

Attempting to reuse a root across threads or calls causes crashes. Each dialog call creates and destroys its own `Tk()` instance on a daemon thread.
