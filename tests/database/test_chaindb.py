import pytest

from hypothesis import (
    given,
    strategies as st,
)

import rlp
from trie import (
    BinaryTrie,
    HexaryTrie,
)

from eth_utils import (
    keccak,
)

from evm.db import (
    get_db_backend,
)
from evm.db.chain import (
    ChainDB,
)
from evm.db.state import (
    MainAccountStateDB,
)
from evm.exceptions import (
    BlockNotFound,
    ParentNotFound,
)
from evm.rlp.headers import (
    BlockHeader,
)
from evm.tools.fixture_tests import (
    assert_rlp_equal,
)
from evm.utils.db import (
    get_empty_root_hash,
    make_block_hash_to_score_lookup_key,
    make_block_number_to_hash_lookup_key,
)
from evm.vm.forks.frontier.blocks import (
    FrontierBlock,
)
from evm.vm.forks.homestead.blocks import (
    HomesteadBlock,
)


A_ADDRESS = b"\xaa" * 20
B_ADDRESS = b"\xbb" * 20


def set_empty_root(chaindb, header):
    root_hash = get_empty_root_hash(chaindb)
    header.transaction_root = root_hash
    header.receipt_root = root_hash
    header.state_root = root_hash


@pytest.fixture(params=[MainAccountStateDB])
def chaindb(request):
    if request.param is MainAccountStateDB:
        trie_class = HexaryTrie
    else:
        trie_class = BinaryTrie
    return ChainDB(
        get_db_backend(),
        account_state_class=request.param,
        trie_class=trie_class,
    )


@pytest.fixture(params=[0, 10, 999])
def header(request):
    block_number = request.param
    difficulty = 1
    gas_limit = 1
    return BlockHeader(difficulty, block_number, gas_limit)


@pytest.fixture(params=[FrontierBlock, HomesteadBlock])
def block(request, header):
    return request.param(header)


def test_add_block_number_to_hash_lookup(chaindb, block):
    block_number_to_hash_key = make_block_number_to_hash_lookup_key(block.number)
    assert not chaindb.exists(block_number_to_hash_key)
    chaindb._add_block_number_to_hash_lookup(block.header)
    assert chaindb.exists(block_number_to_hash_key)


def test_persist_header(chaindb, header):
    with pytest.raises(BlockNotFound):
        chaindb.get_block_header_by_hash(header.hash)
    number_to_hash_key = make_block_hash_to_score_lookup_key(header.hash)
    assert not chaindb.exists(number_to_hash_key)

    chaindb.persist_header(header)

    assert chaindb.get_block_header_by_hash(header.hash) == header
    assert chaindb.exists(number_to_hash_key)


@given(seed=st.binary(min_size=32, max_size=32))
def test_persist_header_unknown_parent(chaindb, header, seed):
    header.parent_hash = keccak(seed)
    with pytest.raises(ParentNotFound):
        chaindb.persist_header(header)


def test_persist_block(chaindb, block):
    set_empty_root(chaindb, block.header)
    block_to_hash_key = make_block_hash_to_score_lookup_key(block.hash)
    assert not chaindb.exists(block_to_hash_key)
    chaindb.persist_block(block)
    assert chaindb.exists(block_to_hash_key)


def test_get_score(chaindb):
    genesis = BlockHeader(difficulty=1, block_number=0, gas_limit=0)
    chaindb.persist_header(genesis)

    genesis_score_key = make_block_hash_to_score_lookup_key(genesis.hash)
    genesis_score = rlp.decode(chaindb.db.get(genesis_score_key), sedes=rlp.sedes.big_endian_int)
    assert genesis_score == 1
    assert chaindb.get_score(genesis.hash) == 1

    block1 = BlockHeader(difficulty=10, block_number=1, gas_limit=0, parent_hash=genesis.hash)
    chaindb.persist_header(block1)

    block1_score_key = make_block_hash_to_score_lookup_key(block1.hash)
    block1_score = rlp.decode(chaindb.db.get(block1_score_key), sedes=rlp.sedes.big_endian_int)
    assert block1_score == 11
    assert chaindb.get_score(block1.hash) == 11


def test_get_block_header_by_hash(chaindb, block, header):
    set_empty_root(chaindb, block.header)
    set_empty_root(chaindb, header)
    chaindb.persist_block(block)
    block_header = chaindb.get_block_header_by_hash(block.hash)
    assert_rlp_equal(block_header, header)


def test_lookup_block_hash(chaindb, block):
    set_empty_root(chaindb, block.header)
    chaindb._add_block_number_to_hash_lookup(block.header)
    block_hash = chaindb.lookup_block_hash(block.number)
    assert block_hash == block.hash
