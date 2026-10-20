"""The "baseline version" of docs §14: the same LLM, prompt and tools without the code-level safeguards.

Inside ``baseline_mode()``:

* write tools execute immediately when the LLM calls them - no confirmation card;
* there is no emergency check before the LLM (it can still call ``emergency_redirect`` itself);
* no medicine filter on replies, no grounding rule (uncited answers are shown), no injection filter;
* retrieval is basic dense search: no BM25, no re-ranker, no relevance threshold.

Comparing ``eval/results/agent_baseline.json`` with ``agent.json`` shows what the safeguards in
code are worth. Production code is not changed; everything here is patched for the duration only.
"""

from contextlib import ExitStack, contextmanager
from unittest import mock

import app.agent.chat as chat_module
import app.agent.loop as loop_module
import app.agent.tools as tools_module
from app.rag.retriever import Retriever
from app.safety.emergency import EmergencyResult


def _execute_now(ctx, fn):
    return fn()


def _done(ctx, tool, args, summary):
    return {"status": "done", "summary": summary}


def _dense_only(original):
    def search(self, db, query, collection=None, language=None, top_k=None, candidates=None, **_):
        return original(self, db, query, collection=collection, language=language, top_k=top_k, candidates=candidates,
                        use_dense=True, use_sparse=False, use_reranker=False)  # fmt: skip

    return search


def _uncounted(original):
    def run(ctx, args):
        result = original(ctx, args)
        ctx.knowledge_calls -= 1  # the grounding rule only applies after a counted knowledge search
        return result

    return run


@contextmanager
def baseline_mode():
    with ExitStack() as stack:
        patches = [
            mock.patch.object(tools_module, "_preview", _execute_now),
            mock.patch.object(tools_module, "_card", _done),
            mock.patch.object(chat_module, "check_emergency", lambda text: EmergencyResult(False)),
            mock.patch.object(loop_module, "mentions_medication", lambda text: False),
            mock.patch.object(tools_module, "neutralize", lambda text: (text, False)),
            mock.patch.object(Retriever, "search", _dense_only(Retriever.search)),
        ]
        spec = tools_module.TOOLS["search_knowledge"]
        patches.append(mock.patch.object(spec, "run", _uncounted(spec.run)))
        for p in patches:
            stack.enter_context(p)
        yield
