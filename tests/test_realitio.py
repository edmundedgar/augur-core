from ethereum.tools import tester
from ethereum.tools.tester import ABIContract, TransactionFailed
from pytest import fixture, raises
from utils import longTo32Bytes, PrintGasUsed, fix, bytesToLong, bytesToHexString, stringToBytes, longToHexString
from datetime import timedelta
from os import path
from ethereum.utils import ecsign, sha3, normalize_key, int_to_32bytearray, bytearray_to_bytestr, zpad

from reporting_utils import proceedToDesignatedReporting, proceedToInitialReporting, proceedToNextRound, proceedToFork, finalizeFork

def bytes32ToHexString(bts):
    return longToHexString(bytesToLong(bts), 64)

def test_realitio_true_last_correct(localFixture, controller, universe):
	realitiocon = _test_answer_set(localFixture, controller, universe, longTo32Bytes(long(1)), longTo32Bytes(long(0)), True)

def test_realitio_true_last_incorrect(localFixture, controller, universe):
	realitiocon = _test_answer_set(localFixture, controller, universe, longTo32Bytes(long(0)), longTo32Bytes(long(1)), True)

def test_realitio_false_last_correct(localFixture, controller, universe):
	realitiocon = _test_answer_set(localFixture, controller, universe, longTo32Bytes(long(0)), longTo32Bytes(long(1)), False)

def test_realitio_false_last_incorrect(localFixture, controller, universe):
	realitiocon = _test_answer_set(localFixture, controller, universe, longTo32Bytes(long(0)), longTo32Bytes(long(1)), False)

def test_realitio_invalid_last_correct(localFixture, controller, universe):
    pass

def test_realitio_invalid_last_incorrect_true(localFixture, controller, universe):
    pass

def test_realitio_invalid_last_incorrect_false(localFixture, controller, universe):
    pass

	#realitiocon = _test_answer_set(localFixture, controller, universe, longTo32Bytes(long(1)), longTo32Bytes(long(0)), False)
	#realitiocon = _test_answer_set(localFixture, controller, universe, longTo32Bytes(long(1)), longTo32Bytes(long(0)), False)
	#realitiocon = _test_answer_set(localFixture, controller, universe, longTo32Bytes(long(1)), longTo32Bytes(long(0)), True)
	#realitiocon = _test_answer_set(localFixture, controller, universe, longTo32Bytes(long(1)), longTo32Bytes(long(0)), None)
	
