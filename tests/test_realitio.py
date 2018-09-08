from ethereum.tools import tester
from ethereum.tools.tester import ABIContract, TransactionFailed
from pytest import fixture, raises
from utils import longTo32Bytes, bytesToLong, bytesToHexString, stringToBytes, longToHexString
from reporting_utils import proceedToDesignatedReporting, proceedToInitialReporting, proceedToNextRound, proceedToFork, finalizeFork

REALITIO_YES = longTo32Bytes(long(1))
REALITIO_NO  = longTo32Bytes(long(0))
REALITIO_INVALID = "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff".decode('hex')

def bytes32ToHexString(bts):
    return longToHexString(bytesToLong(bts), 64)

def test_realitio_true_last_correct(localFixture, controller, universe):
	_test_answer_set(localFixture, controller, universe, REALITIO_YES, REALITIO_NO, True)

def test_realitio_true_last_incorrect(localFixture, controller, universe):
	_test_answer_set(localFixture, controller, universe, REALITIO_NO, REALITIO_YES, True)

def test_realitio_false_last_correct(localFixture, controller, universe):
	_test_answer_set(localFixture, controller, universe, REALITIO_NO, REALITIO_YES, False)

def test_realitio_false_last_incorrect(localFixture, controller, universe):
	_test_answer_set(localFixture, controller, universe, REALITIO_YES, REALITIO_NO, False)

def test_realitio_invalid_last_correct(localFixture, controller, universe):
	_test_answer_set(localFixture, controller, universe, REALITIO_INVALID, REALITIO_NO, False)

def test_realitio_invalid_last_incorrect_true(localFixture, controller, universe):
	_test_answer_set(localFixture, controller, universe, REALITIO_YES, REALITIO_INVALID, False)

def test_realitio_invalid_last_incorrect_false(localFixture, controller, universe):
	_test_answer_set(localFixture, controller, universe, REALITIO_NO, REALITIO_INVALID, False)

