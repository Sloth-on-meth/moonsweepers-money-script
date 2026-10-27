# moonsweepers-money-script

Add dollars to the crew wallet in a Moon Sweepers save (`session.moon`) and keep `slot.json` in sync.

## Usage

```
python3 moonsweepers_wallet.py SLOT_DIR [--add 1000] [--dry-run]
```

`SLOT_DIR` is e.g. `.../MoonSessions/slot-1`. Before running, close the game
(and detach scanmem) and turn off Steam Cloud. Backups are written next to the
originals as `*.pre-wallet`. Use `--dry-run` to preview.

No dependencies beyond the Python 3 standard library.

## Save format (reverse engineered)

- `session.moon` = `b'1PCM'` + u32 payload length + u8 hash length (64) + SHA-256 hex of the *uncompressed* payload + gzip(payload)
- The crew wallet is the 16 bytes right after the `\x04team` record: a .NET `System.Decimal`
  (lo, mid, hi uint32 + flags uint32). Scale 17 (flags `0x00110000`): dollars = mantissa / 1e17.

The script aborts without changing anything unless exactly one wallet record is found.

## Tests

```
python3 -m unittest discover tests
```
