# Aelyx LinkedIn Content Engine

Autonomous daily content generation for Aelyx AI and Intelligence's LinkedIn company page.

## What this does

Every day, on a schedule, this system:
1. Picks a content angle (case study / product education / thought leadership) that hasn't been used recently
2. Generates fresh post copy in Aelyx's voice, referencing real client work
3. Generates a unique, professionally designed graphic concept (SVG, rendered to PNG) — not a templated chart, not generic "AI" imagery
4. Logs the post so future runs avoid repeating hooks, visuals, or angles
5. Publishes the result to a simple web dashboard for one-tap approval
6. On approval: posts to LinkedIn via the Community Management API (once your app is approved), or queues it for manual posting in the meantime

## What this does NOT do

- It does not auto-like, auto-comment, or auto-connect on other people's content. That category of automation is what gets LinkedIn pages restricted or banned, regardless of which tool wraps it. This system only ever touches your own page's own posts.
- It does not bypass LinkedIn's API approval process. Until your Community Management API access is approved, posts queue for manual publishing via LinkedIn's own native scheduler.

## Structure

```
aelyx-linkedin-engine/
├── .github/workflows/daily-post.yml   # the cron job — runs the pipeline daily
├── scripts/
│   ├── generate_post.py               # core generation logic
│   ├── post_history.py                # tracks what's been posted, prevents repeats
│   └── publish.py                     # publishes to LinkedIn API (once approved) or queues
├── data/
│   ├── source_material.md             # case studies / facts the generator pulls from
│   └── post_history.json              # auto-maintained log of past posts (angles, hooks, visuals used)
├── dashboard/
│   └── index.html                     # approval dashboard (static site, reads from data/queue.json)
├── requirements.txt
└── .env.example
```

## Setup (one-time)

1. **Push this repo to your GitHub.**
2. **Choose your AI provider and add the matching secret(s)** in repo Settings → Secrets and variables → Actions:
   - Secrets tab: add the API key for whichever provider(s) you want available — `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, and/or `GEMINI_API_KEY`. You can add more than one and switch later without touching code.
   - Variables tab: set `LLM_PROVIDER` to `anthropic`, `openai`, or `gemini` — this is what actually controls which one runs. Not a secret, since it's not sensitive.
   - Also on the Variables tab (optional): `POSTS_PER_DAY` — how many fresh posts to generate each run. Defaults to `1` if unset.
   - LinkedIn-related secrets (`LINKEDIN_ACCESS_TOKEN`, `LINKEDIN_ORG_URN`) — leave blank until your Community Management API approval comes through.
3. **Enable GitHub Pages** on this repo (Settings → Pages → set source to `/dashboard`) — this gives you the approval link.
4. **That's it.** The workflow in `.github/workflows/daily-post.yml` runs automatically every day. No server, no manual trigger needed.

### Switching AI providers later

Change the `LLM_PROVIDER` repo variable to `anthropic`, `openai`, or `gemini` — no code edits, no redeploy. The next scheduled run (or a manual one from the Actions tab) picks it up automatically. Default models per provider are set in `scripts/llm_provider.py`; override with `ANTHROPIC_MODEL`, `OPENAI_MODEL`, or `GEMINI_MODEL` repo variables if you want a specific model version.

### Changing how many posts generate per day

Set the `POSTS_PER_DAY` repo variable to whatever number you want — each run will generate that many posts, and the anti-repetition logic accounts for the whole batch (post 3 of today won't repeat post 1 or 2's angle, hook, or visual style). For a one-off run with a different count without changing the default, trigger the workflow manually from the Actions tab and fill in the `count` input.

## Updating source material

Edit `data/source_material.md` any time you want to feed it new case studies, client wins, or product updates. The generator pulls from whatever's in there, so keep it current — this is the difference between generic posts and posts that actually sound like Aelyx.

## LinkedIn API approval status

Posting only goes live automatically once your Community Management API application is approved (apply at developer.linkedin.com — organizational `w_organization_social` scope). Until then, every generated post still gets created and shows up on the dashboard, marked "Ready — post manually." Once `LINKEDIN_ACCESS_TOKEN` is set as a secret, `publish.py` switches to auto-publish on approval instead of just queuing.
