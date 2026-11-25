"""Make shorts.env (the YouTube upload keys) for the server. Run once on your Mac.

  pip3 install google-auth-oauthlib google-api-python-client
  python3 make_env.py

The client_secret*.json from Google Cloud is picked up from this folder or ~/Downloads.
For each channel a browser tab opens: pick that channel's account and click Allow.
On a server: scp shorts.env ubuntu@SERVER_IP:~/.shorts.env  (running on the Mac: leave it where it is)
shorts.env is git-ignored; never commit it.
"""
import glob
import json
import os

from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/youtube.upload",
          "https://www.googleapis.com/auth/youtube.readonly"]
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "shorts.env")

cands = glob.glob(os.path.join(HERE, "client_secret*.json")) + \
    glob.glob(os.path.expanduser("~/Downloads/client_secret*.json"))
if not cands:
    raise SystemExit("client_secret*.json not found here or in ~/Downloads")
SECRET = max(cands, key=os.path.getmtime)
print("Using", SECRET)
cfg = json.load(open(SECRET))
cfg = cfg.get("installed") or cfg.get("web")
env = {"YT_CLIENT_ID": cfg["client_id"], "YT_CLIENT_SECRET": cfg["client_secret"]}

for slug in sorted(os.listdir(os.path.join(HERE, "channels"))):
    name = json.load(open(os.path.join(HERE, "channels", slug, "channel.json")))["name"]
    if input(f"\nNext: '{name}'. Enter = authorise, s = skip: ").strip().lower() == "s":
        continue
    flow = InstalledAppFlow.from_client_secrets_file(SECRET, SCOPES)
    creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")
    me = build("youtube", "v3", credentials=creds).channels().list(part="snippet", mine=True).execute()
    got = me["items"][0]["snippet"]["title"] if me.get("items") else None
    print(f"  authorised channel: {got}")
    if got != name and input(f"  expected '{name}'. Use it anyway? [y/N] ").lower() != "y":
        continue
    env[f"YT_REFRESH_TOKEN_{slug.upper()}"] = creds.refresh_token

with open(OUT, "w") as f:
    f.writelines(f"{k}={v}\n" for k, v in env.items())
os.chmod(OUT, 0o600)
print(f"\nSaved {OUT}. Copy it to the server:  scp shorts.env ubuntu@SERVER_IP:~/.shorts.env")
