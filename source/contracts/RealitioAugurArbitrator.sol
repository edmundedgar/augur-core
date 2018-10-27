pragma solidity ^0.4.25;

import 'BalanceHolder.sol';
import 'IRealitio.sol';

import 'strings.sol';

contract ICash{}

contract IMarket {
    function getWinningPayoutNumerator(uint256 _outcome) public view returns (uint256);
    function isFinalized() public view returns (bool);
    function isInvalid() public view returns (bool);
}

contract IUniverse {
    function getWinningChildUniverse() public view returns (IUniverse);
    function createYesNoMarket(uint256 _endTime, uint256 _feePerEthInWei, ICash _denominationToken, address _designatedReporterAddress, bytes32 _topic, string _description, string _extraInfo) public 
    payable returns (IMarket _newMarket); 
}

contract RealitioAugurArbitrator is BalanceHolder {

    using strings for *;

    IRealitio public realitio;
    uint256 public template_id;
    uint256 dispute_fee;

    ICash public market_token;
    IUniverse public latest_universe;

    bytes32 constant REALITIO_INVALID = 0xffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff;
    bytes32 constant REALITIO_YES     = 0x0000000000000000000000000000000000000000000000000000000000000001;
    bytes32 constant REALITIO_NO      = 0x0000000000000000000000000000000000000000000000000000000000000000;
    uint256 constant AUGUR_YES_INDEX  = 1;
    uint256 constant AUGUR_NO_INDEX   = 0;
    string constant REALITIO_DELIMITER = '␟';

    event LogRequestArbitration(
        bytes32 indexed question_id,
        uint256 fee_paid,
        address requester,
        uint256 remaining
    );

    struct RealitioQuestion {
        uint256 bounty;
        address disputer;
        IMarket augur_market;
        address owner;
    }

    mapping(bytes32 => RealitioQuestion) public realitio_questions;

    modifier onlyInitialized() { 
        require(dispute_fee > 0);
        _;
    }

    modifier onlyUninitialized() { 
        require(dispute_fee == 0); // uninitialized
        _;
    }

    /// @notice Initialize a new contract
    /// @param _realitio The address of the realitio contract you arbitrate for
    /// @param _template_id The ID of the realitio template we support. 
    /// @param _dispute_fee The fee this contract will charge for resolution
    /// @param _genesis_universe The earliest supported Augur universe
    /// @param _market_token The token used by the market we create, typically Augur's wrapped ETH
    function initialize(IRealitio _realitio, uint256 _template_id, uint256 _dispute_fee, IUniverse _genesis_universe, ICash _market_token) 
        onlyUninitialized
    external {

        require(_dispute_fee > 0);
        require(_realitio != IRealitio(0x0));
        require(_genesis_universe != IUniverse(0x0));
        require(_market_token != ICash(0x0));

        dispute_fee = _dispute_fee;
        template_id = _template_id;
        realitio = _realitio;
        latest_universe = _genesis_universe;
        market_token = _market_token;

    }

    /// @notice Register a new child universe after a fork
    /// @dev Anyone can create Augur universes but the "correct" ones should be in a single line from the official genesis universe
    /// @dev If a universe goes into a forking state, someone will need to call this before you can create new markets.
    function addForkedUniverse() 
        onlyInitialized
    external {
        IUniverse child_universe = IUniverse(latest_universe).getWinningChildUniverse();
        latest_universe = child_universe;
    }

    /// @notice Trim the realitio question content to the part before the initial delimiter.
    /// @dev The Realitio question is a list of parameters for a template.
    /// @dev We throw away the subsequent parameters of the question.
    /// @dev The first item in the (supported) template must be the title.
    /// @dev Subsequent items (category, lang) aren't needed in Augur.
    /// @dev This does not support more complex templates, eg selects which also need a list of answrs.
    function _trimQuestion(string q) 
    internal pure returns (string) {
        return q.toSlice().split(REALITIO_DELIMITER.toSlice()).toString();
    }

    function _callAugurMarketCreate(bytes32 question_id, string question, address designated_reporter) 
    internal {
        realitio_questions[question_id].augur_market = latest_universe.createYesNoMarket.value(msg.value)( now, 0, market_token, designated_reporter, 0x0, _trimQuestion(question), "");
        realitio_questions[question_id].owner = msg.sender;
    }

    /// @notice Create a market in Augur and store the creator as its owner
    /// @dev Anyone can call this, and calling this will give them the rights to claim the bounty
    /// @dev They will need have sent this contract some REP for the no-show bond.
    /// @param question The question content (a delimited parameter list)
    /// @param timeout The timeout between rounds, set when the question was created
    /// @param opening_ts The opening timestamp for the question, set when the question was created
    /// @param asker The address that created the question, ie the msg.sender of the original realitio.askQuestion call
    /// @param nonce The nonce for the question, set when the question was created
    /// @param designated_reporter The Augur designated reporter. We let the market creator choose this, if it's bad the Augur dispute resolution should sort it out
    function createMarket(
        string question, uint32 timeout, uint32 opening_ts, address asker, uint256 nonce,
        address designated_reporter
    ) 
        onlyInitialized
    external payable {
        // Reconstruct the question ID from the content
        bytes32 question_id = keccak256(keccak256(template_id, opening_ts, question), this, timeout, asker, nonce);

        // Arbitration must have been requested, and the market not yet created.
        require(realitio_questions[question_id].bounty > 0);
        require(realitio_questions[question_id].augur_market == IMarket(0x0));

        // Create a market in Augur
        _callAugurMarketCreate(question_id, question, designated_reporter);
    }

    /// @notice Return data needed to verify the last history item
    /// @dev Filters the question struct from Realitio to stuff we need
    /// @dev Broken out into its own function to avoid stack depth limitations
    /// @param question_id The realitio question
    /// @param last_history_hash The history hash when you gave your answer 
    /// @param last_answer_or_commitment_id The last answer given, or its commitment ID if it was a commitment 
    /// @param last_bond The bond paid in the last answer given
    /// @param last_answerer The account that submitted the last answer (or its commitment)
    /// @param is_commitment Whether the last answer was submitted with commit->reveal
    function _verifyInput(
        bytes32 question_id, 
        bytes32 last_history_hash, bytes32 last_answer_or_commitment_id, uint256 last_bond, address last_answerer, bool is_commitment
    ) internal view returns (bool, bytes32) {
        require(realitio.isPendingArbitration(question_id));
        bytes32 history_hash = realitio.getHistoryHash(question_id);
        
        require(history_hash == keccak256(last_history_hash, last_answer_or_commitment_id, last_bond, last_answerer, is_commitment));

    }

    /// @notice Given the last history entry, get whether they had a valid answer if so what it was
    /// @dev These just need to be fetched from Realitio, but they can't be fetched directly because we don't store them to save gas
    /// @dev To get the final answer, we need to reconstruct the final answer using the history hash
    /// @dev TODO: This should probably be in a library offered by Realitio
    /// @param question_id The ID of the realitio question
    /// @param last_history_hash The history hash when you gave your answer 
    /// @param last_answer_or_commitment_id The last answer given, or its commitment ID if it was a commitment 
    /// @param last_bond The bond paid in the last answer given
    /// @param last_answerer The account that submitted the last answer (or its commitment)
    /// @param is_commitment Whether the last answer was submitted with commit->reveal
    function _answerData(
        bytes32 question_id, 
        bytes32 last_history_hash, bytes32 last_answer_or_commitment_id, uint256 last_bond, address last_answerer, bool is_commitment
    ) internal view returns (bool, bytes32) {
    
        bool is_pending_arbitration;
        bytes32 history_hash;

        // If the question hasn't been answered, nobody is ever right
        if (last_bond == 0) {
            return (false, bytes32(0));
        }

        bytes32 last_answer;
        bool is_answered;

        if (is_commitment) {
            uint256 reveal_ts;
            bool is_revealed;
            bytes32 revealed_answer;
            (reveal_ts, is_revealed, revealed_answer) = realitio.commitments(last_answer_or_commitment_id);

            if (is_revealed) {
                last_answer = revealed_answer;
                is_answered = true;
            } else {
                // Shouldn't normally happen, but if the last answerer might still reveal when we are called, bail out and wait for them.
                require(reveal_ts < uint32(now));
                is_answered = false;
            }
        } else {
            last_answer = last_answer_or_commitment_id;
            is_answered = true;
        }

        return (is_answered, last_answer);

    }

    /// @notice Get the answer from the Augur market and map it to a Realitio value
    /// @param market The Augur market
    function realitioAnswerFromAugurMarket(
       IMarket market
    ) 
        onlyInitialized
    public view returns (bytes32) {
        bytes32 answer;
        if (market.isInvalid()) {
            answer = REALITIO_INVALID;
        } else {
            uint256 no_val = market.getWinningPayoutNumerator(AUGUR_NO_INDEX);
            uint256 yes_val = market.getWinningPayoutNumerator(AUGUR_YES_INDEX);
            if (yes_val == no_val) {
                answer = REALITIO_INVALID;
            } else {
                if (yes_val > no_val) {
                    answer = REALITIO_YES;
                } else {
                    answer = REALITIO_NO;
                }
            }
        }
        return answer;
    }

    /// @notice Report the answer from a finalized Augur market to a Realitio contract with a question awaiting arbitration
    /// @dev Pays the arbitration bounty to whoever created the Augur market. Probably the same person will call this function, but they don't have to.
    /// @dev We need to know who gave the final answer and what it was, as they need to be supplied as the arbitration winner if the last answer is right
    /// @dev These just need to be fetched from Realitio, but they can't be fetched directly because to save gas, Realitio doesn't store them 
    /// @dev To get the final answer, we need to reconstruct the final answer using the history hash
    /// @param question_id The ID of the question you're reporting on
    /// @param last_history_hash The history hash when you gave your answer 
    /// @param last_answer_or_commitment_id The last answer given, or its commitment ID if it was a commitment 
    /// @param last_bond The bond paid in the last answer given
    /// @param last_answerer The account that submitted the last answer (or its commitment)
    /// @param is_commitment Whether the last answer was submitted with commit->reveal
    function reportAnswer(
        bytes32 question_id,
        bytes32 last_history_hash, bytes32 last_answer_or_commitment_id, uint256 last_bond, address last_answerer, bool is_commitment
    ) 
        onlyInitialized
    public {

        IMarket market = realitio_questions[question_id].augur_market;

        // There must be an open bounty
        require(realitio_questions[question_id].bounty > 0);

        bool is_answered; // the answer was provided, not just left as an unrevealed commit
        bytes32 last_answer;

        _verifyInput(question_id, last_history_hash, last_answer_or_commitment_id, last_bond, last_answerer, is_commitment);

        (is_answered, last_answer) = _answerData(question_id, last_history_hash, last_answer_or_commitment_id, last_bond, last_answerer, is_commitment);  

        require(market.isFinalized());

        bytes32 answer = realitioAnswerFromAugurMarket(market);
        address winner;
        if (is_answered && last_answer == answer) {
            winner = last_answerer;
        } else {
            // If the final answer is wrong, we assign the person who paid for arbitration.
            // See https://realitio.github.io/docs/html/arbitrators.html for why.
            winner = realitio_questions[question_id].disputer;
        }

        realitio.submitAnswerByArbitrator(question_id, answer, winner);

        address owner = realitio_questions[question_id].owner;
        balanceOf[owner] += realitio_questions[question_id].bounty;

        delete realitio_questions[question_id];

    }

    /// @notice Return the dispute fee for the specified question. 0 indicates that we won't arbitrate it.
    /// @dev Uses a general default, but can be over-ridden on a question-by-question basis.
    function getDisputeFee(bytes32) 
    public constant returns (uint256) {
        return dispute_fee;
    }


    /// @notice Request arbitration, freezing the question until we send submitAnswerByArbitrator
    /// @dev The bounty can be paid only in part, in which case the last person to pay will be considered the payer
    /// @dev Will trigger an error if the notification fails, eg because the question has already been finalized
    /// @param question_id The question in question
    /// @param max_previous The highest bond level we should accept (used to check the state hasn't changed)
    function requestArbitration(bytes32 question_id, uint256 max_previous) 
        onlyInitialized
    external payable returns (bool) {

        uint256 arbitration_fee = getDisputeFee(question_id);
        require(arbitration_fee > 0);
        require(msg.value >= arbitration_fee);

        realitio.notifyOfArbitrationRequest(question_id, msg.sender, max_previous);

        realitio_questions[question_id].bounty = msg.value;
        realitio_questions[question_id].disputer = msg.sender;

        LogRequestArbitration(question_id, msg.value, msg.sender, 0);

    }

}
