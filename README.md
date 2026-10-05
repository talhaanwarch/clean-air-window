# 🌿 Clean Air Window

Clean Air Window tells you the cleanest time to go outside today. You give it your city, your activity, the hours you are free, and whether you are in a sensitive group such as people with asthma. It answers with one time window, an hourly air-quality chart, and advice taken from the U.S. EPA's health guidance.

![Demo: planning a walk in Lahore, then the same run as a trace in AcruxCore](docs/images/demo.gif)

[Full-quality demo video (MP4, 45 s)](docs/demo.mp4)

## What you see

![The plan for a 45-minute walk in Lahore: best option 15:00–16:00 at AQI 155, an hourly AQI chart in EPA colours, and advice for a person with asthma](docs/images/app-result.png)

The card at the top and the chart come straight from the forecast data. The model writes the three lines below the chart, and the health advice links to the EPA document it came from.

## How it works

An open-weight model, Qwen3-Next-80B, runs a tool-calling loop with two tools:

| Tool | What it does |
|---|---|
| `get_air_and_weather` | Fetches today's hourly U.S. AQI, temperature and rain chance from [Open-Meteo](https://open-meteo.com/), then ranks every window inside your free hours by its worst hour. |
| `search_health_guidance` | Searches five EPA / AirNow documents (RAG) and returns the passages that match the AQI level and the person. |

Plain Python code does the arithmetic and picks the best and the worst window. The model only explains the result, because a model that copies numbers by hand sometimes copies them wrong. The model ends with a typed answer (`why`, `for_you`, `source_title`, `tip`), so the page shows the same four parts every time.

[AcruxCore](https://github.com/AcruxCore/AcruxCore), an open-source LLM-ops platform, keeps three things for the app:

- **The prompt**, as a versioned template. You can edit it in the dashboard and promote a new version without a redeploy.
- **The two tools**, in its tool catalog. `@acrux.tool` registers each one from its Python signature and docstring on the first run.
- **One trace per plan**, with every model call and every tool call, their inputs and outputs, and the "I went outside" feedback.

![The trace of one plan in AcruxCore: four model calls and the two tool calls, in order, with timings](docs/images/acrux-trace.png)

The model calls go straight to OpenRouter with your own key. AcruxCore receives only the trace.

## Run it

You need Python 3.12, an [OpenRouter](https://openrouter.ai/) API key, and an AcruxCore API key. For AcruxCore, either sign up at [acruxcore.com](https://acruxcore.com) or [self-host it](https://github.com/AcruxCore/AcruxCore#-self-hosting) with one Docker Compose command.

```bash
git clone https://github.com/talhaanwarch/clean-air-window.git
cd clean-air-window
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then fill in the two keys
streamlit run app.py
```

Open http://localhost:8501. The first plan takes about 20 seconds longer than the rest, because the app builds the guidance index once and caches it in `data/guidance-index.npz`.

### With Docker

```bash
docker build -t clean-air-window .
docker run --rm -p 8501:8501 --env-file .env -v caw-cache:/cache clean-air-window
```

The `caw-cache` volume keeps the guidance index between restarts. If AcruxCore runs on the same machine, point `ACRUXCORE_BASE_URL` at `http://host.docker.internal:<port>/api/v1` and add `--add-host=host.docker.internal:host-gateway`.

## Settings

| Variable | Default | Meaning |
|---|---|---|
| `ACRUXCORE_API_KEY` | — | Your AcruxCore API key (`acx_sk_…`). |
| `ACRUXCORE_BASE_URL` | `http://localhost:3001/api/v1` | `https://api.acruxcore.com/api/v1` for the hosted version. |
| `ACRUXCORE_DASHBOARD_URL` | `http://localhost:8080` | Where the "open this trace" link points. |
| `OPENROUTER_API_KEY` | — | Your OpenRouter key. |
| `CHAT_MODEL` | `qwen/qwen3-next-80b-a3b-instruct:nitro` | Any OpenRouter model that supports tool calls and JSON schema output. |
| `EMBED_MODEL` | `qwen/qwen3-embedding-8b` | The embedding model for the guidance search. |
| `INDEX_PATH` | `data/guidance-index.npz` | Where the guidance index is cached. |

## Project layout

```
app.py                      Streamlit page: form, verdict card, chart, answer, feedback
clean_air/agent.py          the prompt, the typed answer, and the traced tool loop
clean_air/tools.py          the two tools the model can call
clean_air/open_meteo.py     forecast download and window ranking
clean_air/guidance.py       chunking, embeddings and search over data/guidance/
data/guidance/              the EPA / AirNow texts, as markdown
scripts/build_guidance.py   downloads those texts again from their sources
```

## Data and licences

- Air quality and weather come from [Open-Meteo](https://open-meteo.com/), under CC BY 4.0.
- The health guidance in `data/guidance/` is U.S. EPA and AirNow material, which is in the public domain. Each file names its source URL at the top.
- Qwen3-Next-80B and Qwen3-Embedding-8B are released under Apache 2.0.
- This project is released under the Apache 2.0 licence.

This app is not medical advice. It repeats general EPA guidance for each AQI level.
