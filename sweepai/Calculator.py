def add(num1, num2):
    return num1 + num2

def subtract(num1, num2):
    return num1 - num2

def multiply(num1, num2):
    return num1 * num2

def divide(num1, num2):
    if num2 != 0:
        return num1 / num2
    else:
        print("Error! Division by zero.")
        return None

def main():
    num1 = float(input("Enter the first number: "))
    operator = input("Enter the operator: ")
    num2 = float(input("Enter the second number: "))

    if operator == "+":
        result = add(num1, num2)
    elif operator == "-":
        result = subtract(num1, num2)
    elif operator == "*":
        result = multiply(num1, num2)
    elif operator == "/":
        result = divide(num1, num2)
    else:
        print("Invalid operator.")
        return

    print("The result is: ", result)

if __name__ == "__main__":
    main()