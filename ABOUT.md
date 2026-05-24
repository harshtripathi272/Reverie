# Reverie

### *A way to see how AI agents actually think.*

> You can watch your agent run. You just can't understand it.
> Reverie changes that.

---

## What this is, in plain English

When you ask an AI agent to do something — book a flight, summarize a folder of documents, write code, anything that isn't a simple chatbot reply — there's a lot of stuff happening behind the scenes that you never see.

The agent breaks the task down into goals. It decides which tools to use. It searches its memory. It tries something, fails, and tries again. It might call in helper agents to handle subtasks. It changes its mind. Sometimes it gets stuck in a loop, doing the same thing over and over without making progress, burning through your money in the process.

You see none of this. You see a spinner, and then either an answer or an error.

When something goes wrong — and it will go wrong — your only options are to read a giant wall of raw logs (think: thousands of lines of computer-speak, no structure, no story) or guess.

Neither is acceptable. No other field works this way. When a website crashes, an engineer opens a tool that shows them exactly which step took too long and why. When a video game stutters, there's a tool that shows the exact frame that lagged. When a phone app misbehaves, developers can step through the code line by line.

AI agents have nothing like that. They're black boxes wrapped in vibes.

**Reverie is the tool that was missing.**

It plugs into your agent, watches everything it does as it does it, remembers all of it, and shows you the whole journey as a living 3D world — a universe of glowing orbs floating in space. Each orb is one thought, one tool the agent used, one memory it looked up, one decision it made. Lines of light connect them, showing you exactly how one action led to the next.

When the agent finishes, you can replay the whole run like a movie. Scrub backward, fast-forward, pause. Compare two runs side by side and see the exact moment one succeeded and the other failed, and why.

This isn't a flashy demo for impressing investors. It's a practical tool for engineers who are serious about building agents that actually work.

---

## The name

**Reverie** — the word means a daydream, a state of being pleasantly lost in your own thoughts. A wandering of the mind.

That's what you see when you open Reverie: the mind of your agent, laid out in space. Not a log file. Not a dashboard with numbers. A place you can walk through, explore, and understand.

The name has a second meaning, too. A reverie is also a *replay* of mental experience — your mind running back over something that already happened. That's exactly the platform's core feature: replaying everything an agent thought and did, at any speed, from any moment.

---

## The problem, stated precisely

### Problem 1: Agents are invisible while they run

A real agent doing a real task might do hundreds of things in a single run — call dozens of tools, look up information eighty different times, retry forty failed attempts, hand off work to half a dozen helper agents. The only record of all this is a flat text dump. No structure. No story. No way to see *why* the 147th thing the agent did caused the 148th.

It's like trying to understand a movie by reading a transcript with all the dialogue jumbled into one paragraph and no scene breaks.

### Problem 2: Debugging is a guessing game

When a run fails, the engineer reads backwards through the logs trying to piece together what happened. This is slow, error-prone, and breaks down completely once you have multiple agents working together. The industry currently has no better answer than "read the logs more carefully."

### Problem 3: There's no way to compare runs

This is the deepest problem. Agents are unpredictable. Run the same prompt twice and you can get two completely different journeys. When run A succeeds and run B fails, engineers today have no tool to show them where the two diverged, what was different about the path each one took, and why one ended well while the other didn't.

That's the "Why did *this* run fail when the other one succeeded?" question every AI engineer asks, and right now there's no good answer to it.

### Problem 4: Visualizing agents naively just makes things worse

The instinct to draw an agent run as a picture is right. But if you just throw all the events on screen, you get an unreadable mess of overlapping lines within seconds of the agent starting. Without the ability to zoom from "the big picture" down to "this one specific tool call," any visualization makes the problem worse, not better.

This is why every previous attempt at agent visualization stayed a demo and never became a tool engineers actually use.

### Problem 5: The agent's "thoughts" can't be relied on

A tempting shortcut is to just show the raw chain-of-thought reasoning text that some AI models produce — the literal words the model is "thinking." But the major AI labs are progressively hiding this internal reasoning, summarizing it, or stripping it out entirely. Anything built on top of those raw thoughts will break the moment a lab decides to lock things down.

Reverie treats raw reasoning text as a nice-to-have, never as the foundation. The whole platform works fine even when the model exposes nothing internal at all.

---

## The solution, stated precisely

Reverie is built around five core capabilities, each one a direct answer to one of the five problems above.

### 1. Watching the agent live