def _test_answer_set(localFixture, controller, universe, realitio_answer_final, realitio_answer_wrong, augur_bool):

    augarb = controller.lookup("AugurArbitrator")
    realitio = controller.lookup("Realitio")
    cash = controller.lookup("Cash")

    # Params used in the Realitio question
    template_id = 0 # This is our basic yes/no question type
    opening_ts = 1000000123 # Any timestamp or 0, we'll use one past for simplicity
    nonce = 987654321 # Usually 0
    timeout = 1

    augurarbcon = localFixture.uploadAndAddToController("../source/contracts/AugurArbitrator.sol", lookupKey="AugurArbitrator")

    augurarbcon.initialize(realitio, template_id, 12345, universe.address, cash);
    assert augurarbcon.getDisputeFee("0x0") == 12345 # All question ids are the same
    assert augurarbcon.latest_universe() == universe.address
    assert augurarbcon.market_token() == cash
    assert augurarbcon.template_id() == template_id

    realitiocon = localFixture.uploadAndAddToController("../source/contracts/Realitio.sol", lookupKey="Realitio")

    question_asker = tester.a1
    question_id = realitiocon.askQuestion(template_id, "Is this thing on?", augurarbcon.address, timeout, opening_ts, nonce, sender=tester.k1)

    answer_hist_hash = []
    answer_hist_addr = []
    answer_hist_bond = []
    answer_hist_answ = []

    answer_hist_hash.append(realitiocon.questions(question_id)[8])
    realitiocon.submitAnswer(question_id, realitio_answer_final, 0, sender=tester.k3, value=321)
    answer_hist_addr.append(tester.a3)
    answer_hist_bond.append(321)
    answer_hist_answ.append(realitio_answer_final)

    answer_hist_hash.append(realitiocon.questions(question_id)[8])

    realitiocon.submitAnswer(question_id, realitio_answer_wrong, 0, sender=tester.k4, value=642)

    answer_hist_addr.append(tester.a4)
    answer_hist_bond.append(642)
    answer_hist_answ.append(realitio_answer_wrong)

    answer_hist_hash.append(realitiocon.questions(question_id)[8])
    realitiocon.submitAnswer(question_id, realitio_answer_final, 0, sender=tester.k3, value=1400)
    answer_hist_addr.append(tester.a3)
    answer_hist_bond.append(1400)
    answer_hist_answ.append(realitio_answer_final)

    # Validity bond in ETH
    valbond = universe.getOrCacheValidityBond()
    assert valbond > 1

    # No show bond in REP
    noshowbond = universe.getOrCacheDesignatedReportNoShowBond();
    assert noshowbond > 0;
 
    repaddr = universe.getReputationToken()
    rep = localFixture.applySignature('ReputationToken', repaddr)
    t0rep = rep.balanceOf(tester.a0)
    assert t0rep > 0

    # We'll make ourselves the designated reporter. Somebody else would work too though.
    designated_reporter = tester.a1

    # Revert if the max_previous is too low
    with raises(TransactionFailed):
        augurarbcon.requestArbitration(question_id, 320, value=12345, sender=tester.k8)

    # Revert if you haven't yet requested arbitration
    with raises(TransactionFailed):
        augurarbcon.createMarket("Is this thing on?", timeout, opening_ts, question_asker, nonce, designated_reporter)

    augurarbcon.requestArbitration(question_id, 0, value=12345, sender=tester.k8)

    # Fail if the contract doesn't yet own sufficient REP
    with raises(TransactionFailed):
        augurarbcon.createMarket("Is this thing on?", timeout, opening_ts, question_asker, nonce, designated_reporter, value=valbond)

    # Make sure the arbitrator contract has some REP for the validity bond
    # TODO: Work out how to prevent someone else from spending the REP before you can use it
    # Either use an intermediate contract owned per-user or do something clever with transferFrom
    rep.transfer(augurarbcon.address, noshowbond, sender=tester.k0)
    assert rep.balanceOf(augurarbcon.address) == noshowbond 

    # This will do some checks then call:
    # IMarket market = universe.createYesNoMarket.value(msg.value)( now+1, 0, market_token, designated_reporter, 0x0, question, "");

    augurarbcon.createMarket("Is this thing on?", timeout, opening_ts, question_asker, nonce, designated_reporter, value=valbond)

    # You can only do this once per question
    rep.transfer(augurarbcon.address, noshowbond, sender=tester.k0)
    with raises(TransactionFailed):
        augurarbcon.createMarket("Is this thing on?", timeout, opening_ts, question_asker, nonce, designated_reporter, value=valbond)

    market_addr = augurarbcon.realitio_questions(question_id)[2]
    owner_addr = augurarbcon.realitio_questions(question_id)[3]

	# The following is mostly copied from test_reporting.py
	# We only cover the happy case, assuming the Augur tests will cover other cases

	# TODO: Test various different potential final answers, including invalid

    market = localFixture.applySignature('Market', market_addr)
    proceedToDesignatedReporting(localFixture, market)

    reporter_stake = universe.getOrCacheDesignatedReportStake()
    rep.transfer(designated_reporter, reporter_stake, sender=tester.k0)

    augur_answer_in_realitio = None
    if augur_bool is None:
        market.doInitialReport([0, 0], True, sender=tester.k1)
        augur_answer_realitio_hex = "0xffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"
    elif augur_bool:
        market.doInitialReport([0, market.getNumTicks()], False, sender=tester.k1)
        augur_answer_realitio_hex = "0x0000000000000000000000000000000000000000000000000000000000000001";
    else:
        market.doInitialReport([market.getNumTicks(), 0], False, sender=tester.k1)
        augur_answer_realitio_hex = "0x0000000000000000000000000000000000000000000000000000000000000000";

    # the market is now assigned a fee window
    newFeeWindowAddress = market.getFeeWindow()
    assert newFeeWindowAddress
    feeWindow = localFixture.applySignature('FeeWindow', newFeeWindowAddress)

    # time marches on and the market can be finalized
    localFixture.contracts["Time"].setTimestamp(feeWindow.getEndTime() + 1)
    market.finalize()

    hash_before_arb_report = realitiocon.questions(question_id)[8]

    with raises(TransactionFailed, message="answer mismatch should fail"):
        augurarbcon.reportAnswer(question_id, answer_hist_hash[-1], realitio_answer_final, 1400, tester.a5, False)
  
    assert not realitiocon.isFinalized(question_id)

    augurarbcon.reportAnswer(question_id, answer_hist_hash[-1], realitio_answer_final, 1400, tester.a3, False)

    assert realitiocon.isFinalized(question_id)
    assert hash_before_arb_report != realitiocon.questions(question_id)[8]

    ans = realitiocon.getFinalAnswer(question_id)
    assert bytes32ToHexString(ans) == augur_answer_realitio_hex

    claimer = None
    if (bytes32ToHexString(realitio_answer_final) == augur_answer_realitio_hex):
        claimer = tester.a3
    else:
        claimer = tester.a8

    answer_hist_hash.append(hash_before_arb_report)
    answer_hist_addr.append(claimer)
    answer_hist_bond.append(0)
    answer_hist_answ.append(ans)

    start_bal = realitiocon.balanceOf(claimer)
    realitiocon.claimWinnings(
        question_id, 
        answer_hist_hash[::-1],
        answer_hist_addr[::-1],
        answer_hist_bond[::-1],
        answer_hist_answ[::-1]
    )
    end_bal = realitiocon.balanceOf(claimer)

    return realitiocon


@fixture(scope="session")
def localSnapshot(fixture, kitchenSinkSnapshot):
    fixture.resetToSnapshot(kitchenSinkSnapshot)
    augur = fixture.contracts["Augur"]
    return fixture.createSnapshot()

@fixture
def localFixture(fixture, localSnapshot):
    fixture.resetToSnapshot(localSnapshot)
    return fixture

@fixture
def controller(localFixture, kitchenSinkSnapshot):
    return localFixture.contracts['Controller']

BASE_PATH = path.dirname(path.abspath(__file__))
def resolveRelativePath(relativeFilePath):
    return path.abspath(path.join(BASE_PATH, relativeFilePath))

@fixture
def universe(localFixture, kitchenSinkSnapshot):
    return ABIContract(localFixture.chain, kitchenSinkSnapshot['universe'].translator, kitchenSinkSnapshot['universe'].address)

@fixture
def cash(localFixture, kitchenSinkSnapshot):
    return ABIContract(localFixture.chain, kitchenSinkSnapshot['cash'].translator, kitchenSinkSnapshot['cash'].address)
