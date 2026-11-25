#!/usr/bin/env python3
"""Synthetic NE metadata tests; never claims native input support."""
from pathlib import Path
import sys,struct,tempfile,unittest
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root/'HOST'))
import inputabi

def nt(rows):
    return b''.join(bytes([len(n)])+n.encode()+struct.pack('<H',o) for n,o in rows)+b'\0'

def fixture(packed=False):
    h=0x80; b=bytearray(1024);b[h:h+2]=b'NE';b[h+2:h+4]=b'\x05\x01'
    if not packed:
        b[:2]=b'MZ';struct.pack_into('<I',b,0x3c,h)
    resident=nt([('USER',0),('SetCursorPos',70),('mouse_event',299)])
    table=bytes([69,0,1,1,1,0x10,0,218,0,1,255,1,0xcd,0x3f,1,0x20,0,9,0,1,1,1,0x30,0,0])
    # ordinal 70 fixed, 289 movable, 299 fixed.
    struct.pack_into('<HH',b,h+4,0x100,len(table));struct.pack_into('<H',b,h+0x1c,1)
    struct.pack_into('<HH',b,h+0x26,0x60,0x60+len(resident))
    b[h+0x60:h+0x60+len(resident)]=resident;b[h+0x100:h+0x100+len(table)]=table
    nr=nt([('User module',0),('keybd_event',289)]);struct.pack_into('<H',b,h+0x20,len(nr));struct.pack_into('<I',b,h+0x2c,0x300);b[0x300:0x300+len(nr)]=nr
    return b

class Test(unittest.TestCase):
    def test_standalone(self):
        r=inputabi.parse_header(fixture(),0x80,True);c={x['ordinal']:x for x in r['candidates']}
        self.assertEqual(r['module'],'USER');self.assertEqual(r['entry_status'],'PARSED');self.assertEqual(c[17]['state'],'ENTRY_NOT_PRESENT');self.assertEqual(c[70]['entry']['offset'],16);self.assertEqual(c[289]['names'],['keybd_event']);self.assertEqual(c[289]['entry']['segment'],1);self.assertEqual(c[299]['entry']['offset'],48)
    def test_packed(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'WIN100.BIN';p.write_bytes(fixture(True));r=inputabi.inspect_file(p)['modules'][0];self.assertEqual(r['nonresident_status'],'UNRESOLVED_PACKED_OFFSET');self.assertEqual(r['entry_status'],'PARSED');self.assertEqual(next(x for x in r['candidates'] if x['ordinal']==289)['names'],[]);self.assertFalse(inputabi.inventory(Path(t))['input_qualified'])
    def test_bad_tables(self):
        b=fixture();struct.pack_into('<H',b,0x80+6,1);r=inputabi.parse_header(b,0x80,True);self.assertEqual(r['entry_status'],'UNRESOLVED');self.assertEqual(next(x for x in r['candidates'] if x['ordinal']==299)['state'],'UNKNOWN');self.assertIsNone(inputabi.parse_header(b,0,False));self.assertIsNone(inputabi.parse_header(b,10000,False))
    def test_no_modules(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'WIN200.BIN';p.write_bytes(b'NE'+bytes(1024));self.assertEqual(inputabi.inventory(Path(t))['user_table_status'],'UNRESOLVED')
    def test_dispatch(self):
        s=(root/'AUDIT.BAT').read_text();self.assertIn('if /I "%MODE%"=="INPUTABI" goto runner',s);self.assertIn('set "MODE=STARTSHOT"\ngoto ready\n:inputabi',s);self.assertIn("if mode == 'INPUTABI':",(root/'HOST/AUDIT.PY').read_text());self.assertIn('INPUTABI', __import__('audit_modes').OPERATOR_MODES)
if __name__=='__main__':unittest.main()
