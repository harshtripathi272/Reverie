# Reverie

### *The cognitive observability platform for autonomous AI agents.*

> You can watch your agent run. You just can't understand it.  
> Reverie changes that.

---

## What this is, in plain English

When you run an AI agent today — any agent, doing anything — it produces a river of invisible activity. It creates goals. It calls tools. It searches memory. It retries failed operations. It spawns sub-agents. It reflects on its own mistakes. It runs validation checks. It sometimes loops in circles consuming thousands of tokens going nowhere.

You see none of this. You see a blinking cursor, and then either an answer or an error.

When something goes wrong — and it will go wrong — you have two options: read a wall of JSON logs, or guess.

Neither is acceptable for serious engineering. No other discipline works this way. When a web server fails, you open a trace viewer and see exactly which function call took 4 seconds and why. When a GPU is underperforming, you open Perfetto and see the exact kernel that stalled. When a frontend crashes, you open Chrome DevTools and see the exact line.

AI agents have none of this. They are black boxes wrapped in vibes.

**Reverie is the tool that was missing.**

It instruments your agent at the runtime level, captures every cognitive event as it happens, stores them with full context, and renders the entire cognitive journey as a living 3D world — a universe of glowing orbs floating in space, each one a thought, a tool call, a memory, a decision, connected by luminous filaments that show you exactly how one action caused the next.

And when your run finishes, you can replay it. You can scrub through time. You can compare two runs side by side and see the exact moment one succeeded and one failed, and why.

This is not a visualization for impressing investors. This is a debugging tool for engineers who are serious about building agents that actually work.

---

## The name

**Reverie** — a state of being pleasantly lost in one's thoughts. A daydream. A journey through the mind.

That is what you see when you open Reverie: the mind of your agent, rendered in space. Not a log file. Not a dashboard with numbers. A place you can walk through, explore, zoom into, and understand.

The name also holds a technical meaning. A *reverie* is a replay of mental experience. That is exactly what the platform's core feature provides: a faithful replay of everything your agent thought and did, played back at any speed, from any point in time.

---

## The problem, stated precisely

### Problem 1: Agents are opaque at runtime

An agent running a complex task might make 300 tool calls, retrieve memory 80 times, retry 40 times, and spawn 6 sub-agents — all in one run. The only record of this is a flat JSON log that no human can efficiently navigate. There is no causal structure. There is no topology. There is no way to see *why* event 147 caused event 148.

### Problem 2: Debugging agent failures is a guessing game

When a run fails, the engineer reads backwards through logs trying to reconstruct causality by hand. This is slow, error-prone, and does not scale to complex multi-agent systems. The industry currently has no better answer than "read the logs more carefully."

### Problem 3: There is no way to compare runs

This is the deepest problem. Agent behavior is non-deterministic. The same prompt can produce wildly different trajectories on different runs. When Run A succeeds and Run B fails, engineers currently have no tool to show them where the two runs diverged, what was different, and why one outcome happened and not the other.

### Problem 4: Graphs of raw events are unusable

The instinct to visualize agent traces as a graph is correct. But naive implementations produce unusable spaghetti within seconds of a real agent run. Without abstraction layers — without the ability to zoom from "high-level goals" down to "individual retry attempts" — graph visualization makes the problem worse, not better. This is why every previous attempt at agent visualization has remained a demo rather than becoming infrastructure.

### Problem 5: Reasoning traces are unstable

A tempting shortcut is to visualize the raw chain-of-thought reasoning text that models like DeepSeek-R1 expose. But closed frontier labs (OpenAI, Anthropic, Google) are progressively hiding or summarizing internal reasoning for policy reasons. Any architecture built on exposed reasoning as a foundation will break as the ecosystem evolves. Reverie treats reasoning as an optional enrichment layer, never as a core dependency. The platform works fully even when no reasoning text is exposed.

---

## The solution, stated precisely

Reverie is built around five core capabilities, each solving one of the five problems above.

### 1. Runtime instrumentation

