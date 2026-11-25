# Discovery lease takeover

After a second SDK call takes the lease for a persisted discovery run, the
original call cannot save a checkpoint. The property also applies while the
original call's expected version still matches the stored version.

## Run the check

From the repository root, run the check with Java and `curl` available. CI uses
Java 17 and calls the same script. Set `JAVA_HOME` to select a specific JDK.

```sh
pnpm check:tlc
```

The script downloads [TLA+ Tools v1.7.4](https://github.com/tlaplus/tlaplus/releases/tag/v1.7.4),
verifies its SHA-256 digest, and removes the downloaded JAR and TLC state files
after the run. To run offline, pass a local copy of the same JAR.

```sh
pnpm check:tlc /path/to/tla2tools.jar
```

The check passes when TLC verifies the intact invariant, finds that both callers
can make progress, and produces the expected `NoOriginalSaveAfterTakeover`
violation with the lease guard disabled.

## Code mapping and bounds

The model starts after the original call's extraction checkpoint and normalizes
its stored version to zero. It covers one run, two callers, one lease expiry,
and one checkpoint attempt per caller. The successor's lease stays fresh for
the modeled interval. Monotonic tokens stand in for production lease tokens.

- `ExpireOriginal` advances past the lease deadline. `Takeover` captures the
  successor's lease identity and expected version without saving a checkpoint.
  These steps model the application's `advance_discovery` claim and the
  [SQLite lease repository](../../../src/domain_kernel/_shared/infrastructure/sqlite_operations.py).
- `CommitCheckpoint` models the [lease renewal and checkpoint save](../../../src/domain_kernel/discovery/application/workflow.py)
  as one atomic step. The version predicate corresponds to the
  [SQLite checkpoint save](../../../src/domain_kernel/discovery/infrastructure/sqlite_runs.py).
  `RejectCheckpoint` leaves the stored lease and version intact.
- With the guard disabled, TLC reaches expiry, takeover at version zero, then
  a stale original save at expected version zero. The
  [two-client SQLite regression](../../integration/discovery/test_discovery_lease_takeover.py)
  exercises this ordering using the public SDK and scripted inference.

These checks cover the bounded model and the replayed SQLite ordering. Evaluate
other adapter behavior, lease renewal during inference, and delivery guarantees
with evidence at those boundaries. Recheck the model mapping when any of the
covered transitions or transaction boundaries changes.
