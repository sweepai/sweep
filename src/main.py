from src.new_feature import NewFeature

def main():
    # Create an instance of NewFeature
    new_feature = NewFeature()
    
    # Call the execute_feature method and handle the result
    result = new_feature.execute_feature()
    if result > 10:
        print("Feature executed successfully.")
    else:
        print("Feature execution failed.")
    # Print the result
    print(result)

if __name__ == "__main__":
    main()