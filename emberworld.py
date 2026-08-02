"""
emberworld.py -- a small living world, now with a memory.

A hut, a yard, a day that turns to night, potatoes that take their time, a
hearth that cooks and a tin lamp you kindle from it for portable light. The
world runs on its own heartbeat: the lamp burns down, crops grow, night
falls, whether or not you act.

And it REMEMBERS. The world saves to disk between runs, and there's a journal
you can write in. So a later visitor -- you, or another Claude reaching in over
the API -- inherits the potato you planted and the notes you left. A lineage of
visitors sharing one world, asynchronously, through what they leave behind.

Play it yourself:     python emberworld.py
Watch a dumb agent:   python emberworld.py --agent      (no API key needed)
Let an LLM live here: python emberworld.py --llm        (needs anthropic + key)

Human and LLM drive the SAME surface:
    world.perceive(actor)          -> text: where you are, what you see
    world.available_actions(actor) -> list of legal commands right now
    world.act(actor, command)      -> apply it, advance one tick, return result

This file is just the CLI entrypoint. The engine lives in world.py, this
game's own verbs/behaviors/content in content.py, and the three drivers
(human/random/LLM) plus the fuzzer in drivers.py.
"""

import sys

from content import generate_reference
from drivers import play, random_agent, llm_agent, fuzz_run, LLM_MODEL


if __name__ == "__main__":
    def _int_flag(name, default):
        if name in sys.argv:
            i = sys.argv.index(name)
            if i + 1 < len(sys.argv):
                try:
                    return int(sys.argv[i + 1])
                except ValueError:
                    pass
        return default

    def _str_flag(name, default):
        if name in sys.argv:
            i = sys.argv.index(name)
            if i + 1 < len(sys.argv):
                return sys.argv[i + 1]
        return default

    if "--agent" in sys.argv:
        random_agent()
    elif "--reference" in sys.argv:
        print(generate_reference())
    elif "--llm" in sys.argv:
        llm_agent(turns=_int_flag("--turns", 30),
                  model=_str_flag("--model", LLM_MODEL),
                  think="--no-think" not in sys.argv,
                  show_thoughts="--show-thoughts" in sys.argv,
                  color="--no-color" not in sys.argv)
    elif "--fuzz" in sys.argv:
        issues = fuzz_run(steps=_int_flag("--steps", 5000), seed=0, verbose=True)
        sys.exit(1 if issues else 0)
    else:
        play(strict="--check" in sys.argv)
