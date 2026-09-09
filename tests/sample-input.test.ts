import assert from 'node:assert/strict';
import { test } from 'node:test';
import { SampleInput } from '../lib/sample-input.ts';
function setup() {
  const editor = new SampleInput(); const sent: string[] = []; let interrupts = 0;
  return { editor, sent, feed: (value: string) => editor.feed(value, text => sent.push(text), () => interrupts++), interrupts: () => interrupts };
}
void test('split bracketed paste preserves Unicode and embedded commands until Enter', () => {
  const t = setup();
  t.feed('\x1b[20'); t.feed('0~最初\r\n/quit\n👩🏽‍💻\x1b[20'); t.feed('1~');
  assert.deepEqual(t.sent, []);
  assert.equal(t.editor.text, '最初\n/quit\n👩🏽‍💻');
  t.feed('\r'); assert.deepEqual(t.sent, ['最初\n/quit\n👩🏽‍💻']);
});
void test('Ctrl+J, Alt+Enter and backslash Enter insert newlines', () => {
  const t = setup(); t.feed('A\nB\x1b\rC\\\rD');
  assert.equal(t.editor.text, 'A\nB\nC\nD'); assert.deepEqual(t.sent, []);
  t.feed('\r'); assert.deepEqual(t.sent, ['A\nB\nC\nD']);
});
void test('completion acceptance and sending use separate Enter presses', () => {
  const t = setup(); t.feed('/di\t'); assert.equal(t.editor.completion, '/dictionary');
  t.feed('\r'); assert.deepEqual(t.sent, []); assert.equal(t.editor.text, '/dictionary');
  t.feed('\r'); assert.deepEqual(t.sent, ['/dictionary']);
});
void test('cursor editing deletes a full composed grapheme and restores history draft', () => {
  const t = setup(); t.feed('A👩🏽‍💻B\x1b[D\x7f');
  assert.equal(t.editor.text, 'AB'); t.feed('\r');
  t.feed('下書き\x1b[A'); assert.equal(t.editor.text, 'AB');
  t.feed('\x1b[B'); assert.equal(t.editor.text, '下書き');
});
void test('Ctrl+C clears input and interrupts only empty input', () => {
  const t = setup(); t.feed('未送信\x03'); assert.equal(t.editor.text, ''); assert.equal(t.interrupts(), 0);
  t.feed('\x03'); assert.equal(t.interrupts(), 1); assert.deepEqual(t.sent, []);
});
void test('escape sequences in pasted data cannot become executable commands or terminal output', () => {
  const t = setup(); t.feed('\x1b[200~/quit\x1b]52;c;secret\x07\x9d52;c;hidden\x9c\nnext\x1b[201~');
  assert.deepEqual(t.sent, []); assert.ok(!t.editor.text.includes('\x1b')); assert.ok(t.editor.text.includes('\nnext'));
  assert.ok(!t.editor.text.includes('\x9d')); assert.ok(!t.editor.text.includes('\x9c'));
});
void test('multiline up/down move within draft before navigating history', () => {
  const t = setup(); t.feed('first\r'); t.feed('一行\n二行');
  t.feed('\x1b[A'); assert.equal(t.editor.cursor, 2); assert.equal(t.editor.text, '一行\n二行');
  t.feed('\x1b[B'); assert.equal(t.editor.cursor, 5);
});
