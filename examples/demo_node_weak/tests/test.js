const assert = require('assert');
const { isAdult } = require('../app');

assert.strictEqual(isAdult(20), true);
console.log('demo_node_weak tests passed');
