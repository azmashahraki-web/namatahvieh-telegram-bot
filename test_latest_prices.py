import unittest
from types import SimpleNamespace
from unittest.mock import Mock

import catalog_pdf
import latest_prices as prices


class PriceTests(unittest.TestCase):
    def setUp(self):
        self.original = Mock()
        self.bot = SimpleNamespace(handle_text=self.original, get_session=Mock(return_value=(None, {})),
                                   ensure_user=Mock(), send=Mock(), catalog_keyboard=catalog_pdf.keyboard)
        prices.install(self.bot)

    def msg(self, text, kind='private'):
        return {'chat': {'id': 101, 'type': kind}, 'from': {'id': 101}, 'text': text}

    def test_every_exact_gplus_price(self):
        self.assertEqual(len(prices.PRICES), 39)
        for model, amount in prices.PRICES.items():
            self.bot.send.reset_mock()
            self.bot.handle_text(self.msg(f'قیمت {model} چنده؟'))
            self.assertIn(f'{model}: {amount:,} ریال', self.bot.send.call_args.args[1])

    def test_model_boundaries_normalization_and_suffixes(self):
        self.assertEqual(prices.exact_prices('قیمت gtv – ۳۲sd۶۴۸n چنده؟'), [('GTV-32SD648N', 370000000)])
        self.assertEqual(prices.exact_prices('قیمت GTV-55SQ789NP'), [('GTV-55SQ789NP', 910000000)])
        self.assertEqual(prices.exact_prices('GTV-55SQ789N-X'), [])
        self.assertEqual(prices.exact_prices('AGTV-55SQ789N'), [])
        self.assertEqual(prices.exact_prices('GWM-R808W.NX'), [])
        self.assertEqual(prices.exact_prices('GWM-R808W.N.'), [('GWM-R808W.N', 960000000)])

    def test_every_radiator_price_and_word_counts(self):
        self.assertEqual(sum(map(len, prices.RADIATORS.values())), 12)
        for series, rows in prices.RADIATORS.items():
            for count, amount in rows.items():
                self.bot.handle_text(self.msg(f'قیمت {series} {count} پره چنده؟'))
                self.assertIn(f'{count} پره: {amount:,}', self.bot.send.call_args.args[1])
        self.bot.handle_text(self.msg('قیمت رادیاتور ایل پرمو سه پره'))
        self.assertIn('62,960,700', self.bot.send.call_args.args[1])
        self.bot.handle_text(self.msg('قیمت النا ۷ پره'))
        self.assertIn('124,124,000', self.bot.send.call_args.args[1])

    def test_unknown_and_unsupported_do_not_guess(self):
        for text in ('قیمت GTV-55SQ789NX', 'قیمت ویتوریا ۱۲ پره', 'قیمت کولر جی پلاس ۲۴۰۰۰'):
            self.bot.handle_text(self.msg(text))
            self.assertTrue(self.bot.send.called)
            self.original.assert_not_called()
            self.bot.send.reset_mock()

    def test_mixed_models_and_amounts_kept_verbatim(self):
        self.bot.handle_text(self.msg('قیمت GDW-R5683S و GDW-R1599B و GTV-NOPE'))
        text = self.bot.send.call_args.args[1]
        for value in ('1,270,000,001', '1,479,000,001', 'GTV-NOPE', prices.NOTICE):
            self.assertIn(value, text)

    def test_preserve_commands_sessions_specs_groups_and_pdf(self):
        for text, kind in [('/start', 'private'), ('مشخصات GTV-32SD648N', 'private'),
                           ('قیمت GTV-32SD648N', 'group'), ('لیست قیمت GTV-32SD648N را بفرست', 'private')]:
            self.bot.handle_text(self.msg(text, kind))
        self.assertEqual(self.original.call_count, 4)
        self.bot.get_session.return_value = ('admin_teach', {})
        self.bot.handle_text(self.msg('قیمت GTV-32SD648N'))
        self.assertEqual(self.original.call_count, 5)
        self.bot.send.assert_not_called()

    def test_bare_model(self):
        self.bot.handle_text(self.msg('GTV-32SD648N'))
        self.assertIn('370,000,000', self.bot.send.call_args.args[1])

    def test_multiple_radiator_series_keep_their_own_counts(self):
        self.assertEqual(prices.radiator_prices('قیمت ایل پرمو سه پره و ویتوریا ۷ پره'),
                         [('رادیاتور ایل پرمو 3 پره', 62960700), ('رادیاتور ویتوریا 7 پره', 124124000)])
        self.assertEqual(prices.radiator_prices('قیمت ۷ پره ویتوریا'),
                         [('رادیاتور ویتوریا 7 پره', 124124000)])


if __name__ == '__main__':
    unittest.main()
