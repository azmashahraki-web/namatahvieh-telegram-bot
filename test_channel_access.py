import importlib
import io
import json
import time
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch
from urllib.error import HTTPError

import ai_assistant
import bot
import channel_access


class Response:
    def __init__(self, value):
        self.value = value

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def read(self):
        return json.dumps(self.value).encode()


class ChannelAccessTests(unittest.TestCase):
    def setUp(self):
        importlib.reload(bot)
        self.config = {"owner_id": "1", "bot_username": "ShopTest_bot", "channel_id": "@shoptest",
                       "ai_enabled": "1", "ai_provider": "gemini"}
        self.sessions = {}
        self.users = {}
        self.calls = []
        self.models = []
        self.history = []
        self.channel = {"id": -10042, "type": "channel", "username": "shoptest", "title": "فروشگاه"}
        self.rights = {"status": "administrator", "can_post_messages": True, "can_edit_messages": True}
        self.pin_fails = False
        bot.db = self.database
        bot.api = self.telegram
        # No external requests or real secrets are used in these integration tests.
        bot.SUPABASE_URL = "https://test.invalid"
        self.network = patch.object(ai_assistant, "urlopen", self.ai_network)
        self.network.start()
        self.addCleanup(self.network.stop)
        self.key = patch.object(ai_assistant, "GEMINI_API_KEY", "test-key")
        self.key.start()
        self.addCleanup(self.key.stop)
        with redirect_stdout(io.StringIO()):
            ai_assistant.install(bot)
            channel_access.install(bot)

    def database(self, action, payload=None):
        p = payload or {}
        uid = p.get("telegram_id")
        if action == "cfg_get":
            return {"value": self.config.get(p["k"])}
        if action == "cfg_set":
            self.config[p["k"]] = p["v"]
        elif action == "ensure_user":
            self.users.setdefault(uid, dict(p))
            return self.users[uid]
        elif action == "user_get":
            return self.users.get(uid)
        elif action == "session_get":
            return self.sessions.get(uid)
        elif action == "session_set":
            self.sessions[uid] = {"step": p["step"], "data": p["data"]}
        elif action == "session_delete":
            self.sessions.pop(uid, None)
        elif action == "lead_insert":
            self.fail("A chat message was incorrectly treated as a sales form")

    def telegram(self, method, data=None, **kwargs):
        data = data or {}
        self.calls.append((method, data))
        if method == "getChat":
            return dict(self.channel)
        if method == "getMe":
            return {"id": 999, "username": "ShopTest_bot"}
        if method == "getChatMember":
            return self.rights
        if method == "sendMessage":
            return {"message_id": 77}
        if method == "editMessageText":
            raise HTTPError("https://test.invalid", 400, "unchanged", {}, io.BytesIO(b'{"description":"Bad Request: message is not modified"}'))
        if method == "pinChatMessage" and self.pin_fails:
            raise RuntimeError("temporary failure")
        return True

    def ai_network(self, request, **kwargs):
        payload = json.loads(request.data)
        if request.full_url.endswith("/rpc/bot_ai_api"):
            action = payload["action"]
            if action == "history_append":
                self.history.append(payload["payload"])
            return Response([] if action in ("knowledge_for_ai", "history_get") else {})
        if ":generateContent" in request.full_url:
            self.models.append(payload)
            return Response({"candidates": [{"content": {"parts": [{"text": "شهر و شرایط محل نصب را بفرمایید."}]}}]})
        self.fail("Unexpected outbound request")

    def message(self, text, uid=2):
        return {"chat": {"id": uid, "type": "private"}, "from": {"id": uid, "first_name": "مشتری"}, "text": text}

    def click_publish(self, uid=1, target="-10042"):
        bot.handle_callback({"id": "test", "from": {"id": uid}, "message": {"chat": {"id": uid, "type": "private"}},
                             "data": "panel_publish:" + target})

    def channel_posts(self):
        return [d for m, d in self.calls if m == "sendMessage" and d["chat_id"] < 0]

    def member_update(self):
        return {"chat": self.channel, "old_chat_member": {"status": "left"},
                "new_chat_member": {"status": "member", "user": {"id": 2, "first_name": "مشتری"}}}

    def test_start_clears_form_and_question_reaches_ai(self):
        self.sessions[2] = {"step": "quote_phone", "data": {"product": "AC"}}
        bot.handle_text(self.message("/start channel"))
        self.assertNotIn(2, self.sessions)
        welcome = [d for m, d in self.calls if m == "sendMessage"][-1]
        self.assertIn("خوش آمدی", welcome["text"])
        self.assertTrue(welcome["reply_markup"]["is_persistent"])
        bot.handle_text(self.message("برای ۱۲۰ متر چه کولری بخرم؟"))
        self.assertEqual(len(self.models), 1)
        self.assertEqual(len(self.history), 2)

    def test_referral_and_quote_links_preserve_their_routes(self):
        bot.handle_text(self.message("/start r_friend", uid=3))
        self.assertEqual(self.users[3]["start_payload"], "r_friend")
        bot.handle_text(self.message("/start channel_quote"))
        self.assertEqual(self.sessions[2]["step"], "quote_product")

    def test_chat_button_exits_form(self):
        self.sessions[2] = {"step": "ac_area", "data": {}}
        bot.handle_text(self.message(channel_access.CHAT_BUTTON))
        self.assertNotIn(2, self.sessions)
        bot.handle_text(self.message("سلام"))
        self.assertEqual(len(self.models), 1)

    def test_preview_never_publishes(self):
        bot.handle_text(self.message("/start channel_setup", uid=1))
        self.assertEqual(self.channel_posts(), [])
        self.assertTrue(any("panel_publish:" in json.dumps(d) for _, d in self.calls))

    def test_non_owner_and_changed_target_cannot_publish(self):
        self.click_publish(uid=2)
        self.click_publish(target="-10099")
        self.assertEqual(self.channel_posts(), [])

    def test_missing_pin_permission_blocks_publication(self):
        self.rights["can_edit_messages"] = False
        self.click_publish()
        self.assertEqual(self.channel_posts(), [])

    def test_retries_after_pin_failure_do_not_duplicate_posts(self):
        self.pin_fails = True
        with redirect_stdout(io.StringIO()):
            self.click_publish()
        self.pin_fails = False
        self.click_publish()
        self.assertEqual(len(self.channel_posts()), 1)
        self.assertEqual(sum(m == "pinChatMessage" for m, _ in self.calls), 2)
        self.assertEqual(self.channel_posts()[0]["reply_markup"]["inline_keyboard"][0][0]["url"],
                         "https://t.me/ShopTest_bot?start=channel")

    def test_new_subscriber_is_not_contacted_until_bot_started(self):
        bot.handle_chat_member(self.member_update())
        self.assertFalse(any(m == "sendMessage" for m, _ in self.calls))
        self.users[2] = {"telegram_id": 2}
        bot.handle_chat_member(self.member_update())
        bot.handle_chat_member(self.member_update())
        self.assertEqual(sum(m == "sendMessage" for m, _ in self.calls), 1)

    def test_unrelated_channel_and_member_promotion_are_ignored(self):
        self.users[2] = {"telegram_id": 2}
        update = self.member_update()
        update["chat"] = {"id": -10099, "username": "other"}
        bot.handle_chat_member(update)
        update = self.member_update()
        update["old_chat_member"]["status"] = "member"
        update["new_chat_member"]["status"] = "administrator"
        bot.handle_chat_member(update)
        self.assertFalse(any(m == "sendMessage" for m, _ in self.calls))

    def test_join_request_respects_contact_window_without_approving(self):
        update = {"chat": self.channel, "from": {"id": 2}, "user_chat_id": 7, "date": time.time() - 300}
        bot.handle_chat_join_request(update)
        self.assertEqual(len(self.calls), 0)
        update["date"] = time.time()
        bot.handle_chat_join_request(update)
        self.assertEqual([(m, d["chat_id"]) for m, d in self.calls], [("sendMessage", 7)])


if __name__ == "__main__":
    unittest.main()
