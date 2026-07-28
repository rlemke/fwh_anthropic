# FFL Examples — `anthropic`

Every numbered scenario is a **complete, compilable FFL file**. Copy one into
`my.ffl` and run it:

```bash
fw ffl run --primary my.ffl \
  --library ~/fw_handlers/fwh_anthropic/src/anthropic_handlers/ffl/messages.ffl \
  --library ~/fw_handlers/fwh_anthropic/src/anthropic_handlers/ffl/files.ffl \
  --workflow my.llm.<WorkflowName>
```

(Repeat `--library` for whichever of the domain's FFL files your workflow uses;
`fw ffl seed --include anthropic` seeds them all once instead.) A runner serving
the `anthropic` namespace must be up (`fw runner start --domain anthropic`) with
`ANTHROPIC_API_KEY` in its environment. Every block below is compile-checked
against the domain's FFL.

New to the language? Start with the
[FFL grammar](https://github.com/rlemke/facetwork/blob/main/docs/reference/language/grammar.md)
and the [canonical examples](https://github.com/rlemke/facetwork/tree/main/examples/canonical).

---

## The facets at a glance

Every Anthropic surface as a typed facet, so an LLM call is just another step in a
workflow — retried, timed out, fanned out, and traced like any other.

| Namespace | Facets |
|---|---|
| `anthropic.messages` | `CreateMessage`, `CountTokens`, `CreateMessageWithTools`, `CreateMessageWithImages`, `CreateMessageStream`, `CreateMessageWithFile`, workflow `ChatOnce` |
| `anthropic.files` | `UploadFile`, `ListFiles`, `DeleteFile` |
| `anthropic.batch` | `SubmitBatch`, `GetBatchStatus`, `GetBatchResults`, `RunBatch` |
| `anthropic.agent` | `RunAgent` (Agent SDK) |
| `anthropic.code` | `RunClaudeCode` |
| `anthropic.computer` | `RunComputerUseSession` |
| `anthropic.compose` | workflow `DocumentQA` (upload → ask about the file) |

Results are **schemas**, so fields nest: `msg.result.text`,
`msg.result.input_tokens`, `up.result.id`.

---

## 1. Run what ships — no FFL to write

```bash
fw ffl seed --include anthropic

fw ffl run --workflow anthropic.messages.ChatOnce \
  --inputs '{"prompt": "Summarize the CAP theorem in two sentences."}'

fw ffl run --workflow anthropic.compose.DocumentQA \
  --inputs '{"path": "/data/report.pdf", "question": "What is the headline finding?"}'
```

Write FFL when you want a different *shape* — a token pre-check, a fan-out over
many prompts, your own error handling, or an LLM step wired into a data pipeline.

## 2. The smallest workflow you can write

Every FFL workflow needs a `namespace`, a `use` per namespace it calls into, and a
`yield` back to itself.

```ffl
namespace my.llm {

    use anthropic.messages

    /** One prompt, one answer. */
    workflow Ask(prompt: String, system: String = "") => (text: String, out_tokens: Long) andThen {

        msg = anthropic.messages.CreateMessage(
            prompt = $.prompt, system = $.system, max_tokens = 1024)

        yield Ask(text = msg.result.text, out_tokens = msg.result.output_tokens)
    }
}
```

Rules visible above: `=>` sits on the **same line** as the closing `)`; references
are always `step.field`, and schema results nest one level (`msg.result.text`);
`$.prompt` reads the workflow's parameter.

## 3. Cost control — count tokens before you spend

`CountTokens` is `Cost(tier = "cheap")`, `CreateMessage` is `"moderate"`. A `when`
gate turns that into a policy: don't send oversized prompts. Inside a case, `$` is
the counting step and `$$` reaches the workflow.

```ffl
namespace my.llm {

    use anthropic.messages

    /** Refuse prompts over a token budget instead of paying for them. */
    workflow BudgetedAsk(prompt: String, max_input: Long = 20000) => (status: String, text: String) andThen {

        counted = anthropic.messages.CountTokens(prompt = $.prompt) andThen when {
            case $.count.input_tokens <= $$.max_input => {
                msg = anthropic.messages.CreateMessage(prompt = $$.prompt, max_tokens = 1024)
                yield BudgetedAsk(status = "answered", text = msg.result.text)
            }
            case _ => {
                yield BudgetedAsk(status = "prompt_too_large", text = "")
            }
        }
    }
}
```

Every `when` needs a default case, and it must come last.

## 4. Fan out over many prompts

`andThen foreach v in <list>` runs the body once per element, in parallel across
the fleet. Here the `foreach` hangs off the **workflow**, so the loop variable and
the workflow's parameters share one `$`.

```ffl
namespace my.llm {

    use anthropic.messages

    /** One CreateMessage per prompt, dispatched in parallel. */
    workflow AskMany(prompts: Json, system: String = "") => (answers: [String]) andThen foreach p in $.prompts {

        msg = anthropic.messages.CreateMessage(
            prompt = $.p, system = $.system, max_tokens = 1024)

        yield AskMany(answers = [msg.result.text])
    }
}
```

```bash
fw ffl run --primary my.ffl --library …/messages.ffl --workflow my.llm.AskMany \
  --inputs '{"prompts": ["Define CRDT", "Define Paxos"], "system": "Answer in one sentence."}'
```

> For large offline workloads prefer `anthropic.batch.RunBatch` — same idea, one
> API call, half the cost.

## 5. Files → question — a two-step composition

`DocumentQA` is exactly this pattern; here it is written out longhand so you can
vary it.

```ffl
namespace my.llm {

    use anthropic.files
    use anthropic.messages

    /** Upload a file, then ask a question against it. */
    workflow AskAboutFile(path: String, question: String) => (file_id: String, text: String) andThen {

        up = anthropic.files.UploadFile(path = $.path)

        msg = anthropic.messages.CreateMessageWithFile(
            prompt = $.question,
            file_ids = up.result.id,
            file_type = "document",
            max_tokens = 1024)

        yield AskAboutFile(file_id = up.result.id, text = msg.result.text)
    }
}
```

`msg` references `up.result.id`, which is what orders it after the upload.

## 6. Prompt caching + a system prompt

`cache_system = true` marks the system prompt as cacheable; the result reports
what was written to and read from cache, so you can prove the saving.

```ffl
namespace my.llm {

    use anthropic.messages

    /** Reuse an expensive system prompt across calls. */
    workflow CachedAsk(prompt: String, system: String) => (text: String, cache_read: Long, cache_write: Long) andThen {

        msg = anthropic.messages.CreateMessage(
            prompt = $.prompt,
            system = $.system,
            cache_system = true,
            max_tokens = 2048)

        yield CachedAsk(
            text = msg.result.text,
            cache_read = msg.result.cache_read_input_tokens,
            cache_write = msg.result.cache_creation_input_tokens)
    }
}
```

## 7. Batch API — submit and wait in one step

```ffl
namespace my.llm {

    use anthropic.batch

    /** Run a whole batch and collect the results. */
    workflow BatchAsk(requests_json: String) => (batch_id: String, results: String, count: Long) andThen {

        run = anthropic.batch.RunBatch(
            requests_json = $.requests_json,
            poll_interval_seconds = 15.0,
            timeout_seconds = 3600.0)

        yield BatchAsk(
            batch_id = run.result.batch_id,
            results = run.result.results_json,
            count = run.result.result_count)
    }
}
```

Prefer this over `SubmitBatch` + a polling loop of your own — the facet already
polls, and its `Timeout` mixin bounds the wait.

## 8. Agents and Claude Code as steps

An agentic session is just another `event facet` — so it can be gated, retried,
and composed with the rest of a pipeline.

```ffl
namespace my.llm {

    use anthropic.agent
    use anthropic.code

    /** Plan with the Agent SDK, then execute with Claude Code. */
    workflow PlanThenDo(task: String, working_dir: String) => (plan: String, exit_code: Long) andThen {

        planned = anthropic.agent.RunAgent(
            prompt = "Write a concise plan for: " ++ $.task,
            max_turns = 6) with Timeout(minutes = 20)

        done = anthropic.code.RunClaudeCode(
            prompt = planned.result.text,
            working_dir = $.working_dir,
            timeout_seconds = 900) with Timeout(minutes = 30)

        yield PlanThenDo(plan = planned.result.text, exit_code = done.result.exit_code)
    }
}
```

## 9. Call-time mixins and `catch`

API calls are the textbook case for both: override the retry/timeout for one call,
and degrade instead of failing when the provider is unavailable.

```ffl
namespace my.llm {

    use anthropic.messages

    /** Be patient with a long generation; report an outage cleanly. */
    workflow ResilientAsk(prompt: String) => (status: String, text: String) andThen {

        msg = anthropic.messages.CreateMessage(
            prompt = $.prompt, max_tokens = 8192) with Timeout(minutes = 15) with Retry(maxAttempts = 3, backoffSeconds = 20) catch {
            yield ResilientAsk(status = "api_unavailable", text = "")
        }

        yield ResilientAsk(status = "answered", text = msg.result.text)
    }
}
```

---

## Cheat sheet

| You want to… | Write |
|---|---|
| Read a workflow/step parameter | `$.name` (`$$.name` one level out) |
| Read a previous step's result | `stepname.field` — schema results nest: `msg.result.text` |
| Run steps in parallel | write them with no reference between them |
| Fan out over a list | `workflow W(items: Json) … andThen foreach i in $.items { … }` |
| Collect fan-out results | `yield W(answers = [msg.result.text])` — the arrays accumulate |
| More time / retries for one call | `… with Timeout(minutes = 15) with Retry(maxAttempts = 3, backoffSeconds = 20)` |
| Handle a step failure | `step = Facet(…) catch { yield … }` |
| Branch | `step = Facet(…) andThen when { case <bool> => { … } case _ => { … } }` |
| Concatenate strings | `a ++ b` |

**Validate before you run:** `afl my.ffl --check` or MCP `fw_validate`. Every error
carries a `rule_id` — fetch `fw://docs/rules/{rule_id}` for a wrong/right pair.

## See also

- [`docs/README.md`](README.md) — per-surface specs for this domain
- [LLM integration guide](https://github.com/rlemke/facetwork/blob/main/docs/guides/llm-integration.md)
  — prompt-block facets, the in-process `ClaudeAgentRunner`, and when to use them
  instead of these facets
- [FFL grammar](https://github.com/rlemke/facetwork/blob/main/docs/reference/language/grammar.md) ·
  [canonical examples](https://github.com/rlemke/facetwork/tree/main/examples/canonical) ·
  [relative `$`-scoping](https://github.com/rlemke/facetwork/blob/main/docs/architecture/ffl-relative-scoping.md)
- The domain's FFL under `src/anthropic_handlers/ffl/` — the source of truth for every signature above
