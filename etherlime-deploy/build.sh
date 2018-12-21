cp ../source/contracts/RealitioAugurArbitrator.sol contracts/
cp ../source/contracts/IRealitio.sol contracts/
cp ../source/contracts/BalanceHolder.sol contracts/
cp ../source/contracts/IBalanceHolder.sol contracts/
cp ../source/contracts/strings.sol contracts/
perl -i.bak -pe "s/import '/import '.\//g" contracts/*.sol
