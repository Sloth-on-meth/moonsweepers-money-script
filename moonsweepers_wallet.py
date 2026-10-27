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


def find_wallets(payload, dollars):
    """Find System.Decimal values (any valid scale) that match slot.json's dollars.

    Candidates right after a b'\\x04team' marker win; otherwise every match in the payload is returned.
    """
    data = bytes(payload)
    found = []
    for off in range(0, len(data) - 15):
        lo, mid, hi, flags = struct.unpack_from('<4I', data, off)
        scale = (flags >> 16) & 0xFF
        if flags & ~(0x1F << 16) or scale > 28:
            continue
        mant = lo | (mid << 32) | (hi << 64)
        if mant and abs(float(Decimal(mant) / Decimal(10) ** scale) - dollars) <= 1.0:
            found.append((off, mant, scale))
    marked = [c for c in found if data[max(0, c[0] - 5):c[0]] == b'\x04team']
    return marked or found


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('slot_dir')
    ap.add_argument('--add', default='1000')
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--diagnose', action='store_true', help='print wallet candidates and team markers')
    a = ap.parse_args(argv)

    slot = Path(a.slot_dir).expanduser()
    sj = slot / 'slot.json'
    meta = json.loads(sj.read_text())
    sessions = list(slot.glob('*/session.moon'))
    if len(sessions) != 1:
        sys.exit(f'expected one <hash>/session.moon under {slot}, found {len(sessions)}')
    sp = sessions[0]
    payload = read_session(sp)

    cands = find_wallets(payload, meta['dollars'])
    if a.diagnose or len(cands) != 1:
        print(f'slot.json dollars: {meta["dollars"]}; payload {len(payload)} bytes; '
              f'{len(cands)} wallet candidate(s):')
        for off, mant, scale in cands:
            print(f'  offset {off} scale {scale} -> ${Decimal(mant) / Decimal(10) ** scale}  '
                  f'ctx={bytes(payload[max(0, off - 12):off])!r}')
        for m in re.finditer(rb'\x04team', bytes(payload)):
            print(f'  team marker at {m.start()}; next 16 bytes: {bytes(payload[m.end():m.end() + 16]).hex()}')
    if len(cands) != 1:
        sys.exit(f'Expected exactly one wallet record, found {len(cands)}. Nothing changed.')
    off, mant, scale = cands[0]
    cur = Decimal(mant) / Decimal(10) ** scale
    print(f'Wallet at offset {off}: ${cur}   (slot.json says {meta["dollars"]})')

    add = int(Decimal(a.add) * Decimal(10) ** scale)
    new = mant + add
    if not (0 <= new < 1 << 96):
        sys.exit('Resulting amount out of range.')
    print(f'New wallet: ${Decimal(new) / Decimal(10) ** scale}')
    if a.dry_run:
        print('Dry run. Nothing written.')
        return

    struct.pack_into('<3I', payload, off, new & 0xFFFFFFFF, (new >> 32) & 0xFFFFFFFF, new >> 64)
    for f in (sp, sj):
        shutil.copy2(f, f.with_name(f.name + '.pre-wallet'))
    write_session(sp, payload)
    meta['dollars'] = float(Decimal(new) / Decimal(10) ** scale)
    sj.write_text(json.dumps(meta, separators=(',', ':')))
    read_session(sp)  # re-validate
    print('Written. Backups: *.pre-wallet')


if __name__ == '__main__':
    main()
