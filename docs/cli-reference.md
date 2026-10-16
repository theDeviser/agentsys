# CLI reference

Generated from `agentsys --help`. Do not edit by hand; run `python3 scripts/check_docs_drift.py --write`.

```text
usage: agentsys [-h] [--version] [--as ACTOR] [--db DB]
                {init,task,show,claim,heartbeat,release,block,unblock,requeue,cancel,finding,checkpoint,submit,verify,review,merge-check,merge,approvals,approve,deny,status,log,resume,handoff,dispatch,budget,usage,adapters,doctor,metrics,demo,check-branch,hooks,mcp,profile,verify-log,approver,ui}
                ...

Durable task coordination for multiple coding agents.

positional arguments:
  {init,task,show,claim,heartbeat,release,block,unblock,requeue,cancel,finding,checkpoint,submit,verify,review,merge-check,merge,approvals,approve,deny,status,log,resume,handoff,dispatch,budget,usage,adapters,doctor,metrics,demo,check-branch,hooks,mcp,profile,verify-log,approver,ui}
    init                create the store for this repository
    task                create and list tasks
    show                full task record as JSON
    claim               claim a task (creates a worktree for implement tasks)
    heartbeat           extend your lease
    release             give a claimed task back
    block               mark blocked (needs human/dependency)
    unblock             return a blocked task to ready
    requeue             return an escalated task to ready
    cancel              cancel a task
    finding             record a finding, artifact, decision, blocker or
                        question
    checkpoint          record progress (optionally commit the worktree)
    submit              commit and hand the task to verification
    verify              run the verification pipeline
    review              independent review (reviewer must not have worked on
                        the task)
    merge-check         dry-run merge; detects conflicts without touching any
                        tree
    merge               merge an accepted task (requires human approval)
    approvals           list approval requests
    approve             grant an approval (human: actors only)
    deny                deny an approval (human: actors only)
    status              overview of tasks, approvals and budgets
    log                 audit trail
    resume              self-contained brief to continue a task from its last
                        verified checkpoint
    handoff             resume brief plus the next dispatch command for a
                        harness
    dispatch            run a headless agent on a task, within budget
    budget              per-account token limits
    usage               self-report interactive usage
    adapters            detect available agent CLIs
    doctor              pass/warn/fail health table
    metrics             local task/run counters
    demo                scripted onboarding story (<30s)
    check-branch        CI: exit 0 only if an agent/* branch is accepted or
                        merged
    hooks               install git hooks for agent/* branches
    mcp                 stdio MCP server (worker tools only)
    profile             repo verification profile
    verify-log          verify tamper-evident event hash chain
    approver            optional passphrase for signed human approvals
    ui                  live dashboard on 127.0.0.1 (actions recorded as
                        human:<you>)

optional arguments:
  -h, --help            show this help message and exit
  --version             show program's version number and exit
  --as ACTOR            identity, e.g. cursor:alice:implementer (or
                        AGENTSYS_ACTOR)
  --db DB               store path (default: <git root>/.agent-
                        system/state.db, or AGENTSYS_DB)
```
