import React, { useState } from 'react';

const Dropdown = ({ question, answer }) => {
  const [isOpen, setIsOpen] = useState(false);

  const toggleDropdown = () => {
    setIsOpen(!isOpen);
  };

  return (
    <div className="dropdown">
      <h2 onClick={toggleDropdown}>{question}</h2>
      {isOpen && <p>{answer}</p>}
    </div>
  );
};

export default Dropdown
