from ethereum.tools import tester
from ethereum.tools.tester import ABIContract, TransactionFailed
from pytest import fixture, raises
from utils import longTo32Bytes, PrintGasUsed, fix, bytesToLong, bytesToHexString, stringToBytes, longToHexString
from datetime import timedelta
from os import path
from ethereum.utils import ecsign, sha3, normalize_key, int_to_32bytearray, bytearray_to_bytestr, zpad

from reporting_utils import proceedToDesignatedReporting, proceedToInitialReporting, proceedToNextRound, proceedToFork, finalizeFork

def test_realitio(localFixture, controller, universe):

    augarb = controller.lookup("AugurArbitrator")
    realitio = controller.lookup("Realitio")
    cash = controller.lookup("Cash")

    # Params used in the Realitio question
    template_id = 0
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

    realitiocon.submitAnswer(question_id, longTo32Bytes(long(0)), 0, sender=tester.k1, value=321)

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
        augurarbcon.requestArbitration(question_id, 320, value=12345)

    # Revert if you haven't yet requested arbitration
    with raises(TransactionFailed):
        augurarbcon.createMarket("Is this thing on?", timeout, opening_ts, question_asker, nonce, designated_reporter)

    augurarbcon.requestArbitration(question_id, 321, value=12345)

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

    market.doInitialReport([0, market.getNumTicks()], False, sender=tester.k1)

    # the market is now assigned a fee window
    newFeeWindowAddress = market.getFeeWindow()
    assert newFeeWindowAddress
    feeWindow = localFixture.applySignature('FeeWindow', newFeeWindowAddress)

    # time marches on and the market can be finalized
    localFixture.contracts["Time"].setTimestamp(feeWindow.getEndTime() + 1)
    market.finalize()

    augurarbcon.reportAnswer(question_id, longTo32Bytes(long(0)), longTo32Bytes(long(0)), 321, tester.a1, False)
    ans = realitiocon.getFinalAnswer(question_id)
    ans == 0


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
