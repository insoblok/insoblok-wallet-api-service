import requests
import json

# Test the /evm/balance endpoint for insoblok
# Using the address from the previous logs
test_address = "0xd32682c328adf192ffeca067398a7599628a106a"

# Try different ports (default is 8080 based on README)
ports = [8080, 8000, 8001]
url = None

payload = {
    "chain": "insoblok",
    "address": test_address
}

print("=" * 60)
print("Testing /evm/balance API")
print("=" * 60)
print(f"Request payload:")
print(json.dumps(payload, indent=2))
print("\nTrying to connect to server...\n")

# Try different ports
response = None
for port in ports:
    test_url = f"http://127.0.0.1:{port}/evm/balance"
    try:
        print(f"Trying port {port}...")
        response = requests.post(test_url, json=payload, timeout=5)
        url = test_url
        print(f"✓ Connected to port {port}\n")
        break
    except requests.exceptions.ConnectionError:
        print(f"✗ Port {port} not available")
        continue
    except requests.exceptions.Timeout:
        print(f"✗ Port {port} timeout")
        continue

if response is None:
    print("\n❌ Error: Could not connect to the server on any port.")
    print(f"   Tried ports: {ports}")
    print("   Make sure the FastAPI server is running.")
    exit(1)

print(f"URL: {url}")
print(f"Status Code: {response.status_code}")
print(f"Response Headers: {dict(response.headers)}")
print("\nResponse Body:")

try:
    
    if response.status_code == 200:
        result = response.json()
        print(json.dumps(result, indent=2))
        
        # Pretty print the balance
        if isinstance(result, list) and len(result) > 0:
            print("\n" + "=" * 60)
            print("Balance Summary:")
            print("=" * 60)
            for item in result:
                if isinstance(item, dict) and "balance" in item:
                    print(f"\n✓ Chain: {item.get('chain', 'N/A')}")
                    print(f"  Token: {item.get('token_symbol', 'N/A')}")
                    print(f"  Balance: {item.get('balance', 0):.6f}")
                    print(f"  Address: {item.get('address', 'N/A')}")
                    print(f"  Token Address: {item.get('token_address', 'N/A')}")
                    print(f"  Updated At: {item.get('updated_at', 'N/A')}")
                elif isinstance(item, dict) and "error" in item:
                    print(f"\n✗ Error for {item.get('chain', 'N/A')}: {item.get('error', 'Unknown error')}")
        elif isinstance(result, dict):
            if "balance" in result:
                print(f"\n✓ Balance: {result.get('balance', 0):.6f} {result.get('token_symbol', '')} on {result.get('chain', '')}")
    else:
        print(f"❌ Error Response ({response.status_code}):")
        print(response.text)
        
except Exception as e:
    print(f"❌ Error: {str(e)}")

print("\n" + "=" * 60)

