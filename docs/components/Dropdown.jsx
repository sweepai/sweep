import React, { useState } from 'react';

const Dropdown = ({ question, answer }) => {
  const [isOpen, setIsOpen] = useState(false);

  const toggleDropdown = () => {
    setIsOpen(!isOpen);
  };

  return (
    <div className="dropdown">
      <button onClick={toggleDropdown}>{question}</button>
      {isOpen && <p>{answer}</p>}
    </div>
  );
};

export default Dropdown