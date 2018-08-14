pragma solidity ^0.4.20;

contract IRealitio {
    function notifyOfArbitrationRequest(bytes32 question_id, address requester, uint256 max_previous) external;
    function submitAnswerByArbitrator(bytes32 question_id, bytes32 answer, address answerer) external; 
    function questions(bytes32 question_id) view public returns (bytes32, address, uint32, uint32, uint32, bool, uint256, bytes32, bytes32, uint256) ;
    function commitments(bytes32 commitment_id) view public returns (uint32, bool, bytes32);
}
