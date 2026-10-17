import json
import threading
import time
import urllib.parse
import urllib.request
import urllib.error
from datetime import datetime

from kivy.clock import Clock
from kivy.animation import Animation
from kivy.metrics import dp
from kivy.properties import StringProperty
from kivy.uix.screenmanager import ScreenManager, FadeTransition
from kivymd.app import MDApp
from kivymd.uix.screen import MDScreen
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.floatlayout import MDFloatLayout
from kivymd.uix.label import MDLabel
from kivymd.uix.button import MDRaisedButton, MDFlatButton, MDIconButton
from kivymd.uix.textfield import MDTextField
from kivymd.uix.card import MDCard
from kivymd.uix.toolbar import MDTopAppBar
from kivymd.uix.list import MDList, TwoLineAvatarIconListItem, IconLeftWidget
from kivymd.uix.scrollview import MDScrollView
from kivymd.uix.dialog import MDDialog
from kivymd.uix.spinner import MDSpinner

APP_NAME = "Chatterly"
CONFIG_FILE = "firebase_config.json"


def http_json(url, method="GET", payload=None, headers=None):
    # Fix: Always include Content-Type so Firebase can read the JSON payload
    h = {"Content-Type": "application/json"}
    if headers:
        h.update(headers)
        
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, method=method, headers=h)
    try:
        with urllib.request.urlopen(request, timeout=12) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        try:
            message = json.loads(exc.read().decode("utf-8"))
            error = message.get("error", message)
        except Exception:
            error = str(exc)
        raise RuntimeError(str(error))
    except Exception as exc:
        raise RuntimeError(str(exc))


class Firebase:
    def __init__(self, config):
        self.api_key = config["api_key"].strip()
        self.db_url = config["database_url"].strip().rstrip("/")
        self.token = None
        self.uid = None
        self.email = None

    def auth(self, email, password, signup=False):
        mode = "signUp" if signup else "signInWithPassword"
        url = f"https://identitytoolkit.googleapis.com/v1/accounts:{mode}?key={self.api_key}"
        result = http_json(url, "POST", {
            "email": email, "password": password, "returnSecureToken": True
        })
        self.token = result["idToken"]
        self.uid = result["localId"]
        self.email = result.get("email", email)
        return result

    def db(self, path, method="GET", payload=None):
        query = urllib.parse.urlencode({"auth": self.token}) if self.token else ""
        url = f"{self.db_url}/{path.strip('/')}.json"
        if query:
            url += "?" + query
        return http_json(url, method, payload)

    def set_profile(self, username, phone=""):
        self.db(f"users/{self.uid}", "PUT", {
            "uid": self.uid, "username": username, "email": self.email,
            "phone": phone, "created_at": {".sv": "timestamp"}
        })

    def find_user(self, username):
        users = self.db("users") or {}
        needle = username.strip().lower()
        for uid, profile in users.items():
            if uid != self.uid and (profile.get("username", "").lower() == needle or
                                    profile.get("email", "").lower() == needle):
                return profile
        return None

    def conversations(self):
        return self.db(f"user_chats/{self.uid}") or {}

    def get_messages(self, chat_id):
        data = self.db(f"messages/{chat_id}") or {}
        return sorted(data.values(), key=lambda x: int(x.get("timestamp", 0)))

    def send_message(self, chat_id, text):
        self.db(f"messages/{chat_id}", "POST", {
            "sender_uid": self.uid,
            "text": text,
            "timestamp": {".sv": "timestamp"}
        })


class ChatScreen(MDScreen):
    pass


