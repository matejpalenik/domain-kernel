# Formal verification with TLA+ and TLC

Use model checking when a consequential concurrency, retry or state-machine
invariant can fail under orderings that are hard to enumerate with ordinary tests.
Start with one property. Use the [TLC model checker](https://lamport.azurewebsites.net/tla/tools.html)
for bounded state and interleaving exploration. This procedure adapts
[pstack's formal verification guidance](https://github.com/cursor/plugins/blob/main/pstack/skills/create-formal-verification-skill/SKILL.md).

1. State the property and the observable harm of breaking it. Identify the exact
   SDK path and give the property a concrete regression through that path.
2. Map the model's state and actions to code. Record the tool version, command,
   bounds, assumptions and covered code revision or diff. Make an action atomic only
   when the implementation gives it that guarantee.
3. Check the intended model. Confirm that useful success and contention paths are
   reachable. Remove the target guard in a scratch model while keeping other guards
   in place, then require a counterexample for the named invariant. Restore and
   recheck the model.
4. Translate the counterexample or critical ordering into calls and observations
   in the real SDK test. Record which adapter and inputs ran. If a model step has
   no implementation counterpart, reconcile the model and source before using
   the result as evidence.
5. Recheck the model and replay when covered transitions, transaction boundaries or
   assumptions change. Record an unavailable tool or a stale mapping as an evidence
   gap. A green result applies to the stated model and bounds.

## First proposed pilot for discovery lease takeover

**Property.** After a second SDK invocation claims the lease for a persisted discovery
run, the original invocation cannot save another checkpoint even when its expected
checkpoint version equals the stored version.

Start with the [existing takeover test](../../../../tests/integration/discovery/test_discovery_lease_takeover.py).
It lets the resumed call finish first, so the checkpoint version can already have
advanced when the original call tries to save. Add the companion ordering in the
same integration suite. Use two `Client` instances, one temporary file-backed
SQLite database, a controlled clock and events.

- Pause the original invocation just before its post-extraction checkpoint so the
  separate extraction lease has completed. Advance the clock. Pause the resumed
  invocation after it commits the discovery lease claim and before it saves its
  first checkpoint. Keep both pauses outside write transactions. A pause at the
  resumed call's inference gateway comes after its first checkpoint.
- Confirm the checkpoint version still matches. Release the original caller and
  assert `StaleStateError` and an unchanged checkpoint from a fresh read while the
  resumed caller is paused. Then let the resumed call finish. Use a scratch variant
  that bypasses the checkpoint lease guard with the version check intact to confirm
  that the regression detects the stale write.

When adding the pilot, pin TLC and record the replayable command with the model.
Bound it to one run, two invocations and the steps needed for lease
expiry, takeover, attempted commit and successful progress. Model the captured
lease identity and expected version separately from the persisted owner and
checkpoint version. Map the ownership check and version-checked save to the
[workflow transaction](../../../../src/domain_kernel/discovery/application/workflow.py).
Check who owns the lease at the time of a successful write. A later takeover may
legitimately leave a checkpoint that was written by the previous owner.

Require the broken model to exhibit takeover before the original write while the
version still matches. Replay that ordering in the SQLite regression. The bounded
model covers those modeled orderings. The regression covers the replayed SQLite
path with test inference. The current Jupyter restart journey exercises keyed
`discover()` replay. The two-client regression is the entry point for explicit
`resume_discovery()` takeover evidence. PostgreSQL and live inference delivery
need their own evidence.
