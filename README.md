# Chatterly — KivyMD real-person chat MVP

This is a starter app, not a fake-chat demo. It has no AI characters or preloaded fake contacts. Two real people can chat once both have accounts in the same Firebase project.

## What is included

- KivyMD mobile-style interface, chat list, message bubbles, search/add user, login and signup.
- Firebase Authentication email/password.
- Firebase Realtime Database for profiles, conversations, and messages.
- Message refresh polling every 2.5 seconds (a simple MVP; not a true persistent realtime socket).
- Empty states instead of fabricated users.

## Important limitations

- This MVP finds users by exact username or email. It does **not** yet import Android phone contacts or verify phone numbers.
- It is not WhatsApp and cannot send messages to WhatsApp accounts. Other people must install this app and register.
- No end-to-end encryption, voice/video calls, push notifications, media uploads, read receipts, or production abuse controls yet.
- The provided database rules are a starting point; test and harden them before real deployment. Do not use public read/write rules.
- Do not put Firebase service-account keys in the client app. This client uses Firebase Auth ID tokens.

## 1. Install a compatible Python environment

Because your current Python is 3.14.7 and your Kivy install failed, start with Python 3.12 for this KivyMD 1.2.0 project.

In PowerShell, from this folder:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python main.py
```

If `py -3.12` says Python 3.12 is missing, install Python 3.12 from python.org and select “Add python.exe to PATH”.

## 2. Configure Firebase

1. Open https://console.firebase.google.com/ and create a project.
2. In Project settings, create/register a Web app and copy its Web API key.
3. In Build → Authentication → Sign-in method, enable **Email/Password**.
4. In Build → Realtime Database, create a database.
5. Copy `firebase_config.example.json` to `firebase_config.json`.
6. Put your Web API key into `api_key` and the exact database URL into `database_url`.
7. In Realtime Database → Rules, paste the contents of `database.rules.json` and publish.

Do not publish `firebase_config.json` in a public repository. The Web API key is not a server secret by itself, but it should still be configured correctly and protected with Firebase rules and API restrictions where applicable.

## 3. Test with two real people

1. Run the app and create an account with a unique username.
2. Have a friend run the same app with the same Firebase project and create their own account.
3. In the home screen, tap the + icon and search for their exact username or email.
4. Send a message. Your friend can open the conversation and reply.

Both devices need internet access and must use the same Firebase project.

## Android contacts and APK packaging

This code currently uses registered usernames/emails instead of reading your phone's contacts. Real Android contact import needs Android runtime permission (`READ_CONTACTS`), contact-provider access, and a privacy-conscious phone-number matching/verification design. For Android APK builds, Kivy normally uses python-for-android/Buildozer; building on Windows usually means using a Linux build environment or a supported cloud build. The desktop version is for testing the UI and backend first.

## Next production steps

- Phone number verification and contact matching (with consent; never upload the entire address book without permission).
- Better database rules and server-side validation.
- True realtime listener, push notifications, delivery/read states.
- End-to-end encryption and key management.
- Block/report controls, rate limiting, account deletion, privacy policy, backups.
