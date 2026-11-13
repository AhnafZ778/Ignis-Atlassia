import sqlite3
import tempfile
import unittest
from pathlib import Path
from fireatlas.mask_map import samples

class NativeMaskMapTest(unittest.TestCase):
    def test_scope_classes_counts_and_sampling(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'masks.sqlite3'
            with sqlite3.connect(path) as db:
                db.executescript('''CREATE TABLE granules(case_id,producer_id,source_id,platform,start_utc);
                    CREATE TABLE pixels(case_id,producer_id,line,sample,lat,lon,mask_class);''')
                db.execute('INSERT INTO granules VALUES (?,?,?,?,?)', ('park','p','MODIS_SP','Terra','2024-07-25T10:00:00Z'))
                for i in range(50):
                    db.execute('INSERT INTO pixels VALUES (?,?,?,?,?,?,?)', ('park','p',0,i,40,-121,5))
                db.execute('INSERT INTO pixels VALUES (?,?,?,?,?,?,?)', ('park','p',1,1,40,-121,4))
                db.execute('INSERT INTO pixels VALUES (?,?,?,?,?,?,?)', ('park','p',1,2,40,-121,9))
                db.execute('INSERT INTO pixels VALUES (?,?,?,?,?,?,?)', ('park','p',1,3,40,-121,1))
                db.execute('INSERT INTO pixels VALUES (?,?,?,?,?,?,?)', ('park','p',1,4,20,-121,5))
            result=samples('2024-07-25',[-122,39,-120,41],path,limit=24)
            self.assertTrue(result['available'])
            self.assertEqual(result['counts'], {'MODIS_SP:5':50,'MODIS_SP:4':1,'MODIS_SP:9':1})
            self.assertEqual(len(result['samples']),4)
            self.assertEqual(result,samples('2024-07-25',[-122,39,-120,41],path,limit=24))
            self.assertFalse(samples('2024-07-26',[-122,39,-120,41],path)['available'])
            self.assertFalse(samples('2024-07-25',[-122,39,-120,41],Path(tmp)/'missing')['available'])

if __name__=='__main__': unittest.main()
