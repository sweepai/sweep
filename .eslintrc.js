module.exports = {
  parser: 'babel-eslint',
  parserOptions: {
    ecmaVersion: 8,
  },
  plugins: ['import'],
  rules: {
    'import/no-unresolved': 'error'
  }
};
