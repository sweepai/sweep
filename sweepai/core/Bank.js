import React, { useState } from 'react';

const Bank = () => {
    const [balance, setBalance] = useState(0);
    const [error, setError] = useState('');

    const deposit = (amount) => {
        setBalance(balance + amount);
        setError('');
    };

    const withdraw = (amount) => {
        if (balance >= amount) {
            setBalance(balance - amount);
            setError('');
        } else {
            setError('Insufficient balance');
        }
    };

    return (
        <div>
            <h2>Balance: {balance}</h2>
            <form onSubmit={(e) => {
                e.preventDefault();
                deposit(parseFloat(e.target.elements.amount.value));
            }}>
                <input type="number" name="amount" min="0" step="0.01" required />
                <button type="submit">Deposit</button>
            </form>
            <form onSubmit={(e) => {
                e.preventDefault();
                withdraw(parseFloat(e.target.elements.amount.value));
            }}>
                <input type="number" name="amount" min="0" step="0.01" required />
                <button type="submit">Withdraw</button>
            </form>
            {error && <p>{error}</p>}
        </div>
    );
};

export default Bank;