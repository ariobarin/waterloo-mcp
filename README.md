# waterloo-mcp

An MCP server with read-only access to your University of Waterloo accounts.

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

Nothing here submits, posts or changes anything. Files and images come back as content the model can read.

## Sign in

```sh
pip install -r requirements.txt playwright && playwright install chromium
python login.py
```

A browser opens; sign in to each service as usual, Duo included. The session cookies are saved to `data/`. Your password never leaves that browser. When a session eventually expires, `sign_in_status` says so; run `login.py` again.

## Use it locally

Add it to any MCP client as a stdio server, e.g. Claude Code:

```sh
claude mcp add waterloo -- python /path/to/waterloo-mcp/server.py
```

## Host it

To reach it from anywhere (phone, web), run it over HTTP behind any HTTPS reverse proxy. Fill in `.env` from `.env.example` (your URL, and a GitHub, Google or Discord OAuth app so only you can sign in), then:

```sh
docker compose up -d
python login.py --push <ssh-host>:<path-to-this-folder>
```

`--push` sends the cookies straight into the container and keeps no local copy. Add `https://<your-domain>/mcp` to your client as a remote server. Hosted, every file also gets a one-time download link that streams through the server without touching disk.

## Contributing

Issues and PRs welcome, including from agents using the server.

Credits: the WaterlooWorks protocol is from [waterloo-works-scraper](https://github.com/ariobarin/waterloo-works-scraper); Piazza method names follow [piazza-api](https://github.com/hfaran/piazza-api).
