import requests

def getERC20():
    # Function to retrieve ERC20 tokens
    response = requests.get("https://ethereum-api-endpoint.com/erc20")
    return response.json()

def sendERC20():
    # Function to handle sending ERC20 tokens
    data = {"token": "ERC20 token details"}
    response = requests.post("https://ethereum-api-endpoint.com/send", data=data)
    return response.json()

def withdrawERC20():
    # Function to handle withdrawing ERC20 tokens
    data = {"token": "ERC20 token details"}
    response = requests.post("https://ethereum-api-endpoint.com/withdraw", data=data)
    return response.json()

def getAllTokens():
    # Function to retrieve all tokens
    response = requests.get("https://ethereum-api-endpoint.com/tokens")
    return response.json()

def getOwnedERC20s():
    # Function to retrieve owned ERC20 tokens
    response = requests.get("https://ethereum-api-endpoint.com/owned-erc20")
    return response.json()