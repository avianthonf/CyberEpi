module.exports = {
  root: true,
  extends: ['expo', 'prettier'],
  plugins: ['prettier', '@typescript-eslint'],
  rules: {
    'prettier/prettier': 'error',
    '@typescript-eslint/no-unused-vars': 'error',
    '@typescript-eslint/explicit-function-return-type': 'off',
    '@typescript-eslint/explicit-module-boundary-types': 'off',
    '@typescript-eslint/no-explicit-any': 'warn',
    'react-hooks/exhaustive-deps': 'warn',
    // tsc --noEmit is the authoritative import/type checker; the eslint
    // import resolver cannot handle the `@/*` tsconfig path alias here.
    'import/no-unresolved': 'off',
    'import/namespace': 'off',
  },
  overrides: [
    {
      files: ['*.ts', '*.tsx'],
      rules: {
        '@typescript-eslint/no-shadow': ['error'],
        'no-shadow': 'off',
        'no-undef': 'off',
      },
    },
    {
      files: ['metro.config.js', 'babel.config.js', 'jest.config.js'],
      env: {node: true},
      globals: {__dirname: 'readonly'},
    },
  ],
  ignorePatterns: ['node_modules/', 'dist/', '.expo/', 'coverage/'],
};
