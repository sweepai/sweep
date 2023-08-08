import React from 'react';
import ReactDOM from 'react-dom';

function App() {
  return (
    <div className="App">
      <h1>Task Manager Application</h1>
    </div>
  );
}

ReactDOM.render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
  document.getElementById('root')
);