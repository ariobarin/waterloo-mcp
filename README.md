# waterloo-mcp

Give Claude read-only access to your University of Waterloo services, from one small server.

| Service | Tools |
|---|---|
| LEARN | `learn_courses`, `learn_due`, `learn_grades`, `learn_assignments`, `learn_assignment`, `learn_announcements`, `learn_content`, `learn_topic` |
| WaterlooWorks | `ww_jobs` (search, paged), `ww_job` (full posting) |
| Odyssey | `exam_schedule` (midterms, quizzes, finals, rooms, seats) |
| Crowdmark | `crowdmark_assessments` (due dates, submissions, marks back) |
| UW Flow | `course_info` (description, requisites, ratings; public) |

Nothing here submits, posts or changes anything.

## How sign-in works

You sign in once on your own computer with `login.py`, in a real browser, Duo and all. It saves the session cookies to `cookies.json`, which you copy to the server. The server never sees your password. It keeps sessions alive by touching each service every 20 minutes, and when a service bounces to sign-in it replays only UW's single sign-on hand-off, which works as long as your UW SSO session is alive. When that finally expires, tools say so and you run `login.py` again.

## Setup

You need Docker, a domain, and an HTTPS reverse proxy.

**1. A Discord OAuth app** (this is how Claude signs in as you; any app works, including one you already use). At [discord.com/developers](https://discord.com/developers/applications), open OAuth2, copy the Client ID and Secret, and add the redirect `https://<your-domain>/auth/callback`. Your Discord user id goes in `OWNER_DISCORD_ID` (Settings → Advanced → Developer Mode, then right-click yourself → Copy User ID).

**2. Run it.**

```sh
cp .env.example .env   # fill in the values
docker compose up -d
```

**3. Sign in** on your own computer, then copy the cookies over:

```sh
pip install playwright && playwright install chromium
python login.py
docker compose cp cookies.json waterloo-mcp:/data/cookies.json && docker compose restart
```

**4. Put HTTPS in front** (Caddy: `reverse_proxy 127.0.0.1:8000`) and add `https://<your-domain>/mcp` in Claude under Settings → Connectors → Add custom connector.

## Storage and security

Built for a Raspberry Pi with an SD card: cookies are written once per keepalive cycle, Docker logs are capped at 2 MB, and request logging is off. The container runs as a non-root user on a read-only filesystem. `cookies.json` is as sensitive as your logged-in browser, so keep the data volume private.

## Credits

The WaterlooWorks protocol comes from [ariobarin/waterloo-works-scraper](https://github.com/ariobarin/waterloo-works-scraper). The LEARN calls are ported from LEARN Link.
