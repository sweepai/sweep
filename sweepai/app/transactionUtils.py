import requests

def getTransactionHistory():
    # Function to retrieve transaction history
    response = requests.get("https://ethereum-api-endpoint.com/transaction-history")
    return response.json()

def cancelTransaction():
    # Function to handle cancelling transactions
    data = {"transaction": "Transaction details"}
    response = requests.post("https://ethereum-api-endpoint.com/cancel-transaction", data=data)
    return response.json()

def getNonce():
    # Function to get nonce
    response = requests.get("https://ethereum-api-endpoint.com/nonce")
    return response.json()