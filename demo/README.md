# The online demo pack

Everything the public demo needs to run the full SAMARTH pipeline **without a
Gemini API key**. The server runs with `SAMARTH_LLM_MODE=demo`, which replays
these recordings and never calls Gemini.

| File | What it is |
|---|---|
| `samples.json` | The sample students offered on the website. **Synthetic, not real children.** |
| `recordings/` | Every model response and legal-search embedding from one real run of each sample |
| `chroma_db/` | Copy of the legal-document index the recordings were made with (RPwD Act 2016, NCTE guidelines) |
| `manifest.json` | The date the run was recorded and which samples were verified to replay |

## Re-recording

Needed after any change to a prompt, an agent, the sample students, or the
legal index. A recording only replays for exactly the same prompt.

```powershell
python scripts/record_demo.py
```

It records each sample with live Gemini (about a minute each, uses your
quota once), then replays all of them in a separate process with the API key
removed. Only samples that pass that check are marked verified and shown on
the website. Then commit this folder and push; Render redeploys.

## Why "today" is frozen

IEP prompts contain real dates (meeting, service start, annual review). In
demo mode the pipeline uses the date in `manifest.json` instead of the real
date, so a recording made in October still matches in December.

## What the demo blocks

- Students other than the samples, since there's nothing recorded for them
- PDF upload, so nobody uploads a real child's report to a public site
- Password changes on the shared demo account
