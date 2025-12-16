from web3 import Web3
from dotenv import load_dotenv
import os

load_dotenv()

NETWORK_CONFIGS = ({
    "solana_mainnet": {
        "name": "Solana Mainnet",
        "rpc_url": os.getenv("SOLANA_MAINNET_RPC_URL", "https://api.mainnet-beta.solana.com"),
        "explorer": "https://explorer.solana.com"
    },
    "solana_devnet": {
        "name": "Solana Devnet",
        "rpc_url": os.getenv("SOLANA_DEVNET_RPC_URL", "https://api.devnet.solana.com"),
        "explorer": "https://explorer.solana.com?cluster=devnet"
    },
    "solana_testnet": {
        "name": "Solana Testnet",
        "rpc_url": os.getenv("SOLANA_TESTNET_RPC_URL", "https://api.testnet.solana.com"),
        "explorer": "https://explorer.solana.com?cluster=testnet"
    }
})

