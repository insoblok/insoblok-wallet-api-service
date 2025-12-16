# services/token_service.py
SEPOLIA_TOKENS = {
    'LINK': {
        'address': '0x779877A7B0D9E8603169DdbD7836e478b4624789',
        'decimals': 18,
        'name': 'Chainlink',
        'symbol': 'LINK',
        'faucet': 'https://faucets.chain.link/sepolia'
    },
    'DAI': {
        'address': '0xFF34B3d4Aee8ddCd6F9AFFFB6Fe49bD371b8a357',
        'decimals': 18,
        'name': 'Dai Stablecoin',
        'symbol': 'DAI',
        'faucet': 'https://testnet.compound.finance/faucet'  # May need to check
    },
    'WETH': {
        'address': '0xfFf9976782d46CC05630D1f6eBAb18b2324d6B14',
        'decimals': 18,
        'name': 'Wrapped Ether',
        'symbol': 'WETH',
        'faucet': 'Wrap Sepolia ETH'
    }
}