class CustomError extends Error {
    constructor(message) {
        super(message);
        this.name = "CustomError";
    }
}

class AnotherCustomError extends Error {
    constructor(message) {
        super(message);
        this.name = "AnotherCustomError";
    }
}

// Add more exceptions as needed...