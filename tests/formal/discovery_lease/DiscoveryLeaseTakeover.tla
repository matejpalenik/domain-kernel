----------------------- MODULE DiscoveryLeaseTakeover ------------------------
EXTENDS Integers

CONSTANT EnforceLeaseGuard

Original == "original"
Resumed == "resumed"
Callers == {Original, Resumed}

VARIABLES lease, capturedToken, expectedVersion, version, attempted, saved,
          originalSavedAfterTakeover

vars == <<lease, capturedToken, expectedVersion, version, attempted, saved,
          originalSavedAfterTakeover>>

\* Start after the original call's extraction checkpoint. Normalize its version to zero.
Init ==
    /\ lease = [owner |-> Original, token |-> 1, expired |-> FALSE]
    /\ capturedToken = [caller \in Callers |-> IF caller = Original THEN 1 ELSE 0]
    /\ expectedVersion = [caller \in Callers |-> 0]
    /\ version = 0
    /\ attempted = {}
    /\ saved = {}
    /\ originalSavedAfterTakeover = FALSE

ExpireOriginal ==
    /\ lease.owner = Original
    /\ ~lease.expired
    /\ lease' = [lease EXCEPT !.expired = TRUE]
    /\ UNCHANGED <<capturedToken, expectedVersion, version, attempted, saved,
                    originalSavedAfterTakeover>>

\* The lease claim commits before the resumed invocation attempts a checkpoint.
Takeover ==
    /\ lease.owner = Original
    /\ lease.expired
    /\ lease' = [owner |-> Resumed, token |-> lease.token + 1, expired |-> FALSE]
    /\ capturedToken' = [capturedToken EXCEPT ![Resumed] = lease'.token]
    /\ expectedVersion' = [expectedVersion EXCEPT ![Resumed] = version]
    /\ UNCHANGED <<version, attempted, saved, originalSavedAfterTakeover>>

Pending(caller) ==
    /\ caller \notin attempted
    /\ (caller = Original \/ lease.owner = Resumed)

OwnsLease(caller) ==
    /\ caller = lease.owner
    /\ capturedToken[caller] = lease.token
    /\ ~lease.expired

CanSave(caller) ==
    /\ version = expectedVersion[caller]
    /\ (EnforceLeaseGuard => OwnsLease(caller))

\* A single transaction renews the lease and saves the version-checked checkpoint.
CommitCheckpoint(caller) ==
    /\ Pending(caller)
    /\ CanSave(caller)
    /\ IF EnforceLeaseGuard
       THEN /\ lease' = [lease EXCEPT !.token = @ + 1]
            /\ capturedToken' = [capturedToken EXCEPT ![caller] = lease'.token]
       ELSE UNCHANGED <<lease, capturedToken>>
    /\ version' = version + 1
    /\ expectedVersion' = [expectedVersion EXCEPT ![caller] = version']
    /\ attempted' = attempted \cup {caller}
    /\ saved' = saved \cup {caller}
    /\ originalSavedAfterTakeover' =
        (originalSavedAfterTakeover \/ (caller = Original /\ lease.owner = Resumed))

RejectCheckpoint(caller) ==
    /\ Pending(caller)
    /\ ~CanSave(caller)
    /\ attempted' = attempted \cup {caller}
    /\ UNCHANGED <<lease, capturedToken, expectedVersion, version, saved,
                    originalSavedAfterTakeover>>

Next ==
    \/ ExpireOriginal
    \/ Takeover
    \/ \E caller \in Callers : CommitCheckpoint(caller) \/ RejectCheckpoint(caller)

Spec == Init /\ [][Next]_vars

TypeOK ==
    /\ lease \in [owner : Callers, token : 1..4, expired : BOOLEAN]
    /\ capturedToken \in [Callers -> 0..4]
    /\ expectedVersion \in [Callers -> 0..2]
    /\ version \in 0..2
    /\ attempted \subseteq Callers
    /\ saved \subseteq attempted
    /\ originalSavedAfterTakeover \in BOOLEAN

NoOriginalSaveAfterTakeover == ~originalSavedAfterTakeover

\* TLC should find a witness refuting each of these reachability probes.
NoOriginalProgress == Original \notin saved
NoTakeoverAtMatchingVersion ==
    ~(lease.owner = Resumed /\ Original \notin attempted /\ version = expectedVersion[Original])
NoResumedProgress == Resumed \notin saved
=============================================================================
