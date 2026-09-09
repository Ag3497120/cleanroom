import assert from 'node:assert/strict';
import { test } from 'node:test';
import headless from '@xterm/headless';
import type { Terminal as BrowserTerminal } from '@xterm/xterm';
import { hostedSample } from '../lib/hosted-sample.ts';

const flush = (term: InstanceType<typeof headless.Terminal>) => new Promise<void>(resolve => term.write('', resolve));
const lines = (term: InstanceType<typeof headless.Terminal>) => Array.from({length:term.buffer.active.length}, (_, i) => term.buffer.active.getLine(i)?.translateToString(true) ?? '').join('\n');
void test('terminal sample renders Japanese input, completion, real recorded limits and next prompt', async () => {
  const term = new headless.Terminal({cols:100,rows:32,allowProposedApi:true});
  const sample = hostedSample(term as unknown as BrowserTerminal, () => {});
  for (let i=0;i<5;i++) await flush(term);
  assert.ok(lines(term).includes('VERANTYX'));
  assert.ok(lines(term).includes('AI未接続'));
  sample.input('日本語\n次の行');
  for (let i=0;i<5;i++) await flush(term);
  assert.ok(lines(term).includes('日本語'));
  assert.ok(lines(term).includes('次の行'));
  sample.input('\x03/demo\r');
  for (let i=0;i<5;i++) await flush(term);
  assert.ok(lines(term).includes('追加の判断は0件'));
  assert.ok(lines(term).includes('テスト用生成器'));
  assert.ok(lines(term).includes('本体には未採用'));
  assert.ok(lines(term).includes('❯'));
  sample.input('/di\t');
  for (let i=0;i<5;i++) await flush(term);
  assert.ok(lines(term).includes('/dictionary'));
  sample.dispose(); term.dispose();
});
