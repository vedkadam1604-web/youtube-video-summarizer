# YouTube Video Summarizer

Paste a YouTube link and get a clear summary of the video in seconds:

- **TL;DR** – the whole video in one or two sentences
- **Summary** – a short paragraph
- **Key points** – the most important ideas, each with a timestamp
- **Chapters** – the video split into sections

Click any timestamp and the video jumps straight to that moment.

**Built with:** Python · FastAPI · OpenAI API

---

## What makes it different

There are already plenty of YouTube summarizers (browser extensions, websites, AI chat apps). Here's how this one compares with a typical tool:

| | Typical summarizer | This project |
| --- | --- | --- |
| **Output** | A block of free text | Structured sections every time: TL;DR, summary, key points, chapters, topic tags |
| **Timestamps** | Often missing, or links that point to the wrong moment | Every key point and chapter has a timestamp, checked against the video length so it never points past the end |
| **Jumping to a moment** | Opens YouTube in a new tab | Clicking a timestamp jumps the built-in player right there |
| **Long videos** | Often cut off or refused past a length limit | Long transcripts are split into parts, summarized in parallel, then combined |
| **Cost** | Monthly subscription or daily limits | Free and open source: you pay only for your own API usage (about a cent per video) |
| **Repeat videos** | Usually processed again (and counted against your limit) | Summaries are cached, so the same video is never paid for twice |
| **Privacy** | You sign in to a third-party service that sees what you watch | Runs on your own computer with your own key; only the transcript is sent to OpenAI |
| **For developers** | Usually a closed app | A documented REST API (`/docs`), JSON output, tests and CI |
| **Sharing** | Copy-paste the text | "Copy as Markdown" with clickable timestamp links, plus shareable `/?v=VIDEO_ID` links |

### Features at a glance

- Works with any YouTube link: normal, `youtu.be`, Shorts, embeds, live streams, mobile and YouTube Music
- Prefers human-written captions, falls back to auto-generated ones, and can translate captions from other languages
- Clear error messages (no captions, private video, rate limits) instead of a generic "something went wrong"
- Dark mode and a phone-friendly layout
- 26 automated tests that run on every push with GitHub Actions

---

## What you need

1. **Python 3.10 or newer** – check with `python3 --version`. Download it from [python.org](https://www.python.org/downloads/) if needed.
2. **An OpenAI API key** – create one at [platform.openai.com/api-keys](https://platform.openai.com/api-keys). You need a small amount of credit on your account (about $5 is plenty; each summary costs around a cent).

---

## How to run it

**1. Download the project**

```bash
git clone https://github.com/vedkadam1604-web/youtube-video-summarizer.git
cd youtube-video-summarizer
```

**2. Create a virtual environment and install the requirements**

Mac / Linux:
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Windows:
```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

**3. Add your API key**

Make a copy of `.env.example` and name it `.env`. Open it and paste your key:

```
OPENAI_API_KEY=sk-your-key-here
```

(`.env` is ignored by git, so your key never gets uploaded.)

**4. Start the app**

```bash
uvicorn app.main:app --reload
```

**5. Open it in your browser**

Go to **http://localhost:8000**, paste a YouTube link and click **Summarize**.

---

## Common problems

| Problem | Fix |
| --- | --- |
| "No transcript is available" | The video has no captions. Try a different video. |
| "OPENAI_API_KEY is not configured" | Check that your `.env` file exists and contains your key. |
| "rate limit or quota reached" | Add credit to your OpenAI account, or wait a minute and try again. |
| "YouTube is blocking transcript requests" | Happens on cloud servers. Run it on your own computer instead. |
| `command not found: uvicorn` | Activate the virtual environment first (step 2). |

---

## How it works

1. The app pulls the video's captions (transcript) from YouTube.
2. The transcript is sent to OpenAI along with a strict format the answer has to follow.
3. The app checks the timestamps it gets back, turns them into clickable links and shows the result.

Very long videos are split into parts, summarized in parallel and then combined. Summaries are cached, so the same video isn't paid for twice.

---

## Project structure

```
app/
  main.py          API routes
  transcript.py    Gets the transcript from YouTube
  summarizer.py    Sends the transcript to OpenAI
  models.py        Shape of the summary data
  static/          The web page (HTML, CSS, JavaScript)
tests/             Automated tests
```

---

## Extra

**API:** the app also has an API. Open **http://localhost:8000/docs** to try it.

**Run the tests:**
```bash
pip install -r requirements-dev.txt
pytest
```

**Run with Docker:**
```bash
docker build -t yt-summarizer .
docker run -p 8000:8000 --env-file .env yt-summarizer
```

**Change the model:** add `OPENAI_MODEL=gpt-5-mini` (or another model) to your `.env` file.
