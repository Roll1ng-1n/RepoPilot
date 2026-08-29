# RepoPilot

RepoPilot describes the domain of completing software-engineering work against a real code repository through autonomous, bounded, and verifiable agent execution.

## Language

**RepoPilot**:
A software-engineering agent that understands a repository-scoped task, changes the repository, verifies the result, and explains its work.
_Avoid_: RepoAgent, DevPilot, shell chatbot

**Implemented Capability**:
A RepoPilot capability reachable from the CLI, supported by an automated test or reproducible demonstration, visible in the execution trace, and documented with its known limitations.
_Avoid_: Stub, placeholder, planned capability

**Target Repository**:
The source-code repository in which RepoPilot performs the requested engineering work.
_Avoid_: RepoPilot repository, project

**Execution Environment**:
The replaceable backend through which RepoPilot executes actions against a target repository. Local and Docker are environment variants, while sandbox refers only to an environment that actually provides isolation.
_Avoid_: Runtime, sandbox

**Tool Call**:
A model's structured request to invoke a named RepoPilot capability with validated arguments.
_Avoid_: Free-form command, model response

**Runtime Test**:
An automated check of RepoPilot's own implementation and control flow.
_Avoid_: Task verification, benchmark

**Task Verification**:
The executable evidence used to determine whether RepoPilot's changes satisfy a task in the target repository. It may include unit or integration tests, static analysis, type checking, or other runnable checks.
_Avoid_: Unit test

**Agent Run**:
One bounded attempt by RepoPilot to complete a task, from the initial request to a terminal outcome.
_Avoid_: Chat, process

**Checkpoint**:
A persisted representation of an Agent Run from which a waiting or stopped Run can resume.
_Avoid_: Trace, backup

**Context Strategy**:
The policy that selects or compresses Agent Run history for the model while leaving the complete Trace intact.
_Avoid_: Trace retention, Checkpoint

**Human Approval**:
A user's explicit decision to allow or reject a high-risk Tool Call before RepoPilot executes it.
_Avoid_: Security guarantee, autonomous commit

**Plan Step**:
A bounded unit of work in an Agent Run's explicit plan, with a stated completion condition.
_Avoid_: Prompt, model turn

**Plan**:
The versioned, ordered collection of Plan Steps for an Agent Run.
_Avoid_: Task tree, conversation outline

**Replan**:
A reasoned revision that preserves completed Plan Steps and replaces the unfinished portion of a Plan.
_Avoid_: Retry, new Run

**Recovery**:
RepoPilot's bounded response to a failure or lack of progress, such as correcting a Tool Call, retrying a transient operation, or Replanning.
_Avoid_: Unbounded retry, Resume

**Run Budget**:
The configured limits on an Agent Run's steps, Replans, consecutive failures, command duration, runtime, tokens, or cost.
_Avoid_: Quota, benchmark budget

**Agent Benchmark**:
A repeatable collection of target-repository tasks used to measure RepoPilot's task-level behavior and outcomes.
_Avoid_: Runtime test, single demo
