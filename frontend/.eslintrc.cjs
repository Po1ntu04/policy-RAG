module.exports = {
  root: true,
  env: {
    browser: true,
    node: true,
    es2021: true,
  },
  extends: [
    'plugin:vue/vue3-essential',
    'eslint:recommended',
  ],
  parserOptions: {
    ecmaVersion: 2021,
    sourceType: 'module',
  },
  rules: {
    // 放宽样式相关规则，避免大规模格式改动
    quotes: 'off',
    semi: 'off',
    'no-extra-semi': 'off',
    'comma-dangle': 'off',

    // 其他
    'no-unused-vars': 'warn',
    'no-undef': 'off',
  },
}
