import io
import hashlib
import unittest
from types import SimpleNamespace
from urllib.error import HTTPError
from unittest.mock import Mock

import catalog_pdf


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.config = {}
        self.calls = []
        self.bot = SimpleNamespace(
            handle_text=Mock(), handle_callback=Mock(), main_menu=Mock(return_value=[]),
            cfg=lambda k: self.config.get(k), setcfg=lambda k,v:self.config.update({k:v}),
            get_session=Mock(return_value=(None,{})), ensure_user=Mock(), answer_cb=Mock(), send=Mock())
        def api(method, data, **kwargs):
            self.calls.append((method,data,kwargs))
            return {'document':{'file_id':'telegram-approved-document'}} if method=='sendDocument' else {}
        self.bot.api = api
        catalog_pdf.install(self.bot)

    def msg(self,text,kind='private'):
        return {'chat':{'id':101,'type':kind},'from':{'id':101,'first_name':'Customer'},'text':text}

    def test_exact_full_pdf(self):
        data=catalog_pdf.document_bytes()
        self.assertEqual(len(data),16083824)
        self.assertEqual(hashlib.sha256(data).hexdigest(),'51f3192640cd090bd4e842cf248332563bbee31991d4b07f5d38d4308f0624d8')

    def test_requests_and_non_requests(self):
        yes=['/catalog','/pdf','/catalog@Azmashahraki_bot',catalog_pdf.BUTTON,'کاتالوگ را بفرست','لیست قیمت کامل رو ارسال کن','pdf میخوام','فایلش رو بفرست','پی‌دی‌اف را بده']
        no=['قیمت هایسنس HIH-24TG چنده؟','مشخصات کولر چیست؟','کاتالوگ نفرست','کاتالوگ لازم ندارم','کاتالوگ نمیخوام','کاتالوگ نده','/teach ارسال | کاتالوگ را بفرست']
        for text in yes:self.assertTrue(catalog_pdf.requests_pdf(text),text)
        for text in no:self.assertFalse(catalog_pdf.requests_pdf(text),text)

    def test_upload_then_versioned_telegram_cache(self):
        self.bot.handle_text(self.msg('کاتالوگ را بفرست'))
        self.bot.handle_text(self.msg('/catalog'))
        docs=[c for c in self.calls if c[0]=='sendDocument']
        self.assertEqual(len(docs),2)
        self.assertEqual(docs[0][2]['files']['document'][1],catalog_pdf.document_bytes())
        self.assertEqual(docs[1][1]['document'],'telegram-approved-document')
        self.assertNotIn('files',docs[1][2])

    def test_private_only_and_existing_flows(self):
        self.bot.handle_text(self.msg('کاتالوگ را بفرست','group'))
        self.bot.handle_callback({'id':'cb','from':{'id':101},'data':catalog_pdf.CALLBACK,'message':{'chat':{'id':102,'type':'group'}}})
        self.assertFalse(any(c[0]=='sendDocument' for c in self.calls))
        self.bot.get_session.return_value=('admin_teach',{})
        self.bot.handle_text(self.msg('ارسال | کاتالوگ را بفرست'))
        self.assertFalse(any(c[0]=='sendDocument' for c in self.calls))

    def test_callback_sends_document(self):
        self.bot.handle_callback({'id':'cb','from':{'id':101},'data':catalog_pdf.CALLBACK,'message':{'chat':{'id':101,'type':'private'}}})
        self.assertEqual([c[0] for c in self.calls],['sendChatAction','sendDocument'])
        self.bot.answer_cb.assert_called_once_with('cb')

    def test_cached_bad_file_falls_back_but_blocked_chat_does_not_retry(self):
        key='catalog_pdf_file_id_'+catalog_pdf.SHA256[:16]
        self.config[key]='expired'
        original=self.bot.api
        def api(method,data,**kwargs):
            if method=='sendDocument' and data.get('document')=='expired':
                raise HTTPError('https://telegram.invalid',400,'invalid file',{},io.BytesIO(b''))
            return original(method,data,**kwargs)
        self.bot.api=api
        self.bot.handle_text(self.msg('/catalog'))
        self.assertEqual(self.config[key],'telegram-approved-document')
        self.assertIn('files',[c for c in self.calls if c[0]=='sendDocument'][0][2])
        self.calls.clear()
        def blocked(method,data,**kwargs):
            if method=='sendDocument':raise HTTPError('https://telegram.invalid',403,'blocked',{},io.BytesIO(b''))
            return original(method,data,**kwargs)
        self.bot.api=blocked
        self.bot.handle_text(self.msg('/catalog'))
        self.assertFalse(any('files' in c[2] for c in self.calls))
        self.bot.send.assert_called_once()

    def test_menu_offer_and_ordinary_model_question(self):
        for _ in range(2):
            menu=self.bot.main_menu(101)
            self.assertEqual(sum(b.get('callback_data')==catalog_pdf.CALLBACK for row in menu for b in row),1)
        self.assertTrue(self.bot.catalog_should_offer('قیمت هایسنس چنده؟'))
        self.bot.handle_text(self.msg('قیمت هایسنس چنده؟'))
        self.assertFalse(any(c[0]=='sendDocument' for c in self.calls))


if __name__=='__main__':unittest.main()
