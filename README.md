# waterloo-mcp

Read-only access to your University of Waterloo accounts for Claude (or any MCP client).

| Service | Tools |
|---|---|
| LEARN | `learn_courses` `learn_due` `learn_grades` `learn_assignments` `learn_assignment` `learn_announcements` `learn_content` `learn_topic` `learn_file` |
| WaterlooWorks | `ww_jobs` `ww_job` |
| Odyssey | `exam_schedule` |
| Crowdmark | `crowdmark_assessments` |
| Outline | `outlines` `outline_section` |
| Piazza | `piazza_classes` `piazza_feed` `piazza_search` `piazza_post` |
| UW Flow | `course_info` |
| | `sign_in_status` |

Nothing here submits, posts or changes anything. Files and images come back as content the model can read, plus a one-time download link that streams through the server without touching disk.

## How sign-in works

You sign in once, on your own computer, in a real browser (Duo included). `login.py` sends the resulting cookies straight into the server and keeps no copy. The server never sees your password; it keeps sessions alive by checking in every 20 minutes. When one finally expires, `sign_in_status` says so and you run `login.py` again.

## Setup

You need Docker, a domain, an HTTPS reverse proxy, and a [Discord OAuth app](https://discord.com/developers/applications) (that's how Claude signs in as you; only your account gets in).

```sh
cp .env.example .env    # fill it in
docker compose up -d
pip install playwright && playwright install chromium
python login.py --push <ssh-host>:<this-dir>
```

Put HTTPS in front (Caddy: `reverse_proxy 127.0.0.1:8000`), then add `https://<your-domain>/mcp` in Claude under Settings → Connectors.

Runs comfortably on a Raspberry Pi 4: one cookie write per check, capped logs, a non-root read-only container.

## Contributing

Issues and PRs welcome, including from agents using the server. CI builds every push.

Credits: the WaterlooWorks protocol is from [waterloo-works-scraper](https://github.com/ariobarin/waterloo-works-scraper); Piazza method names follow [piazza-api](https://github.com/hfaran/piazza-api).
