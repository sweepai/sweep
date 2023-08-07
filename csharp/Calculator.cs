using System;

public class Calculator
{
    static void Main(string[] args)
    {
        Console.WriteLine("Enter the first number:");
        double num1 = Convert.ToDouble(Console.ReadLine());

        Console.WriteLine("Enter the operator:");
        string op = Console.ReadLine();

        Console.WriteLine("Enter the second number:");
        double num2 = Convert.ToDouble(Console.ReadLine());

        switch (op)
        {
            case "+":
                Console.WriteLine("The result is: " + Add(num1, num2));
                break;
            case "-":
                Console.WriteLine("The result is: " + Subtract(num1, num2));
                break;
            case "*":
                Console.WriteLine("The result is: " + Multiply(num1, num2));
                break;
            case "/":
                if (num2 != 0)
                {
                    Console.WriteLine("The result is: " + Divide(num1, num2));
                }
                else
                {
                    Console.WriteLine("Error! Division by zero.");
                }
                break;
            default:
                Console.WriteLine("Invalid operator.");
                break;
        }
    }

    static double Add(double num1, double num2)
    {
        return num1 + num2;
    }

    static double Subtract(double num1, double num2)
    {
        return num1 - num2;
    }

    static double Multiply(double num1, double num2)
    {
        return num1 * num2;
    }

    static double Divide(double num1, double num2)
    {
        return num1 / num2;
    }
}