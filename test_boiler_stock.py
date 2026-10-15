import unittest
import boiler_stock as b
class StockTests(unittest.TestCase):
 def test_current(self):
  for cap,price in b.STOCK.items():self.assertIn(f'{price:,} ریال',b.answer(f'قیمت بی تا {cap}'))
 def test_unavailable(self):
  for s in ['پکیج ایران رادیاتور A22','پرلا پرو ۲۴','پارما 26']:self.assertIn('ناموجود',b.answer(s))
 def test_unrelated(self):self.assertIsNone(b.answer('قیمت رادیاتور ایران رادیاتور'))