Reverie sits between your agent and its runtime. It intercepts every meaningful cognitive event — not by reading logs after the fact, but by hooking directly into the agent framework's execution lifecycle. This means events are captured at the moment they happen, with full context, with accurate timing, and in real time.

The result is a stream of structured events flowing into Reverie as your agent runs. Not logs. Events. Each one has a unique ID, a parent ID (forming a tree), a timestamp, a duration, a type, and a rich payload describing exactly what happened.

### 2. Cognitive event normalization

Different agent frameworks think differently. OpenAI Agents SDK has "spans." LangGraph has "nodes" and "edges." CrewAI has "tasks." MCP has "tool calls." None of these map to each other cleanly.

Reverie defines a universal Cognitive Event Schema — a single vocabulary that all agent frameworks are translated into. `goal.created`. `tool.called`. `memory.retrieved`. `retry.triggered`. `subagent.spawned`. `validation.failed`. `reflection.generated`.

This translation layer — the normalization from runtime-specific semantics to universal cognitive topology — is the hardest engineering problem in the project, and the most valuable. It is the equivalent of what OpenTelemetry did for distributed system traces: defining the standard that the whole ecosystem eventually rallies around.

This is the moat.

### 3. Observational replay

Every event is stored with a full snapshot of the agent's cognitive state at that moment. What goals were active. What was in memory. What the context window looked like. What tools had recently been called and what they returned.

This enables **observational replay** — the ability to scrub backward and forward through any run, seeing exactly what the agent knew and what it did at every moment in time, like a DVR for agent cognition.

This is not re-execution. You are not re-running the agent. LLM calls are stochastic — re-running produces different outputs. Instead, you are replaying the recorded trace. This is exactly how Playwright's trace viewer works, and how Datadog session replay works. Proven, reliable, and far more useful than live re-execution.

### 4. Semantic zoom and cognitive compression

Raw event streams from real agents are overwhelming. Reverie solves this with a four-level semantic zoom system:

- **Level 1 — Mission view:** Only top-level goals. 1 to 5 nodes visible. The 30,000-foot view of what the agent was trying to do.
- **Level 2 — Task view:** Subtasks and major delegations. 5 to 30 nodes. You can see the structure of the agent's plan.
- **Level 3 — Operation view:** Individual tool calls, memory retrievals. 30 to 200 nodes. You can see the moment-to-moment execution.
- **Level 4 — Raw view:** Every event including retries, validations, and intermediate states. 200 to 10,000+ nodes. The full unfiltered trace for deep debugging.

The zoom level is not global — it responds to where the camera is in 3D space. Zooming in toward a cluster of orbs promotes those nodes to higher detail. Zooming out demotes distant nodes to their cluster representative. This is the same technique used by Perfetto for system traces and flamegraphs for performance profiling.

On top of zoom, a salience scoring system assigns each event a score from 0.0 to 1.0 based on its importance to the run outcome. Events on the critical path, events that caused failures, events that consumed disproportionate resources — these score high. Routine, uneventful events score low and are filtered from view by default. This alone reduces visible node count by 40 to 70 percent on typical runs.

For any cluster of events, an AI-powered summarization system (using the Claude API) can generate a two-sentence natural language description: *"This branch failed because the retrieval system returned low-relevance results three times in a row, triggering an exhausting retry loop that consumed 40% of the run's token budget."* This is the feature that makes Reverie feel intelligent rather than just pretty.

### 5. Comparative debugging

This is the feature that makes Reverie frontier engineering infrastructure rather than a nice tool.

Given two runs — a successful one and a failed one — Reverie's comparative debugger:

