import json, sys, tempfile, unittest
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import moonsweepers_wallet as w


def make_slot(root, dollars, scale=w.SCALE):
    slot = Path(root) / 'slot-1'
    (slot / 'abc123').mkdir(parents=True)
    mant = int(Decimal(dollars) * Decimal(10) ** scale)
    wallet = (mant.to_bytes(12, 'little')) + (scale << 16).to_bytes(4, 'little')
    w.write_session(slot / 'abc123' / 'session.moon', b'header\x04team' + wallet + b'tail')
    (slot / 'slot.json').write_text(json.dumps({'dollars': float(dollars)}))
    return slot


def wallet_of(slot):
    p = w.read_session(next(slot.glob('*/session.moon')))
    off = p.index(b'\x04team') + 5
    mant, flags = w.decode(p, off)
    return Decimal(mant) / Decimal(10) ** (flags >> 16)


class WalletTest(unittest.TestCase):
    def test_add(self):
        with tempfile.TemporaryDirectory() as d:
            slot = make_slot(d, '2500.5')
            w.main([str(slot), '--add', '1000'])
            self.assertEqual(wallet_of(slot), Decimal('3500.5'))
            self.assertEqual(json.loads((slot / 'slot.json').read_text())['dollars'], 3500.5)
            self.assertTrue((slot / 'slot.json.pre-wallet').exists())
            self.assertTrue(next(slot.glob('*/session.moon.pre-wallet')).exists())

    def test_high_scale_overflow_rescales(self):
        with tempfile.TemporaryDirectory() as d:
            slot = make_slot(d, '70558.5', scale=24)
            w.main([str(slot), '--add', '30000000'])
            self.assertEqual(wallet_of(slot).quantize(Decimal('0.01')), Decimal('30070558.50'))

    def test_dry_run(self):
        with tempfile.TemporaryDirectory() as d:
            slot = make_slot(d, '10')
            w.main([str(slot), '--dry-run'])
            self.assertEqual(wallet_of(slot), Decimal('10'))


if __name__ == '__main__':
    unittest.main()
