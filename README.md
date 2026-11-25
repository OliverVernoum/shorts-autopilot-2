# Shorts Autopilot

Automatically makes and uploads YouTube Shorts for several faceless channels.

| Channel folder | Channel | Topic | Uploads (UTC) |
|---|---|---|---|
| `channels/cyber`  | Plain Text Threats | One cybersecurity concept per Short | every 2 hours at :07 (even UTC hours) |
| `channels/gaming` | Boss Room Archive | Gaming facts, mechanics and history | 01:07, 07:07, 13:07, 19:07 |
| `channels/tech` | Pocket Silicon | How AI and everyday tech work | 03:07, 09:07, 15:07, 21:07 |

## How it works

```
Claude scheduled tasks        ── researches trends, writes fact-checked scripts ──► channels/<ch>/queue/*.json
Server cron (server/tick.sh)  ── next script → edge-tts voice → animated 1080x1920 video → YouTube API upload
                                  └─► moves script to channels/<ch>/published/ with the video URL
```

- `shorts/render.py`: voiceover (edge-tts, word-timed captions), animated backgrounds and eight scene types (`title`, `big`, `terminal`, `steps`, `versus`, `bars`, `quiz`, `timeline`), then ffmpeg. Colours and glyphs change per video so videos don't share one fixed template.
- `shorts/upload.py`: YouTube Data API v3 resumable upload.
- `shorts/run.py`: queue handling. Broken scripts go to `rejected/`, and it warns when a queue is running low.
- `shorts/validate.py`: checks scripts before they're published (Shorts and long-form).
- `shorts/longform.py` + `shorts/brand.py`: 16:9 long-form videos, chapter cards and thumbnails (below).

## One-time setup (about 20 minutes)

1. **Make the YouTube channels.** Make one per folder, at youtube.com → profile → *Create a channel* / *Settings → Add or manage channels*. Brand-account channels work.
2. **Google Cloud OAuth client** (console.cloud.google.com):
   1. New project → *APIs & Services → Library* → enable **YouTube Data API v3**.
   2. *OAuth consent screen* → External → fill in the app name and your email.
   3. **Publish app → In production.** In "Testing", tokens expire after 7 days and uploads stop. The "unverified app" warning is fine for your own channels.
   4. *Credentials → Create credentials → OAuth client ID → Desktop app* → download it as `client_secret.json`.
3. **Make the upload keys file** on your Mac (in this repo folder):
   ```
   pip3 install google-auth-oauthlib google-api-python-client
   python3 make_env.py
   ```
   For each channel a browser tab opens: pick that channel and click Allow. It saves `shorts.env` (git-ignored, never commit it).
4. **Server** (Oracle Cloud free tier: Ubuntu 24.04, Ampere A1 shape, 2 OCPU / 12 GB). SSH in and run:
   ```
   curl -fsSL https://raw.githubusercontent.com/OliverVernoum/shorts-autopilot-2/main/server/setup.sh | bash
   ```
   It installs ffmpeg + Python, clones this repo, sets up cron and prints a deploy key. Add that key at
   GitHub → this repo → Settings → Deploy keys → *Add deploy key*, with **Allow write access** ticked.
5. **Copy the keys over and test** (from the Mac):
   ```
   scp shorts.env ubuntu@SERVER_IP:~/.shorts.env
   ssh ubuntu@SERVER_IP '~/shorts-autopilot-2/server/tick.sh test'
   ```
   Logs on the server: `~/shorts-short.log` and `~/shorts-long.log`.

**Or run it on a Mac instead of a server:** `bash server/mac-setup.sh` (launchd; `bash server/mac-setup.sh remove` to stop).

No GitHub Actions: the server (or Mac) does all rendering and uploading, and commits queue changes back here.

## Adding another channel

1. Copy `channels/cyber` to `channels/<slug>`, then edit `channel.json` and empty the queue.
2. Re-run `make_env.py` and copy `shorts.env` to the server again.
3. Add it to the `short)` schedule in `server/tick.sh`.

## Local preview

```
pip install -r requirements.txt
python -m shorts.run --channel cyber --dry-run          # real voice
python -m shorts.run --channel cyber --dry-run --tts silent
```

## Long-form videos (16:9, 5-10 min)

Scripts go in `channels/<slug>/longform/queue/<id>.json`: the usual `id`, `title` (max 90),
`description`, `tags`, `sources`, optional `thumb_text` (3-6 words) and `thumb_highlight` (one of
those words), and `chapters`: 5-8 of `{"title": "...", "scenes": [...]}` using the same scene
kinds as Shorts. Total narration 900-1500 words; max 90 words per scene.

- Layout: chapter label and segmented progress bar at the top, the Shorts scene visuals in the
  middle, word-highlighted captions at the bottom, and a full-screen chapter card before each
  chapter in the channel's branding (printout / pixel wall / PCB).
- Thumbnail: 1280x720 PNG in the same style (`shorts/brand.py`).
- Upload: the description gets a `Chapters` list with timestamps from the real render, and the
  thumbnail is set with `thumbnails.set`. Custom thumbnails need a phone-verified channel
  (youtube.com/verify); until then the upload still works and the run logs a warning.
- Schedule: `server/tick.sh long` reads `longform.txt` every hour at :37 and runs when
  `UTC hour % every_hours == 0`, only for listed channels with something in their long-form queue.
  Use `channels: none` to switch it off. Channels without a token are skipped quietly.
- Manual: on the server, `.venv/bin/python -m shorts.run --channel cyber --longform`.

```
python -m shorts.validate channels/*/longform/queue/*.json
python -m shorts.run --channel cyber --longform --dry-run --tts silent    # -> out/
python -m shorts.longform channels/cyber/longform/queue/L001-how-passwords-get-stolen.json /tmp/L001.mp4 silent
```

## Staying within YouTube's rules

- **Inauthentic content (monetisation).** Every script has to teach something different, with its own scene order and visuals. Don't bulk-generate near-identical videos.
- **AI disclosure.** The voice is TTS and the visuals are obvious graphics, so `containsSyntheticMedia` is `false`. Set it to `true` in `channel.json` if you add realistic AI people or scenes.
- **No copyrighted footage, music, game art or logos.** All visuals and sound effects are generated.
- Quota: 1 upload costs 1 unit from the 100/day upload bucket. Setting a thumbnail costs about 50 units.
