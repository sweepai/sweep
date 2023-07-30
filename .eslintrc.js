module.exports = {
  parser: 'babel-eslint',
  parserOptions: {
    ecmaVersion: 6,
  },
  plugins: ['import'],
  rules: {
    'import/no-unresolved': 'error'
  }
};
