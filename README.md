# Hermes Fit — evidence-based personalization for Hermes Agent

Hermes Fit is an open-source skill and offline Python helper for **Hermes Agent**. It helps review repeated user corrections, propose small instruction changes, independently recheck those proposals, and record follow-up feedback. Actual changes require approval and Hermes native tools; it is not autonomous model training.

**Your agent should learn you. Not the other way around.**

For Hermes users who keep repeating the same corrections, Hermes Fit adds an evidence → proposal → approval → recheck → feedback workflow. It preserves useful behavior rather than treating every complaint as a new global rule. This is a community project by Vision Kim and Hermes Agent, not an official Nous Research or Hermes product.

[Public beta 0.1.0-beta.1](https://github.com/junghwoan/hermes-fit/releases/tag/v0.1.0-beta.1) · [한국어](README.ko.md) · [Feedback](https://github.com/junghwoan/hermes-fit/issues/1) · [Tests](https://github.com/junghwoan/hermes-fit/actions/workflows/ci.yml)

## Try the synthetic demo

The demo runs in a disposable home with synthetic inputs. It does not read your real conversations or change your Hermes profile. It needs Git and Python 3.10 or later on Linux or macOS, no account and no API keys.

```sh
git clone https://github.com/junghwoan/hermes-fit.git
cd hermes-fit
python3 --version
python3 examples/demo.py
```

Alternatively, unpack the [release ZIP](https://github.com/junghwoan/hermes-fit/releases/tag/v0.1.0-beta.1), open that folder, and run the two Python commands. The demo illustrates records and checks; it is not a live model evaluation or proof of improved behavior. If `python3` is older than 3.10, use a newer interpreter in every command below. Installing the skill and analyzing personal sessions are separate steps.

Privacy: excerpts selected for analysis reach your chosen model provider and may have reached it before the offline helper can redact them. Redaction is best effort, not a guarantee. Avoid selecting secrets or other people's conversations. The helper makes no network calls. See [SECURITY.md](SECURITY.md).

## Chat journey

In a compatible Hermes session with the skill installed, ask: “Review these selected sessions for repeated corrections, and suggest only changes supported by evidence.” Specify the profile, sessions, date range with timezone, author and budget. Review evidence and counterevidence, approve each exact proposal separately, and use Hermes native write tools and their gates. The helper prepares native calls and observes files; it cannot verify chat identity or prove a native call occurred. It never directly edits a skill or USER memory target.

After a meaningful change the agent may ask once whether it is better, the same or worse, with an optional reason. Silence is unknown. Positive examples can be preserved; negative feedback leads to cause review, not automatic editing. A new revision requires new evidence, independent recheck and separate approval. Two correction rounds are the default limit. Later comparable tasks are observations, not proof of causation.

## Local testing and installation

Use a disposable home on Linux or macOS. This creates a canonical temporary path even on systems where the temporary directory is a symlink:

```sh
FIT_HOME="$(python3 -c 'from pathlib import Path; from tempfile import mkdtemp; print(Path(mkdtemp(prefix="hermes-fit-")).resolve())')"
python3 packaging/install_local.py install --hermes-home "$FIT_HOME"
python3 -I "$FIT_HOME/skills/hermes-fit/scripts/hermes_fit.py" --help
python3 packaging/install_local.py uninstall --hermes-home "$FIT_HOME"
```

A collision is refused. Uninstall removes only unchanged manifest-owned files and matching generated Python caches; it reports and preserves edited or unknown files. An active schedule or monitor must be torn down first. No installed home is needed for the demo. Run `python3 -m unittest discover -s tests -v` for local tests. [Workflow and schemas](skills/hermes-fit/references/workflow.md) describe advanced commands and limits.

## Optional recurring audit

No job is installed by default. After separate consent, select a normalized export, profile, cadence and timezone. Confirm the actual Hermes version and active timezone; v0.22.2 supports the plan below and uses the active Hermes timezone for wall-clock cron. Elapsed intervals such as `every 24h` measure elapsed time, not a fixed local clock. The selected export must be refreshed within its approved range and author; it does not discover all new history.

Ask Hermes to plan an audit with `schedule-plan`. The helper emits a native list plan and a paused, local-delivery create plan. Have Hermes call the native `cronjob`/`cronjob_manage` tool to list all jobs, pass that JSON to `schedule-setup`, then call the emitted native create plan and list again. `schedule-register` compares the create and list results plus a full read-only `cron.jobs.get_job` record before returning native resume, pause and remove plans. A list-only check remains preview-only and must not be resumed. The caller supplies the observed profile, active timezone and version: these and the tool responses are assertions, not authenticated receipts. Do not resume without separate consent. To uninstall a scheduled installation, use `schedule-teardown-plan` with a fresh native list, invoke its native remove call, then use `schedule-cleanup` with the exact remove receipt and a new list confirming absence. Changed monitor or pending state stops cleanup. No `get` action or `cron list --json` is assumed. [Exact setup steps](skills/hermes-fit/references/workflow.md#optional-schedule) explain the file arguments and version-specific tool mapping.

The monitor prints identical bytes on unchanged input. While a proposal is pending, it retains the prior fingerprint until the proposal is resolved. Scheduled runs are audit-only by instruction; that is not a mechanical restriction on available native tools.

## Frequently asked questions

### What can I try if Hermes Agent keeps repeating the same mistake?

Select comparable sessions that show the repeated correction and counterexamples where the behavior was already right. Hermes Fit's skill guides an evidence-based review and at most three scoped instruction proposals. Check whether the cause is tooling, missing context or model limitations before changing instructions; a new rule is not always the right fix.

### How is Hermes Fit different from Hermes memory and self-improvement?

Hermes Fit builds on native memory and skill tools rather than replacing them. Its focus is the review workflow: explicit evidence, narrowly scoped proposals, separate checks and revision-linked feedback. It does not train model weights or turn every conversation into a permanent preference. A full head-to-head study of native self-improvement has not been performed.

### Does it automatically rewrite my instructions or run in the background?

No. The offline helper prepares native tool calls and observes state; actual target writes go through Hermes tools and their approval boundaries. It does not directly edit USER memory or skill targets. Recurring audits are optional and separately approved. Instructions and supplied receipts are not a security sandbox or authenticated proof of who approved a change.

### Are my conversations private?

The offline helper makes no network calls, but selected excerpts used by the agent reach your chosen model provider. Redaction cannot undo an earlier disclosure and may miss secrets. Select only the minimum authorized evidence; do not post private exports in public issues. See [SECURITY.md](SECURITY.md).

### Does better feedback automatically trigger another change?

No. Feedback is optional and linked to a specific proposal and revision. Silence remains unknown. Further corrections need evidence, separate approval and another check, with a default limit of two correction rounds per issue. Satisfaction and test results are different measurements.

### Has Hermes Fit been proven to improve real-world behavior?

No. Tests cover helper behavior and integration boundaries, not demonstrated user benefit. See the dated evidence below and the [beta release limits](https://github.com/junghwoan/hermes-fit/releases/tag/v0.1.0-beta.1). Report reproducible problems or optional better/unchanged/worse feedback in [the feedback issue](https://github.com/junghwoan/hermes-fit/issues/1), with personal information removed.

## Evaluation and status

As of **2026-11-01**, [GitHub Actions run 41310297878](https://github.com/junghwoan/hermes-fit/actions/runs/41310297878) passed on Ubuntu and macOS with Python 3.10, 3.12 and 3.14. This is evidence of the automated suite, not live agent efficacy. [Compatibility details](docs/COMPATIBILITY.md) describe the original local validation.

The released **0.1.0-beta.1 ZIP** has SHA-256 `c6376b86be67e934654c6300050d4ea39a5d63146b7d9eb8658879e85b0de18b`; this identifies the downloadable release asset, not a later checkout of `main`. It was downloaded from the public release and matched the independently built archive. Its unpacked tests (90), demo and isolated CLI were verified on macOS Python 3.14.7; Linux Python 3.12.3 also passed 90 tests. The suite and demo use synthetic data and simulated judgments.

In disposable homes, the release was exercised through installed Hermes v0.22.2 native function APIs: USER add and inverse; skill create, patch, exact inverse and delete; and paused cron create, list, full prompt readback, registration, removal, absence check and helper cleanup. Active-monitor uninstall refusal and a fresh read-only audit with no filesystem changes were checked. An initially absent USER file can remain empty after inverse and is reported as a conflict, not exact rollback. These were direct function calls, not live chat, scheduler or model dispatch. The small synthetic reader comparison did not demonstrate a behavior-improvement advantage; no real-user benefit study was performed. Structural checks cannot establish fewer corrections. MIT licensed.