def _test_answer_set(localFixture, controller, universe, realitio_answer_final, realitio_answer_wrong, augur_bool):

    augarb = controller.lookup("AugurArbitrator")
    realitio = controller.lookup("Realitio")
    cash = controller.lookup("Cash")

    (a_rep_faucet, k_rep_faucet) = (tester.a0, tester.k0)

    (a_asker, k_asker) = (tester.a1, tester.k1)

    (a_market_owner, k_market_owner) = (tester.a2, tester.k2)

    (a_answerer1, k_answerer1) = (tester.a3, tester.k3)
    (a_answerer2, k_answerer2) = (tester.a4, tester.k4)

    (a_reporter, k_reporter) = (tester.a5, tester.k5)

    (a_arb_requester, k_arb_requester) = (tester.a8, tester.k8)


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

    question_id = realitiocon.askQuestion(template_id, "Is this thing on?", augurarbcon.address, timeout, opening_ts, nonce, sender=k_asker)

    answer_hist_hash = []
    answer_hist_addr = []
    answer_hist_bond = []
    answer_hist_answ = []

    answer_hist_hash.append(realitiocon.questions(question_id)[8])
    realitiocon.submitAnswer(question_id, realitio_answer_final, 0, sender=k_answerer1, value=321)
    answer_hist_addr.append(a_answerer1)
    answer_hist_bond.append(321)
    answer_hist_answ.append(realitio_answer_final)

    answer_hist_hash.append(realitiocon.questions(question_id)[8])

    realitiocon.submitAnswer(question_id, realitio_answer_wrong, 0, sender=k_answerer2, value=642)

    answer_hist_addr.append(a_answerer2)
    answer_hist_bond.append(642)
    answer_hist_answ.append(realitio_answer_wrong)

    answer_hist_hash.append(realitiocon.questions(question_id)[8])
    realitiocon.submitAnswer(question_id, realitio_answer_final, 0, sender=k_answerer1, value=1400)
    answer_hist_addr.append(a_answerer1)
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
    assert rep.balanceOf(a_rep_faucet) > 0


    # Revert if the max_previous is too low
    with raises(TransactionFailed):
        augurarbcon.requestArbitration(question_id, 320, value=12345, sender=k_arb_requester)

    # Revert if you haven't yet requested arbitration
    with raises(TransactionFailed):
        augurarbcon.createMarket("Is this thing on?", timeout, opening_ts, a_asker, nonce, a_reporter, value=valbond)

    augurarbcon.requestArbitration(question_id, 0, value=12345, sender=k_arb_requester)

    # Fail if the contract doesn't yet own sufficient REP
    with raises(TransactionFailed):
        augurarbcon.createMarket("Is this thing on?", timeout, opening_ts, a_asker, nonce, a_reporter, value=valbond)

    # Make sure the arbitrator contract has some REP for the validity bond
    # TODO: Work out how to prevent someone else from spending the REP before you can use it
    # Either use an intermediate contract owned per-user or do something clever with transferFrom
    rep.transfer(augurarbcon.address, noshowbond, sender=k_rep_faucet)
    assert rep.balanceOf(augurarbcon.address) == noshowbond 

    # This will do some checks then call:
    # IMarket market = universe.createYesNoMarket.value(msg.value)( now+1, 0, market_token, a_reporter, 0x0, question, "");

    augurarbcon.createMarket("Is this thing on?", timeout, opening_ts, a_asker, nonce, a_reporter, value=valbond)

    # You can only do this once per question
    rep.transfer(augurarbcon.address, noshowbond, sender=k_rep_faucet)
    with raises(TransactionFailed):
        augurarbcon.createMarket("Is this thing on?", timeout, opening_ts, a_asker, nonce, a_reporter, value=valbond)

    market_addr = augurarbcon.realitio_questions(question_id)[2]
    owner_addr = augurarbcon.realitio_questions(question_id)[3]

	# The following is mostly copied from test_reporting.py
	# We only cover the happy case, assuming the Augur tests will cover other cases

	# TODO: Test various different potential final answers, including invalid

    market = localFixture.applySignature('Market', market_addr)
    proceedToDesignatedReporting(localFixture, market)

    reporter_stake = universe.getOrCacheDesignatedReportStake()
    rep.transfer(a_reporter, reporter_stake, sender=k_rep_faucet)

    augur_answer_in_realitio = None
    if augur_bool is None:
        market.doInitialReport([0, 0], True, sender=k_reporter)
        augur_answer_realitio_hex = "0xffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"
    elif augur_bool:
        market.doInitialReport([0, market.getNumTicks()], False, sender=k_reporter)
        augur_answer_realitio_hex = "0x0000000000000000000000000000000000000000000000000000000000000001";
    else:
        market.doInitialReport([market.getNumTicks(), 0], False, sender=k_reporter)
        augur_answer_realitio_hex = "0x0000000000000000000000000000000000000000000000000000000000000000";

    # the market is now assigned a fee window
    newFeeWindowAddress = market.getFeeWindow()
    assert newFeeWindowAddress
    feeWindow = localFixture.applySignature('FeeWindow', newFeeWindowAddress)

    # time marches on and the market can be finalized
    localFixture.contracts["Time"].setTimestamp(feeWindow.getEndTime() + 1)
    market.finalize()

    hash_before_arb_report = realitiocon.questions(question_id)[8]

    with raises(TransactionFailed, message="answerer mismatch should fail"):
        augurarbcon.reportAnswer(question_id, answer_hist_hash[-1], realitio_answer_final, 1400, tester.a9, False)
  
    assert not realitiocon.isFinalized(question_id)

    augurarbcon.reportAnswer(question_id, answer_hist_hash[-1], realitio_answer_final, 1400, a_answerer1, False)

    assert realitiocon.isFinalized(question_id)
    assert hash_before_arb_report != realitiocon.questions(question_id)[8]

    with raises(TransactionFailed, message="You can only report an answer once"):
        augurarbcon.reportAnswer(question_id, answer_hist_hash[-1], realitio_answer_final, 1400, a_answerer1, False)

    ans = realitiocon.getFinalAnswer(question_id)
    assert bytes32ToHexString(ans) == augur_answer_realitio_hex

    claimer = None
    if (bytes32ToHexString(realitio_answer_final) == augur_answer_realitio_hex):
        claimer = a_answerer1
    else:
        claimer = a_arb_requester

    answer_hist_hash.append(hash_before_arb_report)
    answer_hist_addr.append(claimer)
    answer_hist_bond.append(0)
    answer_hist_answ.append(ans)

    claimer_start_bal = realitiocon.balanceOf(claimer)
    realitiocon.claimWinnings(
        question_id, 
        answer_hist_hash[::-1],
        answer_hist_addr[::-1],
        answer_hist_bond[::-1],
        answer_hist_answ[::-1]
    )
    claimer_end_bal = realitiocon.balanceOf(claimer)

    assert (claimer_end_bal - claimer_start_bal) > 0


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

@fixture
def universe(localFixture, kitchenSinkSnapshot):
    return ABIContract(localFixture.chain, kitchenSinkSnapshot['universe'].translator, kitchenSinkSnapshot['universe'].address)

@fixture
def cash(localFixture, kitchenSinkSnapshot):
    return ABIContract(localFixture.chain, kitchenSinkSnapshot['cash'].translator, kitchenSinkSnapshot['cash'].address)
