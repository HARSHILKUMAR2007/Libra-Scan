import test from 'node:test';
import assert from 'node:assert/strict';
import { pairFiles, parseFileName } from '../frontend/js/pairing.js';

test('parseFileName detects front and back patterns', () => {
  assert.deepEqual(parseFileName('zero-to-one_front.jpg'), { base: 'zero-to-one', displayBase: 'zero-to-one', side: 'front' });
  assert.deepEqual(parseFileName('zero-to-one_back.jpg'), { base: 'zero-to-one', displayBase: 'zero-to-one', side: 'back' });
  assert.deepEqual(parseFileName('clean_f.png'), { base: 'clean', displayBase: 'clean', side: 'front' });
  assert.deepEqual(parseFileName('clean_b.png'), { base: 'clean', displayBase: 'clean', side: 'back' });
  assert.deepEqual(parseFileName('dune-1.jpeg'), { base: 'dune', displayBase: 'dune', side: 'front' });
  assert.deepEqual(parseFileName('dune-2.jpeg'), { base: 'dune', displayBase: 'dune', side: 'back' });
  assert.deepEqual(parseFileName('novel_cover.webp'), { base: 'novel', displayBase: 'novel', side: 'front' });
  assert.deepEqual(parseFileName('novel_rear.webp'), { base: 'novel', displayBase: 'novel', side: 'back' });
  assert.deepEqual(parseFileName('random-file.jpg'), { base: 'random-file', displayBase: 'random-file', side: null });
});

test('pairFiles matches _front and _back into pairs', () => {
  const files = [
    { name: 'zero-to-one_front.jpg' },
    { name: 'zero-to-one_back.jpg' },
  ];
  const result = pairFiles(files);
  assert.equal(result.pairs.length, 1);
  assert.equal(result.pairs[0].front.name, 'zero-to-one_front.jpg');
  assert.equal(result.pairs[0].back.name, 'zero-to-one_back.jpg');
  assert.equal(result.unpaired.length, 0);
  assert.equal(result.pairedByOrder, false);
});

test('pairFiles matches _f and _b and -1 and -2', () => {
  const files = [
    { name: 'clean_code_f.png' },
    { name: 'clean_code_b.png' },
    { name: 'sci_fi-1.png' },
    { name: 'sci_fi-2.png' },
  ];
  const result = pairFiles(files);
  assert.equal(result.pairs.length, 2);
  assert.equal(result.pairs[0].front.name, 'clean_code_f.png');
  assert.equal(result.pairs[0].back.name, 'clean_code_b.png');
  assert.equal(result.pairs[1].front.name, 'sci_fi-1.png');
  assert.equal(result.pairs[1].back.name, 'sci_fi-2.png');
  assert.equal(result.pairedByOrder, false);
});

test('pairFiles falls back to order when no pattern is found', () => {
  const files = [
    { name: 'photo_a.jpg' },
    { name: 'photo_b.jpg' },
    { name: 'photo_c.jpg' },
    { name: 'photo_d.jpg' },
  ];
  const result = pairFiles(files);
  assert.equal(result.pairs.length, 2);
  assert.equal(result.pairs[0].front.name, 'photo_a.jpg');
  assert.equal(result.pairs[0].back.name, 'photo_b.jpg');
  assert.equal(result.pairs[1].front.name, 'photo_c.jpg');
  assert.equal(result.pairs[1].back.name, 'photo_d.jpg');
  assert.equal(result.pairedByOrder, true);
  assert.equal(result.unpaired.length, 0);
});

test('pairFiles handles odd number of files by leaving leftover in unpaired', () => {
  const files = [
    { name: 'book1.jpg' },
    { name: 'book2.jpg' },
    { name: 'book3.jpg' },
  ];
  const result = pairFiles(files);
  assert.equal(result.pairs.length, 1);
  assert.equal(result.unpaired.length, 1);
  assert.equal(result.unpaired[0].name, 'book3.jpg');
  assert.equal(result.pairedByOrder, true);
});

test('pairFiles puts unmatched back covers in unpaired list', () => {
  const files = [
    { name: 'matched_front.jpg' },
    { name: 'matched_back.jpg' },
    { name: 'orphan_back.jpg' },
  ];
  const result = pairFiles(files);
  assert.equal(result.pairs.length, 1);
  assert.equal(result.unpaired.length, 1);
  assert.equal(result.unpaired[0].name, 'orphan_back.jpg');
});