class ChatterlyApp(MDApp):
    current_chat_id = StringProperty("")
    current_chat_name = StringProperty("")

    def build(self):
        self.title = APP_NAME
        self.theme_cls.theme_style = "Light"
        self.theme_cls.primary_palette = "Teal"
        self.theme_cls.accent_palette = "Blue"
        self.firebase = None
        self.poll_event = None
        self.dialog = None
        self.chat_peer_uid = ""
        self.chat_items = []
        self.manager = ScreenManager(transition=FadeTransition(duration=.18))
        self.manager.add_widget(self.make_auth_screen())
        self.manager.add_widget(self.make_home_screen())
        self.manager.add_widget(self.make_chat_screen())
        self.manager.current = "auth"
        return self.manager

    def read_config(self):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    def make_auth_screen(self):
        screen = MDScreen(name="auth")
        root = MDBoxLayout(orientation="vertical", padding=[dp(28), dp(32), dp(28), dp(24)], spacing=dp(14))
        root.add_widget(MDLabel(text="Chatterly", font_style="H3", bold=True, adaptive_height=True,
                                theme_text_color="Custom", text_color=(0.02, .48, .43, 1)))
        root.add_widget(MDLabel(text="Private conversations. Real people.", adaptive_height=True,
                                theme_text_color="Secondary"))
        self.email_field = MDTextField(hint_text="Email address", mode="rectangle")
        self.password_field = MDTextField(hint_text="Password", mode="rectangle", password=True)
        self.username_field = MDTextField(hint_text="Username (for new account)", mode="rectangle")
        root.add_widget(self.email_field)
        root.add_widget(self.password_field)
        root.add_widget(self.username_field)
        root.add_widget(MDRaisedButton(text="SIGN IN", size_hint_x=1, height=dp(48),
                                       on_release=lambda *_: self.do_auth(False)))
        root.add_widget(MDFlatButton(text="Create new account", pos_hint={"center_x": .5},
                                     on_release=lambda *_: self.do_auth(True)))
        root.add_widget(MDLabel(text="Chats only work after Firebase is configured in firebase_config.json.",
                                theme_text_color="Hint", font_style="Caption", adaptive_height=True))
        screen.add_widget(root)
        return screen

    def make_home_screen(self):
        screen = MDScreen(name="home")
        root = MDBoxLayout(orientation="vertical")
        root.add_widget(MDTopAppBar(title="Chatterly", right_action_items=[
            ["account-plus", lambda *_: self.open_find_user()],
            ["refresh", lambda *_: self.load_chats()],
            ["logout", lambda *_: self.logout()]
        ]))
        self.home_status = MDLabel(text="Your conversations", padding=[dp(18), dp(8)],
                                   adaptive_height=True, theme_text_color="Secondary")
        root.add_widget(self.home_status)
        scroll = MDScrollView()
        self.chat_list = MDList()
        scroll.add_widget(self.chat_list)
        root.add_widget(scroll)
        screen.add_widget(root)
        return screen

    def make_chat_screen(self):
        screen = MDScreen(name="chat")
        root = MDBoxLayout(orientation="vertical", spacing=dp(4))
        self.chat_toolbar = MDTopAppBar(title="Chat", left_action_items=[["arrow-left", lambda *_: self.back_home()]])
        root.add_widget(self.chat_toolbar)
        scroll = MDScrollView()
        self.message_stack = MDBoxLayout(orientation="vertical", padding=dp(12), spacing=dp(8),
                                         size_hint_y=None)
        self.message_stack.bind(minimum_height=self.message_stack.setter("height"))
        scroll.add_widget(self.message_stack)
        root.add_widget(scroll)
        composer = MDBoxLayout(size_hint_y=None, height=dp(64), padding=[dp(8), dp(6)], spacing=dp(8))
        self.message_field = MDTextField(hint_text="Message", mode="rectangle", multiline=False)
        composer.add_widget(self.message_field)
        composer.add_widget(MDIconButton(icon="send", on_release=lambda *_: self.send_message()))
        root.add_widget(composer)
        screen.add_widget(root)
        return screen

    def do_auth(self, signup):
        self.email_field.focus = False
        self.password_field.focus = False
        self.username_field.focus = False
        Clock.schedule_once(lambda dt: self._execute_auth(signup), 0.05)

    def _execute_auth(self, signup):
        config = self.read_config()
        if not config or not config.get("api_key") or not config.get("database_url"):
            self.alert("Firebase setup needed", "Create firebase_config.json using the instructions in README.md.")
            return
        email = self.email_field.text.strip()
        password = self.password_field.text
        username = self.username_field.text.strip()
        if not email or not password or (signup and not username):
            self.alert("Missing information", "Enter email and password. New accounts also need a username.")
            return
        self.home_status.text = "Connecting…"
        def task():
            try:
                self.firebase = Firebase(config)
                self.firebase.auth(email, password, signup)
                if signup:
                    self.firebase.set_profile(username)
                else:
                    profile = self.firebase.db(f"users/{self.firebase.uid}") or {}
                    if not profile:
                        self.firebase.set_profile(email.split("@")[0])
                Clock.schedule_once(lambda dt: self.auth_success(), 0)
            except Exception as e:
                error_msg = str(e)
                Clock.schedule_once(lambda dt: self.alert("Could not sign in", error_msg), 0)
        threading.Thread(target=task, daemon=True).start()

    def auth_success(self):
        self.manager.current = "home"
        self.load_chats()
        self.start_polling()

    def load_chats(self):
        if not self.firebase:
            return
        def task():
            try:
                chats = self.firebase.conversations()
                rows = []
                for chat_id, info in chats.items():
                    rows.append((chat_id, info.get("name", "Conversation"), info.get("peer_uid", "")))
                Clock.schedule_once(lambda dt: self.render_chats(rows), 0)
            except Exception as e:
                error_msg = str(e)
                Clock.schedule_once(lambda dt: self.alert("Could not load chats", error_msg), 0)
        threading.Thread(target=task, daemon=True).start()

    def render_chats(self, rows):
        self.chat_list.clear_widgets()
        if not rows:
            self.chat_list.add_widget(TwoLineAvatarIconListItem(
                text="No conversations yet", secondary_text="Tap the + icon to find a real user."
            ))
            return
        for chat_id, name, peer_uid in rows:
            item = TwoLineAvatarIconListItem(text=name, secondary_text="Tap to open conversation")
            item.add_widget(IconLeftWidget(icon="account-circle"))
            item.bind(on_release=lambda instance, c=chat_id, n=name, p=peer_uid: self.open_chat(c, n, p))
            self.chat_list.add_widget(item)

    def open_find_user(self):
        self.find_field = MDTextField(hint_text="Exact username or email", mode="rectangle")
        self.dialog = MDDialog(title="Find a real person",
                               type="custom",
                               content_cls=self.find_field,
                               buttons=[
                                   MDFlatButton(text="CANCEL", on_release=lambda *_: self.dialog.dismiss()),
                                   MDRaisedButton(text="FIND", on_release=lambda *_: self.find_user())
                               ])
        self.dialog.open()

    def find_user(self):
        if hasattr(self, 'find_field'):
            self.find_field.focus = False
        Clock.schedule_once(lambda dt: self._execute_find_user(), 0.05)

    def _execute_find_user(self):
        query = self.find_field.text.strip() if hasattr(self, 'find_field') else ""
        if self.dialog:
            self.dialog.dismiss()
        if not query:
            return
        def task():
            try:
                peer = self.firebase.find_user(query)
                if not peer:
                    Clock.schedule_once(lambda dt: self.alert("No user found",
                        "No registered user matches that username or email. Ask them to create an account first."), 0)
                    return
                peer_uid = peer["uid"]
                ids = sorted([self.firebase.uid, peer_uid])
                chat_id = "_".join(ids)
                my_name = self.firebase.db(f"users/{self.firebase.uid}").get("username", self.firebase.email)
                peer_name = peer.get("username", peer.get("email", "Chat"))
                self.firebase.db(f"user_chats/{self.firebase.uid}/{chat_id}", "PUT",
                                 {"peer_uid": peer_uid, "name": peer_name})
                self.firebase.db(f"user_chats/{peer_uid}/{chat_id}", "PUT",
                                 {"peer_uid": self.firebase.uid, "name": my_name})
                Clock.schedule_once(lambda dt: self.open_chat(chat_id, peer_name, peer_uid), 0)
            except Exception as e:
                error_msg = str(e)
                Clock.schedule_once(lambda dt: self.alert("Search failed", error_msg), 0)
        threading.Thread(target=task, daemon=True).start()

    def open_chat(self, chat_id, name, peer_uid):
        self.current_chat_id = chat_id
        self.current_chat_name = name
        self.chat_peer_uid = peer_uid
        self.chat_toolbar.title = name
        self.manager.current = "chat"
        self.refresh_messages()
        if self.poll_event:
            self.poll_event.cancel()
        self.poll_event = Clock.schedule_interval(lambda dt: self.refresh_messages(), 2.5)

    def refresh_messages(self):
        if not self.firebase or not self.current_chat_id:
            return
        chat_id = self.current_chat_id
        def task():
            try:
                messages = self.firebase.get_messages(chat_id)
                Clock.schedule_once(lambda dt: self.render_messages(messages, chat_id), 0)
            except Exception:
                pass
        threading.Thread(target=task, daemon=True).start()

    def render_messages(self, messages, chat_id):
        if chat_id != self.current_chat_id:
            return
        self.message_stack.clear_widgets()
        for msg in messages:
            mine = msg.get("sender_uid") == self.firebase.uid
            bubble = MDCard(orientation="vertical", padding=dp(10), radius=[dp(14)],
                            size_hint=(.82, None), adaptive_height=True,
                            md_bg_color=(.82, .96, .91, 1) if mine else (.94, .95, .96, 1),
                            pos_hint={"right": 1} if mine else {"x": 0})
            bubble.add_widget(MDLabel(text=msg.get("text", ""), adaptive_height=True,
                                     theme_text_color="Primary"))
            self.message_stack.add_widget(bubble)
        if not messages:
            self.message_stack.add_widget(MDLabel(text="Say hello 👋", adaptive_height=True,
                                                  theme_text_color="Hint", halign="center"))
        Animation(opacity=1, duration=.12).start(self.message_stack)

    def send_message(self):
        self.message_field.focus = False
        Clock.schedule_once(lambda dt: self._execute_send_message(), 0.05)

    def _execute_send_message(self):
        text = self.message_field.text.strip()
        if not text or not self.current_chat_id:
            return
        self.message_field.text = ""
        self.message_field.focus = False
        def task():
            try:
                self.firebase.send_message(self.current_chat_id, text)
                self.refresh_messages()
            except Exception as e:
                error_msg = str(e)
                Clock.schedule_once(lambda dt: self.alert("Message not sent", error_msg), 0)
        threading.Thread(target=task, daemon=True).start()

    def back_home(self):
        if self.poll_event:
            self.poll_event.cancel()
            self.poll_event = None
        self.current_chat_id = ""
        self.manager.current = "home"
        self.load_chats()

    def start_polling(self):
        if self.poll_event:
            self.poll_event.cancel()
        self.poll_event = Clock.schedule_interval(
            lambda dt: self.load_chats() if self.manager.current == "home" else None, 8)

    def logout(self):
        if self.poll_event:
            self.poll_event.cancel()
            self.poll_event = None
        self.firebase = None
        self.manager.current = "auth"

    def alert(self, title, text):
        self.dialog = MDDialog(title=title, text=text,
                               buttons=[MDFlatButton(text="OK", on_release=lambda *_: self.dialog.dismiss())])
        self.dialog.open()


if __name__ == "__main__":
    ChatterlyApp().run()