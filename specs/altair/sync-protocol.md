# Altair -- Minimal Light Client

**Notice**: This document is a work-in-progress for researchers and implementers.

## Table of contents

<!-- TOC -->
<!-- START doctoc generated TOC please keep comment here to allow auto update -->
<!-- DON'T EDIT THIS SECTION, INSTEAD RE-RUN doctoc TO UPDATE -->

- [Introduction](#introduction)
- [Constants](#constants)
- [Preset](#preset)
  - [Misc](#misc)
- [Containers](#containers)
  - [`LightClientBootstrap`](#lightclientbootstrap)
  - [`LightClientUpdate`](#lightclientupdate)
  - [`LightClientFinalityUpdate`](#lightclientfinalityupdate)
  - [`LightClientOptimisticUpdate`](#lightclientoptimisticupdate)
  - [`LightClientStore`](#lightclientstore)
- [Helper functions](#helper-functions)
  - [`is_sync_committee_update`](#is_sync_committee_update)
  - [`is_finality_update`](#is_finality_update)
  - [`get_subtree_index`](#get_subtree_index)
  - [`is_next_sync_committee_known`](#is_next_sync_committee_known)
  - [`get_safety_threshold`](#get_safety_threshold)
  - [`is_better_update`](#is_better_update)
- [Light client initialization](#light-client-initialization)
  - [`initialize_light_client_store`](#initialize_light_client_store)
- [Light client state updates](#light-client-state-updates)
  - [`validate_light_client_update`](#validate_light_client_update)
  - [`apply_light_client_update`](#apply_light_client_update)
  - [`try_light_client_store_force_update`](#try_light_client_store_force_update)
  - [`process_light_client_update`](#process_light_client_update)
  - [`process_light_client_finality_update`](#process_light_client_finality_update)
  - [`process_light_client_optimistic_update`](#process_light_client_optimistic_update)
- [Light client sync process](#light-client-sync-process)
- [Deriving light client data](#deriving-light-client-data)
  - [`create_light_client_bootstrap`](#create_light_client_bootstrap)
  - [`create_light_client_update`](#create_light_client_update)
  - [`create_light_client_finality_update`](#create_light_client_finality_update)
  - [`create_light_client_optimistic_update`](#create_light_client_optimistic_update)
- [Networking](#networking)
  - [Configuration](#configuration)
  - [The gossip domain: gossipsub](#the-gossip-domain-gossipsub)
    - [Topics and messages](#topics-and-messages)
      - [Global topics](#global-topics)
        - [`light_client_finality_update`](#light_client_finality_update)
        - [`light_client_optimistic_update`](#light_client_optimistic_update)
  - [The Req/Resp domain](#the-reqresp-domain)
    - [Messages](#messages)
      - [GetLightClientBootstrap](#getlightclientbootstrap)
      - [LightClientUpdatesByRange](#lightclientupdatesbyrange)
      - [GetLightClientFinalityUpdate](#getlightclientfinalityupdate)
      - [GetLightClientOptimisticUpdate](#getlightclientoptimisticupdate)
  - [Light clients](#light-clients)
- [Validator assignments](#validator-assignments)
  - [Beacon chain responsibilities](#beacon-chain-responsibilities)
  - [Sync committee](#sync-committee)

<!-- END doctoc generated TOC please keep comment here to allow auto update -->
<!-- /TOC -->

## Introduction

The beacon chain is designed to be light client friendly for constrained environments to
access Ethereum with reasonable safety and liveness.
Such environments include resource-constrained devices (e.g. phones for trust-minimized wallets)
and metered VMs (e.g. blockchain VMs for cross-chain bridges).

This document suggests a minimal light client design for the beacon chain that
uses sync committees introduced in [this beacon chain extension](./beacon-chain.md).

## Constants

| Name | Value |
| - | - |
| `FINALIZED_ROOT_INDEX` | `get_generalized_index(BeaconState, 'finalized_checkpoint', 'root')` (= 105) |
| `CURRENT_SYNC_COMMITTEE_INDEX` | `get_generalized_index(BeaconState, 'current_sync_committee')` (= 54) |
| `NEXT_SYNC_COMMITTEE_INDEX` | `get_generalized_index(BeaconState, 'next_sync_committee')` (= 55) |

## Preset

### Misc

| Name | Value | Unit | Duration |
| - | - | - | - |
| `MIN_SYNC_COMMITTEE_PARTICIPANTS` | `1` | validators | |
| `UPDATE_TIMEOUT` | `SLOTS_PER_EPOCH * EPOCHS_PER_SYNC_COMMITTEE_PERIOD` | slots | ~27.3 hours |

## Containers

### `LightClientBootstrap`

```python
class LightClientBootstrap(Container):
    # The requested beacon block header
    header: BeaconBlockHeader
    # Current sync committee corresponding to `header`
    current_sync_committee: SyncCommittee
    current_sync_committee_branch: Vector[Bytes32, floorlog2(CURRENT_SYNC_COMMITTEE_INDEX)]
```

### `LightClientUpdate`

```python
class LightClientUpdate(Container):
    # The beacon block header that is attested to by the sync committee
    attested_header: BeaconBlockHeader
    # Next sync committee corresponding to `attested_header`
    next_sync_committee: SyncCommittee
    next_sync_committee_branch: Vector[Bytes32, floorlog2(NEXT_SYNC_COMMITTEE_INDEX)]
    # The finalized beacon block header attested to by Merkle branch
    finalized_header: BeaconBlockHeader
    finality_branch: Vector[Bytes32, floorlog2(FINALIZED_ROOT_INDEX)]
    # Sync committee aggregate signature
    sync_aggregate: SyncAggregate
    # Slot at which the aggregate signature was created (untrusted)
    signature_slot: Slot
```

### `LightClientFinalityUpdate`

```python
class LightClientFinalityUpdate(Container):
    # The beacon block header that is attested to by the sync committee
    attested_header: BeaconBlockHeader
    # The finalized beacon block header attested to by Merkle branch
    finalized_header: BeaconBlockHeader
    finality_branch: Vector[Bytes32, floorlog2(FINALIZED_ROOT_INDEX)]
    # Sync committee aggregate signature
    sync_aggregate: SyncAggregate
    # Slot at which the aggregate signature was created (untrusted)
    signature_slot: Slot
```

### `LightClientOptimisticUpdate`

```python
class LightClientOptimisticUpdate(Container):
    # The beacon block header that is attested to by the sync committee
    attested_header: BeaconBlockHeader
    # Sync committee aggregate signature
    sync_aggregate: SyncAggregate
    # Slot at which the aggregate signature was created (untrusted)
    signature_slot: Slot
```

### `LightClientStore`

```python
@dataclass
class LightClientStore(object):
    # Beacon block header that is finalized
    finalized_header: BeaconBlockHeader
    # Sync committees corresponding to the header
    current_sync_committee: SyncCommittee
    next_sync_committee: SyncCommittee
    # Best available header to switch finalized head to if we see nothing else
    best_valid_update: Optional[LightClientUpdate]
    # Most recent available reasonably-safe header
    optimistic_header: BeaconBlockHeader
    # Max number of active participants in a sync committee (used to calculate safety threshold)
    previous_max_active_participants: uint64
    current_max_active_participants: uint64
```

## Helper functions

### `is_sync_committee_update`

```python
def is_sync_committee_update(update: LightClientUpdate) -> bool:
    return update.next_sync_committee_branch != [Bytes32() for _ in range(floorlog2(NEXT_SYNC_COMMITTEE_INDEX))]
```

### `is_finality_update`

```python
def is_finality_update(update: LightClientUpdate) -> bool:
    return update.finality_branch != [Bytes32() for _ in range(floorlog2(FINALIZED_ROOT_INDEX))]
```

### `get_subtree_index`

```python
def get_subtree_index(generalized_index: GeneralizedIndex) -> uint64:
    return uint64(generalized_index % 2**(floorlog2(generalized_index)))
```

### `is_next_sync_committee_known`

```python
def is_next_sync_committee_known(store: LightClientStore) -> bool:
    return store.next_sync_committee != SyncCommittee()
```

### `get_safety_threshold`

```python
def get_safety_threshold(store: LightClientStore) -> uint64:
    return max(
        store.previous_max_active_participants,
        store.current_max_active_participants,
    ) // 2
```

### `is_better_update`

```python
def is_better_update(new_update: LightClientUpdate, old_update: LightClientUpdate) -> bool:
    # Compare supermajority (> 2/3) sync committee participation
    max_active_participants = len(new_update.sync_aggregate.sync_committee_bits)
    new_num_active_participants = sum(new_update.sync_aggregate.sync_committee_bits)
    old_num_active_participants = sum(old_update.sync_aggregate.sync_committee_bits)
    new_has_supermajority = new_num_active_participants * 3 >= max_active_participants * 2
    old_has_supermajority = old_num_active_participants * 3 >= max_active_participants * 2
    if new_has_supermajority != old_has_supermajority:
        return new_has_supermajority > old_has_supermajority
    if not new_has_supermajority and new_num_active_participants != old_num_active_participants:
        return new_num_active_participants > old_num_active_participants

    # Compare presence of relevant sync committee
    new_has_relevant_sync_committee = is_sync_committee_update(new_update) and (
        compute_sync_committee_period(compute_epoch_at_slot(new_update.attested_header.slot)) ==
        compute_sync_committee_period(compute_epoch_at_slot(new_update.signature_slot))
    )
    old_has_relevant_sync_committee = is_sync_committee_update(old_update) and (
        compute_sync_committee_period(compute_epoch_at_slot(old_update.attested_header.slot)) ==
        compute_sync_committee_period(compute_epoch_at_slot(old_update.signature_slot))
    )
    if new_has_relevant_sync_committee != old_has_relevant_sync_committee:
        return new_has_relevant_sync_committee > old_has_relevant_sync_committee

    # Compare indication of any finality
    new_has_finality = is_finality_update(new_update)
    old_has_finality = is_finality_update(old_update)
    if new_has_finality != old_has_finality:
        return new_has_finality > old_has_finality

    # Compare sync committee finality
    if new_has_finality:
        new_has_sync_committee_finality = (
            compute_sync_committee_period(compute_epoch_at_slot(new_update.finalized_header.slot)) ==
            compute_sync_committee_period(compute_epoch_at_slot(new_update.attested_header.slot))
        )
        old_has_sync_committee_finality = (
            compute_sync_committee_period(compute_epoch_at_slot(old_update.finalized_header.slot)) ==
            compute_sync_committee_period(compute_epoch_at_slot(old_update.attested_header.slot))
        )
        if new_has_sync_committee_finality != old_has_sync_committee_finality:
            return new_has_sync_committee_finality > old_has_sync_committee_finality

    # Tiebreaker 1: Sync committee participation beyond supermajority
    if new_num_active_participants != old_num_active_participants:
        return new_num_active_participants > old_num_active_participants

    # Tiebreaker 2: Prefer older data (fewer changes to best)
    if new_update.attested_header.slot != old_update.attested_header.slot:
        return new_update.attested_header.slot < old_update.attested_header.slot
    return new_update.signature_slot < old_update.signature_slot
```

## Light client initialization

A light client maintains its state in a `store` object of type `LightClientStore`. `initialize_light_client_store` initializes a new `store` with a received `LightClientBootstrap` derived from a given `trusted_block_root`.

### `initialize_light_client_store`

```python
def initialize_light_client_store(trusted_block_root: Root,
                                  bootstrap: LightClientBootstrap) -> LightClientStore:
    assert hash_tree_root(bootstrap.header) == trusted_block_root

    assert is_valid_merkle_branch(
        leaf=hash_tree_root(bootstrap.current_sync_committee),
        branch=bootstrap.current_sync_committee_branch,
        depth=floorlog2(CURRENT_SYNC_COMMITTEE_INDEX),
        index=get_subtree_index(CURRENT_SYNC_COMMITTEE_INDEX),
        root=bootstrap.header.state_root,
    )

    return LightClientStore(
        finalized_header=bootstrap.header,
        current_sync_committee=bootstrap.current_sync_committee,
        next_sync_committee=SyncCommittee(),
        best_valid_update=None,
        optimistic_header=bootstrap.header,
        previous_max_active_participants=0,
        current_max_active_participants=0,
    )
```

## Light client state updates

A light client receives `update`, `finality_update` and `optimistic_update` objects of type `LightClientUpdate`, `LightClientFinalityUpdate` and `LightClientOptimisticUpdate`. Every `update` triggers `process_light_client_update(store, update, current_slot, genesis_validators_root)` where `current_slot` is the current slot based on a local clock. Likewise, every `finality_update` triggers `process_light_client_finality_update`, and every `optimistic_update` triggers `process_light_client_optimistic_update`. `try_light_client_store_force_update` MAY be called based on use case dependent heuristics if light client sync appears stuck.

### `validate_light_client_update`

```python
def validate_light_client_update(store: LightClientStore,
                                 update: LightClientUpdate,
                                 current_slot: Slot,
                                 genesis_validators_root: Root) -> None:
    # Verify sync committee has sufficient participants
    sync_aggregate = update.sync_aggregate
    assert sum(sync_aggregate.sync_committee_bits) >= MIN_SYNC_COMMITTEE_PARTICIPANTS

    # Verify update does not skip a sync committee period
    assert current_slot >= update.signature_slot > update.attested_header.slot >= update.finalized_header.slot
    store_period = compute_sync_committee_period(compute_epoch_at_slot(store.finalized_header.slot))
    signature_period = compute_sync_committee_period(compute_epoch_at_slot(update.signature_slot))
    if is_next_sync_committee_known(store):
        assert signature_period in (store_period, store_period + 1)
    else:
        assert signature_period == store_period

    # Verify update is relevant
    attested_period = compute_sync_committee_period(compute_epoch_at_slot(update.attested_header.slot))
    assert (
        update.attested_header.slot > store.finalized_header.slot
        or (
            not is_next_sync_committee_known(store)
            and attested_period == store_period and is_sync_committee_update(update)
        )
    )

    # Verify that the `finality_branch`, if present, confirms `finalized_header`
    # to match the finalized checkpoint root saved in the state of `attested_header`.
    # Note that the genesis finalized checkpoint root is represented as a zero hash.
    if not is_finality_update(update):
        assert update.finalized_header == BeaconBlockHeader()
    else:
        if update.finalized_header.slot == GENESIS_SLOT:
            finalized_root = Bytes32()
            assert update.finalized_header == BeaconBlockHeader()
        else:
            finalized_root = hash_tree_root(update.finalized_header)
        assert is_valid_merkle_branch(
            leaf=finalized_root,
            branch=update.finality_branch,
            depth=floorlog2(FINALIZED_ROOT_INDEX),
            index=get_subtree_index(FINALIZED_ROOT_INDEX),
            root=update.attested_header.state_root,
        )

    # Verify that the `next_sync_committee`, if present, actually is the next sync committee saved in the
    # state of the `attested_header`
    if not is_sync_committee_update(update):
        assert update.next_sync_committee == SyncCommittee()
    else:
        if attested_period == store_period and is_next_sync_committee_known(store):
            assert update.next_sync_committee == store.next_sync_committee
        assert is_valid_merkle_branch(
            leaf=hash_tree_root(update.next_sync_committee),
            branch=update.next_sync_committee_branch,
            depth=floorlog2(NEXT_SYNC_COMMITTEE_INDEX),
            index=get_subtree_index(NEXT_SYNC_COMMITTEE_INDEX),
            root=update.attested_header.state_root,
        )

    # Verify sync committee aggregate signature
    if signature_period == store_period:
        sync_committee = store.current_sync_committee
    else:
        sync_committee = store.next_sync_committee
    participant_pubkeys = [
        pubkey for (bit, pubkey) in zip(sync_aggregate.sync_committee_bits, sync_committee.pubkeys)
        if bit
    ]
    fork_version = compute_fork_version(compute_epoch_at_slot(update.signature_slot))
    domain = compute_domain(DOMAIN_SYNC_COMMITTEE, fork_version, genesis_validators_root)
    signing_root = compute_signing_root(update.attested_header, domain)
    assert bls.FastAggregateVerify(participant_pubkeys, signing_root, sync_aggregate.sync_committee_signature)
```

### `apply_light_client_update`

```python
def apply_light_client_update(store: LightClientStore, update: LightClientUpdate) -> None:
    store_period = compute_sync_committee_period(compute_epoch_at_slot(store.finalized_header.slot))
    finalized_period = compute_sync_committee_period(compute_epoch_at_slot(update.finalized_header.slot))
    if not is_next_sync_committee_known(store):
        assert finalized_period == store_period
        store.next_sync_committee = update.next_sync_committee
    elif finalized_period == store_period + 1:
        store.current_sync_committee = store.next_sync_committee
        store.next_sync_committee = update.next_sync_committee
        store.previous_max_active_participants = store.current_max_active_participants
        store.current_max_active_participants = 0
    if update.finalized_header.slot > store.finalized_header.slot:
        store.finalized_header = update.finalized_header
        if store.finalized_header.slot > store.optimistic_header.slot:
            store.optimistic_header = store.finalized_header
```

### `try_light_client_store_force_update`

```python
def try_light_client_store_force_update(store: LightClientStore, current_slot: Slot) -> None:
    if (
        current_slot > store.finalized_header.slot + UPDATE_TIMEOUT
        and store.best_valid_update is not None
    ):
        # Forced best update when the update timeout has elapsed
        if store.best_valid_update.finalized_header.slot <= store.finalized_header.slot:
            store.best_valid_update.finalized_header = store.best_valid_update.attested_header
        apply_light_client_update(store, store.best_valid_update)
        store.best_valid_update = None
```

### `process_light_client_update`

```python
def process_light_client_update(store: LightClientStore,
                                update: LightClientUpdate,
                                current_slot: Slot,
                                genesis_validators_root: Root) -> None:
    validate_light_client_update(store, update, current_slot, genesis_validators_root)

    sync_committee_bits = update.sync_aggregate.sync_committee_bits

    # Update the best update in case we have to force-update to it if the timeout elapses
    if (
        store.best_valid_update is None
        or is_better_update(update, store.best_valid_update)
    ):
        store.best_valid_update = update

    # Track the maximum number of active participants in the committee signatures
    store.current_max_active_participants = max(
        store.current_max_active_participants,
        sum(sync_committee_bits),
    )

    # Update the optimistic header
    if (
        sum(sync_committee_bits) > get_safety_threshold(store)
        and update.attested_header.slot > store.optimistic_header.slot
    ):
        store.optimistic_header = update.attested_header

    # Update finalized header
    if (
        sum(sync_committee_bits) * 3 >= len(sync_committee_bits) * 2
        and (
            update.finalized_header.slot > store.finalized_header.slot
            or (
                not is_next_sync_committee_known(store)
                and is_sync_committee_update(update) and is_finality_update(update) and (
                    compute_sync_committee_period(compute_epoch_at_slot(update.finalized_header.slot)) ==
                    compute_sync_committee_period(compute_epoch_at_slot(update.attested_header.slot))
                )
            )
        )
    ):
        # Normal update through 2/3 threshold
        apply_light_client_update(store, update)
        store.best_valid_update = None
```

### `process_light_client_finality_update`

```python
def process_light_client_finality_update(store: LightClientStore,
                                         finality_update: LightClientFinalityUpdate,
                                         current_slot: Slot,
                                         genesis_validators_root: Root) -> None:
    update = LightClientUpdate(
        attested_header=finality_update.attested_header,
        next_sync_committee=SyncCommittee(),
        next_sync_committee_branch=[Bytes32() for _ in range(floorlog2(NEXT_SYNC_COMMITTEE_INDEX))],
        finalized_header=finality_update.finalized_header,
        finality_branch=finality_update.finality_branch,
        sync_aggregate=finality_update.sync_aggregate,
        signature_slot=finality_update.signature_slot,
    )
    process_light_client_update(store, update, current_slot, genesis_validators_root)
```

### `process_light_client_optimistic_update`

```python
def process_light_client_optimistic_update(store: LightClientStore,
                                           optimistic_update: LightClientOptimisticUpdate,
                                           current_slot: Slot,
                                           genesis_validators_root: Root) -> None:
    update = LightClientUpdate(
        attested_header=optimistic_update.attested_header,
        next_sync_committee=SyncCommittee(),
        next_sync_committee_branch=[Bytes32() for _ in range(floorlog2(NEXT_SYNC_COMMITTEE_INDEX))],
        finalized_header=BeaconBlockHeader(),
        finality_branch=[Bytes32() for _ in range(floorlog2(FINALIZED_ROOT_INDEX))],
        sync_aggregate=optimistic_update.sync_aggregate,
        signature_slot=optimistic_update.signature_slot,
    )
    process_light_client_update(store, update, current_slot, genesis_validators_root)
```

## Light client sync process

1. The light client MUST be configured out-of-band with a spec/preset (including fork schedule), with `genesis_state` (including `genesis_time` and `genesis_validators_root`), and with a trusted block root. The trusted block SHOULD be within the weak subjectivity period, and its root SHOULD be from a finalized `Checkpoint`.

2. The local clock is initialized based on the configured `genesis_time`, and the current fork digest is determined to browse for and connect to relevant light client data providers.

3. The light client fetches a [`LightClientBootstrap`](#lightclientbootstrap) object for the configured trusted block root. The `bootstrap` object is passed to [`initialize_light_client_store`](#initialize_light_client_store) to obtain a local [`LightClientStore`](#lightclientstore).

4. The light client tracks the sync committee periods `finalized_period` from `store.finalized_header.slot`, `optimistic_period` from `store.optimistic_header.slot`, and `current_period` from `current_slot` based on the local clock.

   1. When `finalized_period == optimistic_period` and [`is_next_sync_committee_known`](#is_next_sync_committee_known) indicates `False`, the light client fetches a [`LightClientUpdate`](#lightclientupdate) for `finalized_period`. If `finalized_period == current_period`, this fetch SHOULD be scheduled at a random time before `current_period` advances.

   2. When `finalized_period + 1 < current_period`, the light client fetches a `LightClientUpdate` for each sync committee period in range `[finalized_period + 1, current_period)` (current period excluded)

   3. When `finalized_period + 1 >= current_period`, the light client keeps observing [`LightClientFinalityUpdate`](#lightclientfinalityupdate) and [`LightClientOptimisticUpdate`](#lightclientoptimisticupdate). Received objects are passed to [`process_light_client_finality_update`](#process_light_client_finality_update) and [`process_light_client_optimistic_update`](#process_light_client_optimistic_update). This ensures that `finalized_header` and `optimistic_header` reflect the latest blocks.

5. `try_light_client_store_force_update` MAY be called based on use case dependent heuristics if light client sync appears stuck. If available, falling back to an alternative syncing mechanism to cover the affected sync committee period is preferred.

## Deriving light client data

Full nodes are expected to derive light client data from historic blocks and states and provide it to other clients.

### `create_light_client_bootstrap`

```python
def create_light_client_bootstrap(state: BeaconState) -> LightClientBootstrap:
    assert compute_epoch_at_slot(state.slot) >= ALTAIR_FORK_EPOCH
    assert state.slot == state.latest_block_header.slot

    return LightClientBootstrap(
        header=BeaconBlockHeader(
            slot=state.latest_block_header.slot,
            proposer_index=state.latest_block_header.proposer_index,
            parent_root=state.latest_block_header.parent_root,
            state_root=hash_tree_root(state),
            body_root=state.latest_block_header.body_root,
        ),
        current_sync_committee=state.current_sync_committee,
        current_sync_committee_branch=build_proof(state.get_backing(), CURRENT_SYNC_COMMITTEE_INDEX)
    )
```

Full nodes SHOULD provide `LightClientBootstrap` for all finalized epoch boundary blocks in the epoch range `[max(ALTAIR_FORK_EPOCH, current_epoch - MIN_EPOCHS_FOR_BLOCK_REQUESTS), current_epoch]` where `current_epoch` is defined by the current wall-clock time. Full nodes MAY also provide `LightClientBootstrap` for other blocks.

Blocks are considered to be epoch boundary blocks if their block root can occur as part of a valid `Checkpoint`, i.e., if their slot is the initial slot of an epoch, or if all following slots through the initial slot of the next epoch are empty (no block proposed / orphaned).

`LightClientBootstrap` is computed from the block's immediate post state (without applying empty slots).

### `create_light_client_update`

To form a `LightClientUpdate`, the following historical states and blocks are needed:
- `state`: the post state of any block with a post-Altair parent block
- `block`: the corresponding block
- `attested_state`: the post state of the block referred to by `block.parent_root`
- `finalized_block`: the block referred to by `attested_state.finalized_checkpoint.root`

```python
def create_light_client_update(state: BeaconState,
                               block: SignedBeaconBlock,
                               attested_state: BeaconState,
                               finalized_block: Optional[SignedBeaconBlock]) -> LightClientUpdate:
    assert compute_epoch_at_slot(attested_state.slot) >= ALTAIR_FORK_EPOCH
    assert sum(block.message.body.sync_aggregate.sync_committee_bits) >= MIN_SYNC_COMMITTEE_PARTICIPANTS

    assert state.slot == state.latest_block_header.slot
    header = state.latest_block_header.copy()
    header.state_root = hash_tree_root(state)
    assert hash_tree_root(header) == hash_tree_root(block.message)
    signature_period = compute_sync_committee_period(compute_epoch_at_slot(block.message.slot))

    assert attested_state.slot == attested_state.latest_block_header.slot
    attested_header = attested_state.latest_block_header.copy()
    attested_header.state_root = hash_tree_root(attested_state)
    assert hash_tree_root(attested_header) == block.message.parent_root
    attested_period = compute_sync_committee_period(compute_epoch_at_slot(attested_header.slot))

    # `next_sync_committee` is only useful if the message is signed by the current sync committee
    if attested_period == signature_period:
        next_sync_committee = attested_state.next_sync_committee
        next_sync_committee_branch = build_proof(attested_state.get_backing(), NEXT_SYNC_COMMITTEE_INDEX)
    else:
        next_sync_committee = SyncCommittee()
        next_sync_committee_branch = [Bytes32() for _ in range(floorlog2(NEXT_SYNC_COMMITTEE_INDEX))]

    # Indicate finality whenever possible
    if finalized_block is not None:
        if finalized_block.message.slot != GENESIS_SLOT:
            finalized_header = BeaconBlockHeader(
                slot=finalized_block.message.slot,
                proposer_index=finalized_block.message.proposer_index,
                parent_root=finalized_block.message.parent_root,
                state_root=finalized_block.message.state_root,
                body_root=hash_tree_root(finalized_block.message.body),
            )
            assert hash_tree_root(finalized_header) == attested_state.finalized_checkpoint.root
        else:
            finalized_header = BeaconBlockHeader()
            assert attested_state.finalized_checkpoint.root == Bytes32()
        finality_branch = build_proof(attested_state.get_backing(), FINALIZED_ROOT_INDEX)
    else:
        finalized_header = BeaconBlockHeader()
        finality_branch = [Bytes32() for _ in range(floorlog2(FINALIZED_ROOT_INDEX))]

    return LightClientUpdate(
        attested_header=attested_header,
        next_sync_committee=next_sync_committee,
        next_sync_committee_branch=next_sync_committee_branch,
        finalized_header=finalized_header,
        finality_branch=finality_branch,
        sync_aggregate=block.message.body.sync_aggregate,
        signature_slot=block.message.slot,
    )
```

Full nodes SHOULD provide the best derivable `LightClientUpdate` (according to `is_better_update`) for each sync committee period covering any epochs in range `[max(ALTAIR_FORK_EPOCH, current_epoch - MIN_EPOCHS_FOR_BLOCK_REQUESTS), current_epoch]` where `current_epoch` is defined by the current wall-clock time. Full nodes MAY also provide `LightClientUpdate` for other sync committee periods.

- `LightClientUpdate` are assigned to sync committee periods based on their `attested_header.slot`
- `LightClientUpdate` are only considered if `compute_sync_committee_period(compute_epoch_at_slot(update.attested_header.slot)) == compute_sync_committee_period(compute_epoch_at_slot(update.signature_slot))`
- Only `LightClientUpdate` with `next_sync_committee` as selected by fork choice are provided, regardless of ranking by `is_better_update`. To uniquely identify a non-finalized sync committee fork, all of `period`, `current_sync_committee` and `next_sync_committee` need to be incorporated, as sync committees may reappear over time.

### `create_light_client_finality_update`

```python
def create_light_client_finality_update(update: LightClientUpdate) -> LightClientFinalityUpdate:
    return LightClientFinalityUpdate(
        attested_header=update.attested_header,
        finalized_header=update.finalized_header,
        finality_branch=update.finality_branch,
        sync_aggregate=update.sync_aggregate,
        signature_slot=update.signature_slot,
    )
```

Full nodes SHOULD provide the `LightClientFinalityUpdate` with the highest `attested_header.slot` (if multiple, highest `signature_slot`) as selected by fork choice, and SHOULD support a push mechanism to deliver new `LightClientFinalityUpdate` whenever `finalized_header` changes.

### `create_light_client_optimistic_update`

```python
def create_light_client_optimistic_update(update: LightClientUpdate) -> LightClientOptimisticUpdate:
    return LightClientOptimisticUpdate(
        attested_header=update.attested_header,
        sync_aggregate=update.sync_aggregate,
        signature_slot=update.signature_slot,
    )
```

Full nodes SHOULD provide the `LightClientOptimisticUpdate` with the highest `attested_header.slot` (if multiple, highest `signature_slot`) as selected by fork choice, and SHOULD support a push mechanism to deliver new `LightClientOptimisticUpdate` whenever `attested_header` changes.

## Networking

This section extends the [networking specification for Altair](./p2p-interface.md) with additional messages, topics and data to the Req-Resp and Gossip domains.

### Configuration

| Name | Value | Description |
| - | - | - |
| `MAX_REQUEST_LIGHT_CLIENT_UPDATES` | `2**7` (= 128) | Maximum number of `LightClientUpdate` instances in a single request |

### The gossip domain: gossipsub

Gossip meshes are added to allow light clients stay in sync with the network.

#### Topics and messages

New global topics are added to provide light clients with the latest updates.

| name | Message Type |
| - | - |
| `light_client_finality_update` | `LightClientFinalityUpdate` |
| `light_client_optimistic_update` | `LightClientOptimisticUpdate` |

##### Global topics

###### `light_client_finality_update`

This topic is used to propagate the latest `LightClientFinalityUpdate` to light clients, allowing them to keep track of the latest `finalized_header`.

The following validations MUST pass before forwarding the `finality_update` on the network.
- _[IGNORE]_ No other `finality_update` with a lower or equal `finalized_header.slot` was already forwarded on the network
- _[IGNORE]_ The `finality_update` is received after the block at `signature_slot` was given enough time to propagate through the network -- i.e. validate that one-third of `finality_update.signature_slot` has transpired (`SECONDS_PER_SLOT / INTERVALS_PER_SLOT` seconds after the start of the slot, with a `MAXIMUM_GOSSIP_CLOCK_DISPARITY` allowance)

For full nodes, the following validations MUST additionally pass before forwarding the `finality_update` on the network.
- _[IGNORE]_ The received `finality_update` matches the locally computed one exactly (as defined in [`create_light_client_finality_update`](#create_light_client_finality_update))

For light clients, the following validations MUST additionally pass before forwarding the `finality_update` on the network.
- _[REJECT]_ The `finality_update` is valid -- i.e. validate that `process_light_client_finality_update` does not indicate errors
- _[IGNORE]_ The `finality_update` advances the `finalized_header` of the local `LightClientStore` -- i.e. validate that processing `finality_update` increases `store.finalized_header.slot`

Light clients SHOULD call `process_light_client_finality_update` even if the message is ignored.

###### `light_client_optimistic_update`

This topic is used to propagate the latest `LightClientOptimisticUpdate` to light clients, allowing them to keep track of the latest `optimistic_header`.

The following validations MUST pass before forwarding the `optimistic_update` on the network.
- _[IGNORE]_ No other `optimistic_update` with a lower or equal `attested_header.slot` was already forwarded on the network
- _[IGNORE]_ The `optimistic_update` is received after the block at `signature_slot` was given enough time to propagate through the network -- i.e. validate that one-third of `optimistic_update.signature_slot` has transpired (`SECONDS_PER_SLOT / INTERVALS_PER_SLOT` seconds after the start of the slot, with a `MAXIMUM_GOSSIP_CLOCK_DISPARITY` allowance)

For full nodes, the following validations MUST additionally pass before forwarding the `optimistic_update` on the network.
- _[IGNORE]_ The received `optimistic_update` matches the locally computed one exactly (as defined in [`create_light_client_optimistic_update`](#create_light_client_optimistic_update))

For light clients, the following validations MUST additionally pass before forwarding the `optimistic_update` on the network.
- _[REJECT]_ The `optimistic_update` is valid -- i.e. validate that `process_light_client_optimistic_update` does not indicate errors
- _[IGNORE]_ The `optimistic_update` either matches corresponding fields of the most recently forwarded `LightClientFinalityUpdate` (if any), or it advances the `optimistic_header` of the local `LightClientStore` -- i.e. validate that processing `optimistic_update` increases `store.optimistic_header.slot`

Light clients SHOULD call `process_light_client_optimistic_update` even if the message is ignored.

### The Req/Resp domain

#### Messages

##### GetLightClientBootstrap

**Protocol ID:** `/eth2/beacon_chain/req/light_client_bootstrap/1/`

Request Content:

```
(
  Root
)
```

Response Content:

```
(
  LightClientBootstrap
)
```

Requests the `LightClientBootstrap` structure corresponding to a given post-Altair beacon block root.

The request MUST be encoded as an SSZ-field.

Peers SHOULD provide results as defined in [`create_light_client_bootstrap`](#create_light_client_bootstrap). To fulfill a request, the requested block's post state needs to be known.

When a `LightClientBootstrap` instance cannot be produced for a given block root, peers SHOULD respond with error code `3: ResourceUnavailable`.

A `ForkDigest`-context based on `compute_fork_version(compute_epoch_at_slot(bootstrap.header.slot))` is used to select the fork namespace of the Response type.

Per `context = compute_fork_digest(fork_version, genesis_validators_root)`:

[0]: # (eth2spec: skip)

| `fork_version`                  | Response SSZ type                    |
| ------------------------------- | ------------------------------------ |
| `GENESIS_FORK_VERSION`          | n/a                                  |
| `ALTAIR_FORK_VERSION` and later | `altair.LightClientBootstrap`        |

##### LightClientUpdatesByRange

**Protocol ID:** `/eth2/beacon_chain/req/light_client_updates_by_range/1/`

Request Content:
```
(
  start_period: uint64
  count: uint64
)
```

Response Content:
```
(
  List[LightClientUpdate, MAX_REQUEST_LIGHT_CLIENT_UPDATES]
)
```

Requests the `LightClientUpdate` instances in the sync committee period range `[start_period, start_period + count)`, leading up to the current head sync committee period as selected by fork choice.

The request MUST be encoded as an SSZ-container.

The response MUST consist of zero or more `response_chunk`. Each _successful_ `response_chunk` MUST contain a single `LightClientUpdate` payload.

Peers SHOULD provide results as defined in [`create_light_client_update`](#create_light_client_update). They MUST respond with at least the earliest known result within the requested range, and MUST send results in consecutive order (by period). The response MUST NOT contain more than `min(MAX_REQUEST_LIGHT_CLIENT_UPDATES, count)` results.

For each `response_chunk`, a `ForkDigest`-context based on `compute_fork_version(compute_epoch_at_slot(update.attested_header.slot))` is used to select the fork namespace of the Response type. Note that this `fork_version` may be different from the one used to verify the `update.sync_aggregate`, which is based on `update.signature_slot`.

Per `context = compute_fork_digest(fork_version, genesis_validators_root)`:

[0]: # (eth2spec: skip)

| `fork_version`                  | Response chunk SSZ type              |
| ------------------------------- | ------------------------------------ |
| `GENESIS_FORK_VERSION`          | n/a                                  |
| `ALTAIR_FORK_VERSION` and later | `altair.LightClientUpdate`           |

##### GetLightClientFinalityUpdate

**Protocol ID:** `/eth2/beacon_chain/req/light_client_finality_update/1/`

No Request Content.

Response Content:

```
(
  LightClientFinalityUpdate
)
```

Requests the latest `LightClientFinalityUpdate` known by a peer.

Peers SHOULD provide results as defined in [`create_light_client_finality_update`](#create_light_client_finality_update).

When no `LightClientFinalityUpdate` is available, peers SHOULD respond with error code `3: ResourceUnavailable`.

A `ForkDigest`-context based on `compute_fork_version(compute_epoch_at_slot(finality_update.attested_header.slot))` is used to select the fork namespace of the Response type. Note that this `fork_version` may be different from the one used to verify the `finality_update.sync_aggregate`, which is based on `finality_update.signature_slot`.

Per `context = compute_fork_digest(fork_version, genesis_validators_root)`:

[0]: # (eth2spec: skip)

| `fork_version`                  | Response SSZ type                    |
| ------------------------------- | ------------------------------------ |
| `GENESIS_FORK_VERSION`          | n/a                                  |
| `ALTAIR_FORK_VERSION` and later | `altair.LightClientFinalityUpdate`   |

##### GetLightClientOptimisticUpdate

**Protocol ID:** `/eth2/beacon_chain/req/light_client_optimistic_update/1/`

No Request Content.

Response Content:

```
(
  LightClientOptimisticUpdate
)
```

Requests the latest `LightClientOptimisticUpdate` known by a peer.

Peers SHOULD provide results as defined in [`create_light_client_optimistic_update`](#create_light_client_optimistic_update).

When no `LightClientOptimisticUpdate` is available, peers SHOULD respond with error code `3: ResourceUnavailable`.

A `ForkDigest`-context based on `compute_fork_version(compute_epoch_at_slot(optimistic_update.attested_header.slot))` is used to select the fork namespace of the Response type. Note that this `fork_version` may be different from the one used to verify the `optimistic_update.sync_aggregate`, which is based on `optimistic_update.signature_slot`.

Per `context = compute_fork_digest(fork_version, genesis_validators_root)`:

[0]: # (eth2spec: skip)

| `fork_version`                  | Response SSZ type                    |
| ------------------------------- | ------------------------------------ |
| `GENESIS_FORK_VERSION`          | n/a                                  |
| `ALTAIR_FORK_VERSION` and later | `altair.LightClientOptimisticUpdate` |

### Light clients

Light clients using libp2p to stay in sync with the network SHOULD subscribe to the [`light_client_finality_update`](#light_client_finality_update) and [`light_client_optimistic_update`](#light_client_optimistic_update) pubsub topics and validate all received messages while the [light client sync process](#light-client-sync-process) supports processing `LightClientFinalityUpdate` and `LightClientOptimistic` structures.

Light clients MAY also collect historic light client data and make it available to other peers. If they do, they SHOULD advertise supported message endpoints in [the Req/Resp domain](#the-reqresp-domain), and MAY also update the contents of their [`Status`](../phase0/p2p-interface.md#status) message to reflect the locally available light client data.

If only limited light client data is locally available, the light client SHOULD use data based on `genesis_block` and `GENESIS_SLOT` in its `Status` message. Hybrid peers that also implement full node functionality MUST only incorporate data based on their full node sync progress into their `Status` message.

## Validator assignments

This section extends the [honest validator specification](./validator.md) with additional responsibilities to enable light clients to sync with the network.

### Beacon chain responsibilities

All full nodes SHOULD subscribe to and provide stability on the [`light_client_finality_update`](#light_client_finality_update) and [`light_client_optimistic_update`](#light_client_optimistic_update) pubsub topics by validating all received messages.

### Sync committee

Whenever fork choice selects a new head block with a sync aggregate participation `>= MIN_SYNC_COMMITTEE_PARTICIPANTS` and a post-Altair parent block, full nodes with at least one validator assigned to the current sync committee at the block's `slot` SHOULD broadcast derived light client data as follows:

- If `finalized_header.slot` increased, a `LightClientFinalityUpdate` SHOULD be broadcasted to the pubsub topic `light_client_finality_update` if no matching message has not yet been forwarded as part of gossip validation.
- If `attested_header.slot` increased, a `LightClientOptimisticUpdate` SHOULD be broadcasted to the pubsub topic `light_client_optimistic_update` if no matching message has not yet been forwarded as part of gossip validation.

These messages SHOULD be broadcasted after one-third of `slot` has transpired (`SECONDS_PER_SLOT / INTERVALS_PER_SLOT` seconds after the start of the slot). To ensure that the corresponding block was given enough time to propagate through the network, they SHOULD NOT be sent earlier. Note that this is different from how other messages are handled, e.g., attestations, which may be sent early.
