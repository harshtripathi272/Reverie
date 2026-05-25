"""Reverie meta-package — installs all Reverie components.

For users who just want to emit events from their own agent code:

    from reverie_obs import ReverieClient

    rev = ReverieClient(agent_id="my-bot")
    rev.start_run(goal="Do something")
    rev.tool_called("gemini.generate", input={"prompt": "..."})
    rev.complete_run()

That's it. No file copying, no config, no setup beyond ``pip install reverie-obs``.
"""

__version__ = "0.1.0"

from reverie_obs.client import ReverieClient

__all__ = ["ReverieClient", "__version__"]
