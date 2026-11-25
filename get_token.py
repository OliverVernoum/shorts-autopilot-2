"""Run ONCE per channel on your own computer to authorise uploads.

  pip install google-auth-oauthlib google-api-python-client
  python get_token.py client_secret.json

A browser opens: sign in, and when asked "Choose an account or brand account",
pick the YouTube CHANNEL you want this token for. Copy the printed refresh token into
the matching GitHub secret (YT_REFRESH_TOKEN_CYBER, YT_REFRESH_TOKEN_GAMING, ...).
"""
import json
import sys

from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/youtube.upload",
          "https://www.googleapis.com/auth/youtube.readonly"]

secret = sys.argv[1] if len(sys.argv) > 1 else "client_secret.json"
flow = InstalledAppFlow.from_client_secrets_file(secret, SCOPES)
creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")
me = build("youtube", "v3", credentials=creds).channels().list(part="snippet", mine=True).execute()
name = me["items"][0]["snippet"]["title"] if me.get("items") else "(no channel on this account!)"
cfg = json.load(open(secret))
cfg = cfg.get("installed") or cfg.get("web")
print("\nAuthorised channel :", name)
print("YT_CLIENT_ID       :", cfg["client_id"])
print("YT_CLIENT_SECRET   :", cfg["client_secret"])
print("YT_REFRESH_TOKEN_* :", creds.refresh_token)