- Semantically aligns the two event timelines (matching events by meaning, not by index, so extra retries don't shift alignment)
- Finds the exact divergence point: the earliest moment where the two runs took different paths
- Computes a full diff: which tools were called in one but not the other, which memory retrievals returned different quality results, where token consumption diverged, where retries happened in one but not the other
- Constructs a visual fault tree: the causal chain from the failure event back to its root cause
- Generates an AI narrative explaining what went wrong and why

In the 3D interface, this appears as two orb universes side by side, synchronized in time, with a bright connecting beam between the divergence point in each. The diff is interactive — clicking any divergence node loads the full snapshot from that moment in both runs.

This is the answer to the question every AI engineer asks when debugging production agents: *"Why did that run fail when the other one succeeded?"*

---

## The 3D orb world — design and purpose

The visual interface of Reverie is not a graph visualization. It is a spatial world.

Imagine deep space: pure black void, infinite depth, distant stars for scale. Floating in this space are hundreds or thousands of glowing orbs — each one a cognitive event. They are not arranged on a flat plane. They float in three dimensions, their position encoding the structure of the cognitive tree: root goals near the center, subtasks orbiting outward, tool calls clustering around their parent goals like planets around a star.

Each orb glows from within — an emissive material with no external lighting needed. Color encodes type:
- Violet for goals (large, commanding)
- Cyan-blue for tool calls
- Emerald for memory retrievals
- Amber for retries (pulsing slowly, like a warning light)
- Red for failures (intense glow, impossible to miss)
- Purple for reflections
- Teal for sub-agent spawning

Connections between events are luminous filaments — bezier tubes that curve through space like light trails, thicker on the critical path, thinner for routine connections. During replay, active connections carry a flow of light particles moving from parent to child, making the causality visible and directional.

The whole scene is post-processed with bloom — every emissive surface bleeds light into surrounding space, creating the characteristic glow of something genuinely alive. A dense cluster of tool calls surrounding a goal node looks like a small galaxy. A retry storm looks like a pulsing amber nebula. A catastrophic failure cascades like a supernova — red light flooding outward from the failure point.

This is not aesthetic decoration. It serves engineering purpose:

1. **Pattern recognition at a glance.** A healthy run looks different from a failing run before you read a single label. Red clusters signal failure. Amber pulses signal retry loops. A sparse, well-structured tree signals a clean execution.

2. **Spatial memory.** Humans navigate space better than they navigate flat lists. Once you have explored a run in 3D, you remember where things are. The retry storm was in the upper-left cluster. The memory failure was deep in the right subtree. You can navigate back to it directly.

3. **Emotional legibility.** A run that consumed itself in loops *looks* chaotic. A clean successful run *looks* calm and organized. The aesthetics are a compression of information that the human visual system processes in milliseconds.

4. **Virality.** When a developer opens Reverie for the first time and sees their agent's cognition rendered in this way, they will record their screen and share it. This is how Reverie spreads. The infrastructure keeps engineers; the visual brings them in.

---

## How the pieces connect — the full data flow

Here is exactly what happens, step by step, from the moment you start your agent to the moment you see its cognition in 3D space.

```
Step 1: You run your agent.

  reverie run python my_agent.py
  
  The CLI starts the Reverie backend (if not already running) and injects 
  the instrumentation adapter before your agent process starts.

Step 2: The adapter hooks into the agent runtime.

  The OpenAI Agents SDK adapter attaches to the SDK's built-in tracing system.
  It registers callbacks for: trace start, span start, span end, trace end.
  No modification to your agent code is needed.

Step 3: Your agent runs normally.

  From your agent's perspective, nothing is different. It calls tools, 
  retrieves memory, makes decisions, exactly as it always did.

Step 4: The adapter emits CognitiveEvents.

  Every time the agent does something meaningful — creates a goal, calls a tool,
  retrieves memory, retries a failed operation — the adapter captures the event,
  translates it into a normalized CognitiveEvent, and queues it for transmission.
  
  The queue is bounded and the flush is background-threaded. Your agent is never
  slowed down or blocked by Reverie. If the backend is unreachable, events are 
  dropped silently and your agent continues without interruption.

Step 5: Events arrive at the Cognitive Event Bus.

  The FastAPI backend receives events (individually or in batches of up to 50).
  Each event is validated against the CognitiveEvent schema using Pydantic.
  Invalid events are rejected with a structured error — never silently accepted.
  
  Valid events are:
  a) Written to the append-only SQLite event log (durable, crash-safe)
  b) Broadcast to all active WebSocket subscribers for this runId
  c) Used to update run aggregate counters (total_events, total_tokens, etc.)

Step 6: The Snapshot Engine captures state.

  For every significant event, the snapshot engine captures the full cognitive 
  state at that moment: active goals, working memory contents, recent tool 
  results, context window state, cumulative token usage.
  
  Full snapshots are stored every 50 events as checkpoints. Between checkpoints,
  only the delta (what changed) is stored. This keeps storage efficient while
  enabling O(log n) seeks to any point in the timeline.

Step 7: The Graph Intelligence layer processes the event stream.

  As events arrive, the graph engine:
  - Adds nodes and edges to the cognitive DAG
  - Runs clustering to group related events (by goal, by agent, by topic)
  - Runs anomaly detection (loops, hotspots, bottlenecks, poison memory)
  - Assigns semantic zoom level (L1/L2/L3/L4) to every node
  - Computes initial salience scores (updated continuously as the run progresses)

Step 8: The Salience and Compression layer filters the signal.

  The importance scorer evaluates every node and assigns a salience score.
  Nodes scoring below 0.1 are hidden by default.
  Anomaly nodes are flagged with a visual marker.
  Hot path nodes (critical path, high resource consumption) are promoted.
  
  For any selected cluster, the AI summarization endpoint (Claude API, opt-in)
  can generate a natural language description of what happened in that region.

Step 9: The Spatial Renderer receives graph updates.

  The frontend connects to the backend via WebSocket and receives:
  - The initial graph state (all nodes and edges at the current zoom level)
  - Incremental updates as new events arrive (add node, update node, add edge)
  - Anomaly flags and salience score updates
  
  The renderer maintains an InstancedMesh for each node type (one draw call
  per node type, regardless of how many nodes exist). New nodes are assigned
  a position by the force-directed 3D layout engine, which runs for 300 
  iterations on initial load and then pins positions unless new events arrive.

Step 10: You see your agent's cognition in 3D space.

  The browser renders a black void with floating, glowing orbs.
  New orbs materialize as events arrive.
  Connections spark into existence as parent-child relationships are established.
  Failed nodes pulse red.
  Retry nodes pulse amber.
  The camera gently tracks active regions.
  
  You can orbit, zoom, and pan freely.
  Clicking any orb opens a detail panel showing the full event payload.
  Clicking any cluster triggers an AI summary of that region (if enabled).
  Double-clicking flies the camera to that node with a smooth transition.

Step 11: The run completes.

  The adapter sends a run-completion event.
  The backend marks the run as completed (or failed).
  The 3D world freezes in its final state.
  The timeline scrubber becomes active.

Step 12: You replay.

  Dragging the scrubber back in time removes nodes from the scene in reverse,
  restoring the orb world to its state at any past moment.
  
  Pressing play animates forward at your chosen speed (1x, 2x, 5x, 10x).
  The camera follows active nodes.
  
  You can export the replay as a GIF or MP4 for sharing or documentation.

Step 13: You compare (if debugging a failure).

  Selecting two runs and clicking "Compare" opens the side-by-side view.
  Two orb worlds appear, synchronized in time, playing in parallel.
  The divergence point is highlighted with a beam connecting the two timelines.
  The diff panel shows: token delta, tool call diff, memory quality diff.
  The fault tree shows the causal chain from failure back to root cause.
  The AI analysis generates a natural language explanation of what went wrong.
```

---

## What makes this different from everything that exists

### vs. LangSmith and Langfuse

LangSmith and Langfuse show you a list of traces. You can expand a trace into a tree and read the values. They are log viewers with good UX. They do not replay. They do not compare runs causally. They do not spatially render cognition. They do not compress or abstract large traces into navigable zoom levels. They are the text editor; Reverie is the IDE.

### vs. MCP Inspector and similar

MCP Inspector shows you individual tool calls in isolation. It has no concept of run topology, goal structure, memory state, or multi-turn cognition. It is a single-tool debugger. Reverie is a full cognitive runtime observer.

### vs. Observability tools (Datadog, Jaeger, Grafana)

These tools are built for microservices, not for agents. They understand requests, spans, and traces in the HTTP/RPC sense. They have no concept of goals, memory, retries-as-a-cognitive-event, sub-agent delegation, or planning state. Adapting them to agent cognition requires so much custom instrumentation that you have essentially built Reverie anyway, but worse.

### vs. Research prototypes (Vis-CoT, Hippo, AGDebugger)

These are academic proofs of concept. They are not production infrastructure. They do not handle real agent event density. They do not have adapters for production frameworks. They do not have replay engines, comparison systems, or salience modeling. Reverie takes the validated insights from this research (spatial cognition works, intervention improves trust, hierarchical visualization is necessary) and implements them as production-grade infrastructure.

### The gap Reverie fills

No tool in existence today provides:
- Real-time cognitive topology from a live agent run
- Observational replay with full state reconstruction
- Comparative causal debugging across runs
- Semantic zoom from mission-level to individual event level
- AI-powered compression of complex traces into human-readable summaries
- A spatial 3D interface optimized for cognitive navigation

That gap is the market. Reverie is the answer.

---

## The build philosophy — why we build in this exact order

There is one rule that governs every build decision:

**If the replay feature is useful in a terminal with no visual interface, you have built real infrastructure. If it only makes sense with glowing orbs, you built a demo.**

This rule dictates the build order completely.

Phase 0 is pure backend and CLI. Events flowing. Nothing visual.  
Phase 1 is replay in the terminal. No browser.  
Phase 2 is graph intelligence — semantic processing, no rendering.  
Phase 3 is compression and AI summaries — still no pretty UI.  
Phase 4 is comparative debugging — the most complex feature, still without the visual.  
Phase 5 is the 3D renderer — the last thing built, on top of infrastructure that already works.

This means that if the 3D renderer never shipped — if it were cancelled the day before launch — engineers would still have a genuinely useful debugging platform. The orb world is the face of Reverie. It is not the soul of it.

The soul is the event schema.

---

## Who uses this and why

**The primary user is an AI engineer building a production agent.**

They are not a researcher. They are not a business analyst. They ship code. Their agent runs in production. When it fails, they need to understand why, fast. Reverie is their Chrome DevTools.

Secondary users include:

- **Agent framework developers** who want to understand how their framework behaves at runtime under real workloads.
- **AI researchers** studying agent behavior, efficiency, failure modes, and emergent patterns across many runs.
- **Engineering managers** who need to understand the resource consumption and reliability of their team's agents without reading code.
- **QA engineers** building regression test suites for agent behavior, using Reverie's comparative debugger to detect behavioral regressions between agent versions.

---

## The long-term vision

Reverie starts as a developer tool. It ends as the observability standard for autonomous systems.

Today: you debug a single agent run, understand why it failed, fix the bug.

In one year: Reverie's cognitive event schema is being adopted by major agent frameworks as a standard output format. Third-party adapters are being built by the community. The schema becomes the lingua franca of agent cognition, the same way OpenTelemetry became the lingua franca of distributed system traces.

In three years: every serious AI agent in production runs with Reverie instrumentation the same way every serious web application runs with OpenTelemetry tracing. Cognitive observability is not a feature; it is assumed.

The path there is through the developer community. Open source the schema. Open source the adapters. Open source the CLI and backend. Make it trivially easy to instrument any agent. The 3D interface is what brings people in. The schema is what keeps them, and what grows the ecosystem.

---

## The current moment

Autonomous agents are moving from toy projects to production infrastructure. They are running longer, making more decisions, using more tools, managing more memory, delegating to more sub-agents. As they become more capable, they become more opaque.

The tools to understand them have not kept pace. The industry is debugging 2025-level agents with 2020-level tools. Text logs and manually reading traces.

Reverie is early infrastructure for a problem that is about to become critical. The right time to build it is now, before everyone realizes they need it.

The category is real. The gap exists. The architecture is sound.

Now we build.

---

*Reverie — Observe. Replay. Understand.*