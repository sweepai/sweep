import requests

def getCreditBalance():
    # Function to get the credit balance
    response = requests.get("https://ethereum-api-endpoint.com/credit-balance")
    return response.json()

def getRefererInfo():
    # Function to get the referer info
    response = requests.get("https://ethereum-api-endpoint.com/referer-info")
    return response.json()

def submitReferenceCode():
    # Function to submit the reference code
    data = {"code": "Reference code details"}
    response = requests.post("https://ethereum-api-endpoint.com/submit-reference-code", data=data)
    return response.json()

def getRewardInfo():
    # Function to get the reward info
    response = requests.get("https://ethereum-api-endpoint.com/reward-info")
    return response.json()

def getIsProxyWalletUser():
    # Function to check if a user is a proxy wallet user
    response = requests.get("https://ethereum-api-endpoint.com/is-proxy-wallet-user")
    return response.json()

def registerNewWallet():
    # Function to register a new wallet
    data = {"wallet": "Wallet details"}
    response = requests.post("https://ethereum-api-endpoint.com/register-new-wallet", data=data)
    return response.json()