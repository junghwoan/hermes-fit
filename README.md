# Hermes Fit 0.1.0-beta.1

Try the disposable synthetic demo first. It needs Python 3.10 or later, no account and no keys:

```sh
python3 --version
python3 examples/demo.py
```

If `python3` is older than 3.10, use a newer interpreter in every command below. Hermes Fit is a community project by Vision Kim and Hermes Agent, not an official Hermes product. It helps review explicitly selected feedback, propose small instruction changes, independently recheck them, and record optional follow-up feedback.

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

## Evaluation and status

The demo and test suite use synthetic data, simulated native writes and simulated judgments. The parent verified commit `49ba0a8` on macOS Python 3.14.7: all 90 tests, the demo and isolated CLI passed. The independently built 31-file ZIP (SHA-256 `c24684cb47b139274786bc225c6598a796210338f60e66a46d93691d0dce6636`) matched the Linux build; its unpacked tests and demo also passed on macOS. This documentation-only successor retains the tested runtime and tests but has a different ZIP hash.

In disposable homes, the parent also exercised the candidate from that ZIP through the installed v0.22.2 native function APIs: USER add and inverse; skill create, patch, exact inverse and delete; and paused cron create, list, full prompt readback, registration, removal, absence check and helper cleanup. Active-monitor uninstall refusal and a fresh read-only audit with no filesystem changes were checked. An initially absent USER file can remain empty after inverse and is reported as a conflict, not exact rollback. These were direct function calls, not chat dispatch, scheduler or model execution. No cloud CI run, blind model comparison or user benefit study was performed; structural checks cannot establish fewer corrections. See [compatibility](docs/COMPATIBILITY.md). MIT licensed.
