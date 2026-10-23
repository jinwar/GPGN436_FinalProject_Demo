# GPGN 436/536 Final Project Demos

This repository contains independent project demonstrations, each in its own subfolder.

## Online demos for students

- [Acoustic time-reversal lab](https://acoustic-time-reversal-lab.onrender.com/app)
- [Confined aquifer pumping and recovery](https://confined-aquifer-lab.onrender.com/app)

Both run on free Render instances. Allow about a minute for the first visit
if an app has gone idle. No student account or local installation is required.

## Projects

- [Confined aquifer pumping and recovery](aquifer/README.md): radial pressure diffusion, constant-rate production, and shut-in recovery on a logarithmic grid.

- [Acoustic time-reversal lab](acoustic/README.md): interactive 2D acoustic propagation and source localization using Python and Panel.

See each project's README for setup, run, and validation instructions.

## Deployment

The root `render.yaml` defines two independent Python web services on Render:

| Service | Working directory | App route |
| --- | --- | --- |
| `acoustic-time-reversal-lab` | `acoustic/` | `/app` |
| `confined-aquifer-lab` | `aquifer/` | `/app` |

Each service installs its own requirements and starts with `python serve.py`.
The launcher uses Render's `PORT` and `RENDER_EXTERNAL_HOSTNAME` to configure
Panel and its WebSocket origin. A lightweight `/health` liveness endpoint
handles hosting health checks without creating interactive sessions. Each student browser session has its own model
state and simulation results.

To provision both, sign in to [Render](https://dashboard.render.com), create a
new Blueprint from this repository's `main` branch, and review the two free
web services before deploying. For an existing Blueprint, sync it to the latest
commit. Share each assigned HTTPS service URL with `/app` appended after both
services report Live and a browser simulation succeeds.

Free services sleep after 15 idle minutes and can take about a minute to wake.
They share the workspace's 750 monthly free instance hours. Memory and CPU are
limited: test expected classroom concurrency, especially for acoustic wavefield
movies, before a large live session. Paid instances are an optional later choice;
this Blueprint does not select a paid instance.

See [Render free-service limits](https://render.com/docs/free).
