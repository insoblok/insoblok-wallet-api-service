import asyncio
from web3 import Web3, AsyncWeb3, WebSocketProvider

ws_url = "wss://mainnet.infura.io/ws/v3/cd21ca163b6547678b4753d4f8a3a73a"
network_name="ethereum mainnet"
async def test():
    async with AsyncWeb3(WebSocketProvider(ws_url)) as w3:
        subscription_id = await w3.eth.subscribe("newHeads")
        print(f"Subscribed to {network_name}. Subscription ID: {subscription_id}")
        
        # Process blocks
        async for block in w3.socket.process_subscriptions():
            print(block)
            if 'result' in block and 'number' in block['result']:
                block_number = block['result']['number']
                print(f"[{network_name}] New block: #{block_number}")
                
                # Get full block with transactions
                full_block = await w3.eth.get_block(block_number, full_transactions=True)
                # await self.process_block_transactions(w3, full_block, network_name)
                print(full_block)
                
asyncio.run(test())