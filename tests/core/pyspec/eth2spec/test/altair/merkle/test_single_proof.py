from eth2spec.test.context import (
    spec_state_test,
    with_altair_and_later,
)


def do_single_proof_test(spec, state, leaf, leaf_index):
    yield "state", state
    branch = spec.build_proof(state.get_backing(), leaf_index)
    yield "proof", {
        "leaf": "0x" + leaf.hex(),
        "leaf_index": leaf_index,
        "branch": ['0x' + root.hex() for root in branch]
    }
    assert spec.is_valid_merkle_branch(
        leaf=leaf,
        branch=branch,
        depth=spec.floorlog2(leaf_index),
        index=spec.get_subtree_index(leaf_index),
        root=state.hash_tree_root(),
    )
    assert spec.verify_merkle_proof(
        leaf=leaf,
        proof=branch,
        index=leaf_index,
        root=state.hash_tree_root(),
    )
    assert spec.verify_merkle_multiproof(
        leaves=[leaf],
        proof=branch,
        indices=[leaf_index],
        root=state.hash_tree_root(),
    )


@with_altair_and_later
@spec_state_test
def test_finality_root_merkle_proof(spec, state):
    yield from do_single_proof_test(
        spec,
        state,
        state.finalized_checkpoint.root.hash_tree_root(),
        spec.FINALIZED_ROOT_INDEX,
    )


@with_altair_and_later
@spec_state_test
def test_next_sync_committee_merkle_proof(spec, state):
    yield from do_single_proof_test(
        spec,
        state,
        state.next_sync_committee.hash_tree_root(),
        spec.NEXT_SYNC_COMMITTEE_INDEX,
    )
