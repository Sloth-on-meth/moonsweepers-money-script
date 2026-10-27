#!/usr/bin/env python3
"""Add dollars to the Moon Sweepers crew wallet in session.moon (and update slot.json).

Format (reverse engineered from your saves):
  session.moon = b'1PCM' + u32 payload length + u8 64 + sha256 hex of UNCOMPRESSED payload + gzip(payload)
  The crew wallet is the 16 bytes right after the b'\\x04team' record: a .NET System.Decimal
  (lo, mid, hi uint32 + flags uint32). Scale 17 (flags 0x00110000): dollars = mantissa / 1e17.

Usage: moonsweepers_wallet.py SLOT_DIR [--add 1000] [--dry-run]
  SLOT_DIR = .../MoonSessions/slot-1
Close the game (and detach scanmem) and turn off Steam Cloud first. Backups: *.pre-wallet
"""
import argparse, gzip, hashlib, json, re, shutil, struct, sys
from decimal import Decimal
from pathlib import Path

SCALE = 17
FLAGS = SCALE << 16


def read_session(p):
    d = p.read_bytes()
    assert d[:4] == b'1PCM', 'not a 1PCM session file'
    n = struct.unpack('<I', d[4:8])[0]
    hl = d[8]
    h = d[9:9 + hl].decode()
    payload = gzip.decompress(d[9 + hl:])
    assert len(payload) == n, 'length mismatch'
    assert hashlib.sha256(payload).hexdigest() == h, 'hash mismatch (unexpected format)'
    return bytearray(payload)


def write_session(p, payload):
    gz = gzip.compress(bytes(payload), 6, mtime=0)
    h = hashlib.sha256(payload).hexdigest().encode()
    p.write_bytes(b'1PCM' + struct.pack('<I', len(payload)) + bytes([len(h)]) + h + gz)


def decode(payload, off):
    lo, mid, hi, flags = struct.unpack_from('<4I', payload, off)
    return lo | (mid << 32) | (hi << 64), flags


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('slot_dir')
    ap.add_argument('--add', default='1000')
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args(argv)

    slot = Path(a.slot_dir).expanduser()
    sj = slot / 'slot.json'
    meta = json.loads(sj.read_text())
    sessions = list(slot.glob('*/session.moon'))
    if len(sessions) != 1:
        sys.exit(f'expected one <hash>/session.moon under {slot}, found {len(sessions)}')
    sp = sessions[0]
    payload = read_session(sp)

    cands = []
    for m in re.finditer(rb'\x04team', bytes(payload)):
        off = m.end()
        if off + 16 > len(payload):
            continue
        mant, flags = decode(payload, off)
        if flags == FLAGS:
            cands.append((off, mant))
    if len(cands) != 1:
        sys.exit(f'Expected exactly one wallet record, found {len(cands)}. Nothing changed.')
    off, mant = cands[0]
    cur = Decimal(mant) / Decimal(10) ** SCALE
    print(f'Wallet at offset {off}: ${cur}   (slot.json says {meta["dollars"]})')
    if abs(float(cur) - meta['dollars']) > 1.0:
        print('Warning: wallet differs from slot.json by more than $1 (slot.json may be stale).')

    add = int(Decimal(a.add) * Decimal(10) ** SCALE)
    new = mant + add
    if not (0 <= new < 1 << 96):
        sys.exit('Resulting amount out of range.')
    print(f'New wallet: ${Decimal(new) / Decimal(10) ** SCALE}')
    if a.dry_run:
        print('Dry run. Nothing written.')
        return

    struct.pack_into('<3I', payload, off, new & 0xFFFFFFFF, (new >> 32) & 0xFFFFFFFF, new >> 64)
    for f in (sp, sj):
        shutil.copy2(f, f.with_name(f.name + '.pre-wallet'))
    write_session(sp, payload)
    meta['dollars'] = float(Decimal(new) / Decimal(10) ** SCALE)
    sj.write_text(json.dumps(meta, separators=(',', ':')))
    read_session(sp)  # re-validate
    print('Written. Backups: *.pre-wallet')


if __name__ == '__main__':
    main()