Reverie sits between your agent and the runtime that powers it. Every time the agent does something meaningful — sets a goal, calls a tool, looks something up, retries a failed attempt, hands off to a helper — Reverie catches it as it happens, with full context, accurate timing, and zero delay. No reading logs after the fact. We're hooked into the agent itself.

What comes out is a stream of clean, structured events flowing into Reverie in real time. Not raw logs. Events with shape. Each one has an ID, a parent (so events form a family tree), a timestamp, a duration, a category, and a clear description of what happened.

### 2. A common language for what agents do

Different agent toolkits describe agent behavior in different vocabularies. OpenAI's toolkit talks about "spans." Another popular toolkit talks about "nodes" and "edges." A third talks about "tasks." None of these line up with each other.

Reverie defines its own universal vocabulary — a single set of words that every agent toolkit gets translated into. *Goal created. Tool called. Memory retrieved. Retry triggered. Helper agent spawned. Validation failed. Reflection generated.*

Doing this translation cleanly — taking the messy, toolkit-specific reality and mapping it to one consistent vocabulary — is the hardest engineering problem in the project, and the most valuable. Why? Because once everyone speaks the same language, tools can be built on top of it, the ecosystem can grow around it, and the whole industry benefits.

There's a precedent for this exact move in the world of regular software (a project called OpenTelemetry, which standardized how web servers report what they're doing). It quietly became the standard the whole industry rallied around. Reverie is making that same kind of move for AI agents.

This is the moat.

### 3. Replay, like a DVR for agent thought

Every event Reverie captures comes with a full snapshot of the agent's state at that exact moment. What goals it was working on. What was in its memory. What information it had on hand. What tools it had recently used and what they returned.

This means you can scrub backward and forward through any run, seeing exactly what the agent knew and what it did at every moment in time. Just like rewinding a movie or scrubbing through a security camera recording.

Important detail: this is not re-running the agent. AI is unpredictable — running it again gives you a different result every time. Instead, Reverie plays back the *recording* of what already happened. Same idea as the slow-motion replay system used to review professional sports plays, or the recordings airlines pull off black boxes after an incident.

### 4. Zooming out, zooming in

Real agent runs produce overwhelming amounts of activity. Reverie handles this with four levels of detail:

- **Level 1 — The mission.** Just the top-level goals. One to five orbs. The 30,000-foot view of what the agent was trying to do.
- **Level 2 — The plan.** Major subtasks and how they were divided up. A few dozen orbs. You can see the structure of the agent's strategy.
- **Level 3 — The actions.** Individual tool calls and memory lookups. A few hundred orbs. You can see the moment-to-moment work.
- **Level 4 — The raw stream.** Every single event, including retries and intermediate steps. Thousands of orbs. The full unfiltered trace for deep digging.

The detail level isn't a global setting. It responds to where your camera is. Fly close to a cluster and that cluster reveals more detail. Pull back and distant clusters collapse into summary form. It's the same technique used by detailed maps that show you streets when you're zoomed in and just country names when you're zoomed out.

On top of zoom, Reverie automatically scores how *important* each event is — based on whether it was on the path to the final answer, whether it caused a failure, whether it consumed unusual amounts of resources. Routine, uneventful stuff gets filtered out by default. This alone hides 40 to 70 percent of the noise on a typical run.

For any cluster of events, you can ask the AI to write you a short, plain-English summary of what happened there: *"This branch failed because the agent's memory kept returning bad results three times in a row, triggering a retry loop that burned through 40% of the run's budget."* This is the feature that makes Reverie feel smart instead of just pretty.

### 5. Side-by-side debugging

This is the feature that makes Reverie real engineering infrastructure rather than a nice toy.

Give Reverie two runs — one that worked and one that didn't — and it will:

