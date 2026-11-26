"""Upload a rendered Short or long-form video to YouTube with the Data API v3.

Long-form uploads pass extra= (the chapter list, placed right after the description so YouTube
turns it into chapters) and thumbnail= (custom thumbnail; needs a verified channel, so a failure
only logs a warning).

Env vars:
  YT_CLIENT_ID, YT_CLIENT_SECRET     OAuth Desktop client (shared by all channels)
  YT_REFRESH_TOKEN_<CHANNEL>         one per channel folder, e.g. YT_REFRESH_TOKEN_CYBER
"""
import datetime as dt
import os

SCOPES = ["https://www.googleapis.com/auth/youtube.upload",
          "https://www.googleapis.com/auth/youtube.readonly"]


def client(channel_slug):
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    key = f"YT_REFRESH_TOKEN_{channel_slug.upper()}"
    token = os.environ.get(key)
    if not token:
        raise SystemExit(f"Missing secret {key}")
    creds = Credentials(None, refresh_token=token, client_id=os.environ["YT_CLIENT_ID"],
                        client_secret=os.environ["YT_CLIENT_SECRET"],
                        token_uri="https://oauth2.googleapis.com/token", scopes=SCOPES)
    creds.refresh(Request())  # raises RefreshError if the token was revoked/expired
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def build_description(script, channel, extra=None):
    parts = [script["description"]] + ([extra] if extra else []) + [" ".join(channel.get("hashtags", []))]
    if script.get("credits"):
        parts.append("Image credits:\n" + "\n".join(script["credits"]))
    if script.get("sources"):
        parts.append("Sources:\n" + "\n".join(script["sources"]))
    if channel.get("description_footer"):
        parts.append(channel["description_footer"])
    return "\n\n".join(parts)[:4900]


def upload(video_path, script, channel, channel_slug, extra=None, thumbnail=None, publish_at=None):
    """publish_at: aware datetime -> uploaded private and YouTube publishes it then."""
    from googleapiclient.http import MediaFileUpload

    yt = client(channel_slug)
    me = yt.channels().list(part="snippet", mine=True).execute()
    if me.get("items"):
        print("Uploading to channel:", me["items"][0]["snippet"]["title"])
    tags = list(dict.fromkeys(script.get("tags", []) + channel.get("default_tags", [])))
    while sum(len(t) + 3 for t in tags) > 480:
        tags.pop()
    body = {
        "snippet": {
            "title": script["title"][:100],
            "description": build_description(script, channel, extra),
            "tags": tags,
            "categoryId": channel.get("category_id", "28"),
            "defaultLanguage": "en",
            "defaultAudioLanguage": "en",
        },
        "status": {
            "privacyStatus": channel.get("privacy", "public"),
            "selfDeclaredMadeForKids": channel.get("made_for_kids", False),
            "containsSyntheticMedia": channel.get("contains_synthetic_media", False),
        },
    }
    if publish_at:  # YouTube only schedules private videos
        body["status"]["privacyStatus"] = "private"
        body["status"]["publishAt"] = publish_at.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    req = yt.videos().insert(part="snippet,status", body=body,
                             media_body=MediaFileUpload(video_path, mimetype="video/mp4",
                                                        chunksize=8 * 1024 * 1024, resumable=True))
    resp = None
    while resp is None:
        status, resp = req.next_chunk()
        if status:
            print(f"  {int(status.progress() * 100)}%")
    if thumbnail:
        mime = "image/jpeg" if thumbnail.lower().endswith((".jpg", ".jpeg")) else "image/png"
        try:
            yt.thumbnails().set(videoId=resp["id"],
                                media_body=MediaFileUpload(thumbnail, mimetype=mime)).execute()
            print("  thumbnail set")
        except Exception as e:  # 403 until the channel is phone-verified (custom thumbnails)
            print(f"::warning::[{channel_slug}] custom thumbnail not set for {resp['id']}: {e}")
    st = resp.get("status", {})
    return resp["id"], ("scheduled " + st["publishAt"]) if st.get("publishAt") else st.get("privacyStatus")
