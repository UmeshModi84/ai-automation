/** @type {import('jest').Config} */
module.exports = {
  testEnvironment: "node",
  coverageDirectory: "coverage",
  collectCoverageFrom: ["src/**/*.js"],
  testMatch: ["**/tests/**/*.test.js"],
};