- Line the two timelines up event by event, matching by *meaning* (so a couple of extra retries don't throw off the alignment). This is the same kind of matching technique scientists use to compare DNA sequences.
- Find the exact moment the two runs took different paths.
- Compute a full report of differences: which tools each run used that the other didn't, which memory lookups returned different quality results, where each one spent its budget, where retries happened in one but not the other.
- Trace the chain of cause-and-effect from the failure backward to its root cause.
- Generate a plain-English explanation of what went wrong and why.

In the 3D view, this looks like two orb universes side by side, locked together in time, with a bright beam connecting the moment they diverged. The differences are interactive — click any one of them and the full state of both runs at that moment loads up.

This is the answer to the question every agent engineer asks: *"Why did that run fail when the other one succeeded?"*

---

## The 3D orb world — what it is and why it looks the way it does

Reverie's main interface isn't a chart. It isn't a graph. It's a place.

Picture deep space: pure black, infinite depth, distant stars. Floating in this space are hundreds of glowing orbs, each one a single thing the agent did. They aren't laid out flat on a sheet. They float in three dimensions, and *where* they sit means something — the original goals near the center, subtasks orbiting outward, individual tool calls clustering around their parent goals like planets around a star.

Each orb glows from inside, no external light needed. Color tells you what kind of thing it is:

- Violet for goals (large, commanding)
- Cyan-blue for tool calls
- Emerald for memory lookups
- Amber for retries (gently pulsing, like a warning light)
- Red for failures (intense, impossible to miss)
- Purple for moments of reflection
- Teal for spawning helper agents

The lines between orbs aren't lines exactly. They're luminous filaments — light trails that curve gracefully through space. Thicker on the path that mattered, thinner for routine connections. During replay, points of light flow along the active connections from one orb to the next, making the cause-and-effect visible and directional.

The whole scene has a soft halo around bright objects — every glowing surface bleeds light into the space around it. A dense cluster of tool calls around a goal looks like a small galaxy. A retry loop looks like a pulsing amber nebula. A run that hit a catastrophic failure looks like a supernova — red light flooding outward from the moment things went wrong.

This isn't decoration. It does real work for the engineer:

1. **You can spot trouble at a glance.** A healthy run looks visibly different from a failing run before you read a single label. Red clusters mean failure. Amber pulses mean retry storms. A clean, well-structured tree means a clean execution. The pattern hits your eye before your conscious mind catches up.

2. **Your spatial memory kicks in.** Humans navigate space better than they navigate flat lists. Once you've explored a run in 3D, you remember where things are. The retry storm was up and to the left. The memory failure was deep in the right branch. You can fly back to it directly.

3. **The feeling matches the truth.** A run that ate itself in loops *looks* chaotic. A clean successful run *looks* calm. The visual is a kind of compression — your eyes process in milliseconds what would take minutes to read from a log.

4. **People want to share it.** When an engineer sees their agent's mind rendered like this for the first time, they record their screen and post it. The visual brings people in. Once they're in, the tool keeps them.

---

## How the pieces connect — what actually happens, step by step

Here's exactly what happens, from the moment you start your agent to the moment you see it in 3D space.

```
Step 1: You run your agent.

  reverie run python my_agent.py

  The Reverie command-line tool starts the backend (if not already
  running) and quietly slips its watcher into your agent before it
  begins. You don't change a line of your code.

Step 2: The watcher hooks into the agent's runtime.

  Reverie listens to the toolkit's built-in tracing system. Every
  meaningful event the toolkit emits — start, finish, success,
  failure — gets caught by the watcher.

Step 3: Your agent runs as it always does.

  From the agent's perspective, nothing has changed. It calls tools,
  looks up memory, makes decisions, exactly as before. No slowdown.
  If Reverie's backend is unreachable, events are quietly dropped
  and the agent keeps running. We never get in the way.

Step 4: The watcher translates into Reverie's vocabulary.

  Each raw event from the toolkit is converted into a clean Reverie
  event — the universal vocabulary mentioned earlier — and sent off
  to the backend in small, efficient batches.

Step 5: The backend receives, validates, and stores.

  The Reverie backend checks every event against a strict schema.
  Anything malformed is rejected on the spot — never silently
  accepted and forgotten about. Valid events get:

   a) Saved to durable storage on disk (so the run survives crashes).
   b) Broadcast live to any tab currently viewing the run, so the 3D
      view updates in real time as the agent works.
   c) Used to update the run's running totals — events so far, total
      cost, anomalies detected, and so on.

Step 6: Snapshots of the agent's state are captured.

  At regular checkpoints, Reverie saves a full picture of what the
  agent knew at that moment — active goals, working memory, recent
  tool results, total resources used. Between checkpoints, only
  what changed gets stored. This keeps the storage small while
  still letting you jump to any moment in the run instantly.

Step 7: The graph is assembled and analyzed in real time.

  As events flow in, Reverie quietly builds the family tree of
  events, groups related ones into clusters (by goal, by helper
  agent, by topic), and runs automatic anomaly detection — looking
  for loops, hot spots, bottlenecks, bad memory results, suspicious
  branching, and abandoned threads.

Step 8: Importance is scored, the noise is filtered.

  The importance scorer rates every event from 0 to 1. Events
  scoring near zero get hidden by default. Anomalies get visual
  warning markers. Events on the critical path of the run get
  promoted. If you ask, the AI summarizer will read a cluster and
  describe what happened there in plain English.

Step 9: The 3D view receives live updates.

  The browser maintains an open connection to the backend. As the
  agent works, new orbs materialize in the scene, lines spark into
  existence between them, failed orbs pulse red, retries pulse amber.
  An automatic layout engine — basically virtual magnets and springs
  — places new orbs so the whole scene stays visually balanced. It
  does this once per fresh run, then locks the positions in.

Step 10: You see your agent's mind in 3D space.

  Black void. Floating orbs. Threads of light. New orbs appearing
  as the agent works. You can orbit the scene with your mouse, zoom
  in, pan around. Click any orb to see exactly what happened. Click
  a cluster to get the AI's plain-English summary of the region.
  Double-click to fly the camera there.

Step 11: The run finishes.

  The watcher sends one final completion event. The run gets marked
  as completed (or failed). The 3D world freezes in its final shape.
  The timeline scrubber at the bottom comes to life.

Step 12: You replay.

  Drag the scrubber back in time and orbs disappear in reverse
  order, leaving the world as it was at any past moment.

  Press play and the run animates forward at whatever speed you
  pick. The camera follows whatever's currently active.

  Export the replay as an animated image to share with your team
  or include in a write-up.

Step 13: You compare (when something went wrong).

  Pick a successful run and a failed one, hit "Compare." Two orb
  universes appear side by side, synced in time. The exact moment
  they diverged glows brightly. A panel shows you all the
  differences — token cost, tools called, memory quality. A chain
  shows the cause-and-effect leading up to the failure. The AI
  writes you a short explanation of what went wrong and why.
```

---

## What makes this different from everything else out there

### vs. the existing log-viewer tools

There are a few existing tools that show you a list of agent runs. You can click into one and see a tree of what happened, with all the values laid out. They're log viewers with nicer styling. They don't replay. They don't compare runs. They don't render anything spatially. They don't compress big runs into navigable layers. They're the text editor; Reverie is the integrated workbench.

### vs. tool inspectors

Some tools show you individual function calls in isolation. They don't understand the bigger picture — the structure of goals, the memory state, the way retries fit into cognition, how helper agents get involved. They're a one-tool debugger. Reverie watches the whole mind.

### vs. general-purpose monitoring tools

Tools like Datadog, Jaeger, and Grafana are built for tracking traditional websites and services, not agents. They understand requests and responses in a web-server sense. They have no concept of goals, memory, retries-as-meaningful-events, helper agent delegation, or planning. Adapting them for agents would mean building so much custom plumbing that you'd basically have built Reverie yourself, except worse.

### vs. research demos

A few academic papers have demonstrated proof-of-concept agent visualizations. Those are research prototypes. They don't handle real agent volumes. They don't plug into production toolkits. They have no replay, no comparison, no importance scoring. Reverie takes the validated insights from this research (spatial visualization works, hierarchical zoom is necessary, intervention helps engineers trust the system) and turns them into actual production infrastructure.

### The gap Reverie fills

Nothing on the market today gives you all of:

- Real-time visualization of an agent's mind as it runs
- Replay with full state reconstruction at any moment
- Side-by-side debugging that explains why one run worked and another didn't
- Zoom from the highest mission level all the way down to the smallest event
- AI-written summaries that make complex runs human-readable
- A 3D interface that lets you navigate cognition spatially

That gap is the opportunity. Reverie is the answer.

---

## The build philosophy — why it was built in this exact order

One rule shaped every build decision:

**If the replay feature is useful in a plain text terminal with no graphics, you've built real infrastructure. If it only makes sense once you add the glowing orbs, you've built a demo.**

This rule dictated the whole order:

Phase 0 was pure backend and command-line. Events flowing. Nothing visual at all.
Phase 1 was replay in the terminal. No browser yet.
Phase 2 was the analysis layer — clusters, anomalies, zoom levels. Still no rendering.
Phase 3 was importance scoring and AI summaries — still no pretty UI.
Phase 4 was the side-by-side debugger — the most complex feature, still without the visual.
Phase 5 was the 3D world — built last, on top of infrastructure that already worked.

What this means: even if you stripped away the 3D world tomorrow, engineers would still have a genuinely useful debugging platform. The orb world is the *face* of Reverie. It isn't the soul.

The soul is the universal event vocabulary.

---

## What's working today

Every phase of the original plan is shipped and gate-passed. In numbers:

- **22 event types** in the frozen v1.0 vocabulary, validated identically by both the Python and TypeScript halves of the system. Wire format is byte-for-byte identical across languages.
- **One toolkit adapter** for the OpenAI Agents SDK that auto-injects via `reverie run python my_agent.py` — zero code changes to your agent.
- **A backend** that ingests events safely, stores them durably, and broadcasts them live to anyone watching. Single-event ingest comfortably beats the 5-millisecond budget.
- **A snapshot system** that can reconstruct what the agent knew at any past moment in any run. Periodic checkpoints keep replay seeking fast without slowing live ingest.
- **A graph and analysis layer** that automatically builds the cause-and-effect tree, assigns each event a zoom level, and runs all six built-in anomaly detectors: loops, hot spots, bottlenecks, bad memory, branching explosions, and abandoned threads.
- **An importance scorer** that ranks every event by how much it mattered to the run, plus an AI summary service backed by Claude (gracefully no-ops without an API key, caches results so the same region is never summarized twice).
- **A side-by-side debugger** that aligns two runs by meaning, computes the structured differences across all seven dimensions defined in the spec, traces failures back to their root causes, and generates an AI explanation of why the runs diverged.
- **A 3D explorer** built on modern web tech, with custom shaders for the orb glow, careful tone mapping so the bloom doesn't blow out, selective glow only on the parts that should glow, smooth orbiting camera, automatic 3D layout, and a clean glassmorphic interface.
- **A `reverie` command-line tool** with twelve subcommands including `start` (which boots the whole system in one go), `run`, `status`, `runs list/show`, `replay`, `state`, `graph`, `anomalies`, `zoom`, `summary`, and `compare`. Most of them have a `--json` mode for piping into other scripts.
- **400+ automated tests** across the project, covering everything from the schema to the adapter to the backend to the analysis layer to the AI client to the comparison logic to the command-line tool. The cross-language tests guarantee Python and TypeScript stay in lockstep.

The whole stack is set up so a developer can clone the repo and run one command — `reverie start` — and within thirty seconds have a backend, an instrumented run, and the 3D explorer open in their browser.

---

## Who uses this and why

**The main user is an engineer building a real agent.**

Not a researcher. Not an analyst. They ship code. Their agent runs in production. When it fails, they need to understand why, fast. Reverie is their workbench.

Other people who get value from Reverie:

- **Toolkit developers** who want to see how their toolkit behaves under real-world workloads.
- **AI researchers** studying agent behavior, efficiency, failure patterns, and how things change across many runs.
- **Engineering managers** who need to understand the cost and reliability of their team's agents without reading code.
- **Quality engineers** building tests for agent behavior, using the comparison feature to catch behavioral changes between agent versions.

---

## The long-term vision

Reverie ships today as a developer tool. It's built to grow into the standard for understanding autonomous AI.

Today: clone the repo, plug it into your agent, debug a failed run in 3D, all in one afternoon.

In a year: Reverie's event vocabulary is being adopted by major agent toolkits as a standard output format. The community is building third-party adapters. The vocabulary becomes the shared language of agent cognition — the same way a project called OpenTelemetry quietly became the shared language of regular software monitoring.

In three years: every serious AI agent in production runs with Reverie's instrumentation, the same way every serious website runs with proper monitoring. Watching agents think isn't a feature anymore. It's assumed.

The path there runs through the developer community. The vocabulary is open. The adapters are open. The command-line tool, the backend, the 3D explorer — all open. Plugging Reverie into any agent is genuinely easy. The 3D world is what brings people in. The vocabulary is what keeps them, and what grows the ecosystem around it.

---

## The current moment

AI agents are moving from experiments to production infrastructure. They're running longer, making more decisions, using more tools, holding more memory, delegating to more helpers. The more capable they become, the more opaque they become.

The tools to understand them haven't kept up. The industry is debugging tomorrow's agents with yesterday's tools — text logs and squinting.

Reverie is the answer that ships today. The vocabulary is frozen. The adapter works. The replay reconstructs state at any moment. The analysis layer surfaces anomalies on its own. The comparison engine pinpoints divergence between runs. The 3D explorer turns cognition into a place you can navigate.

The category is real. The gap exists. The architecture holds up. The build is shipped.

Now it grows.

---

*Reverie — Observe. Replay. Understand.*
