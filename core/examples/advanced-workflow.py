#!/usr/bin/env python3
"""Exercise the new checked-out integration through externally signed CLI calls.

The private key, repository, decisions and answers are synthetic fixtures. This
script is not part of the product authority implementation or a user approval.
"""
from pathlib import Path
import argparse
import importlib.util
import json
import sys

helper = importlib.util.spec_from_file_location('verantyx_advanced_demo', Path(__file__).with_name('end-to-end.py'))
module = importlib.util.module_from_spec(helper)
helper.loader.exec_module(module)
Demo, write_json = module.Demo, module.write_json


class AdvancedDemo(Demo):
    def document(self, name, value):
        path = self.output / (name + '.json')
        write_json(path, value)
        return path

    def signed(self, label, *arguments):
        invocation = self.document(label + '-invocation', {'argv': list(map(str, arguments))})
        approval = self.output / (label + '-approval.json')
        signature = self.output / (label + '-approval.sig')
        self.cli(label + '-prepare', 'authority-request', '--invocation', invocation, '--output', approval, '--ttl', '600')
        signature.write_bytes(self.fixture_key.sign(approval.read_bytes()))
        result = self.cli(label, 'authority-execute', '--approval', approval, '--signature', signature)
        self.check(label + '-signature-verified', result['authorization'] == 'SIGNATURE_VERIFIED')
        self.last_approval, self.last_signature = approval, signature
        return result['result']

    def run_advanced(self):
        self.prepare()
        self.propose_run('candidate')
        self.cli('fixture-choice', 'decide', 'candidate', '--point', 'separation', '--choice', 'isolate',
                 '--reason', 'Artificial fixture choice; not user approval', '--key', 'choice')
        lease = self.cli('candidate-permission', 'authorize', 'candidate', '--action', 'writer', '--precedent', self.precedent,
                         '--ttl', '600', '--key', 'candidate-permission')['lease_id']
        executed = self.cli('candidate-execute', 'execute', 'candidate', '--lease', lease, '--precedent', self.precedent,
                            '--key', 'candidate-execute')
        self.check('isolated-candidate-tested', executed['execution']['status'] == 'CANDIDATE_TESTED')
        writer_view = self.cli('candidate-writer-history', 'writers')
        self.check('gateway-actual-process-registered', bool(writer_view['writers']))
        adoption = self.cli('adoption-proposal', 'adoption-propose', 'candidate', '--lease', lease, '--precedent', self.precedent,
                            '--key', 'adoption-proposal')['adoption_id']
        self.cli('adoption-permission', 'adoption-authorize', 'candidate', '--adoption', adoption, '--precedent', self.precedent,
                 '--reason', 'Artificial adoption review', '--ttl', '600', '--key', 'adoption-permission')
        adopted = self.cli('adoption-apply', 'adopt', 'candidate', '--adoption', adoption, '--precedent', self.precedent,
                           '--key', 'adoption-apply')
        self.check('adoption-did-not-change-checked-out-head', self.git('rev-parse', 'HEAD').decode().strip() == self.before_head)
        # Only this script's disposable repository is restored for a clean target.
        for name in ('.gitignore', 'calc.py', 'notes.txt', 'test_calc.py'):
            (self.project / name).write_bytes(self.git('show', 'HEAD:' + name))
        self.git('read-tree', 'HEAD')
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        self.fixture_key = Ed25519PrivateKey.generate()
        public = self.output / 'synthetic-public-key.pem'
        public.write_bytes(self.fixture_key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
        self.signed('enable-signatures', 'authority-enable', '--public-key', public)
        self.check('signatures-enabled', self.cli('signature-status', 'authority-status')['enabled'])
        self.cli('unsigned-integration-rejected', 'integration-plan', 'candidate', '--adoption', adoption, '--branch', 'main',
                 '--precedent', self.precedent, '--key', 'unsigned', expected=2, error='AUTHORITY_REQUIRED')
        planned = self.signed('integration-plan', 'integration-plan', 'candidate', '--adoption', adoption, '--branch', 'main',
                              '--mode', 'merge', '--precedent', self.precedent, '--key', 'integration-plan')
        identifier = planned['integration_id']
        common = ('candidate', '--integration', identifier, '--precedent', self.precedent)
        verified = self.signed('integration-verify', 'integration-verify', *common, '--key', 'integration-verify')
        self.check('integration-own-fixed-tests-pass', verified['integration']['status'] == 'VERIFIED')
        self.check('verification-is-not-adoption', self.git('rev-parse', 'HEAD').decode().strip() == self.before_head)
        self.signed('integration-permission', 'integration-authorize', *common, '--reason', 'Artificial final integration review',
                    '--ttl', '600', '--key', 'integration-permission')
        integrated = self.signed('integration-apply', 'integration-apply', *common, '--key', 'integration-apply')
        item = integrated['integration']
        self.check('checked-out-integration-completed', item['status'] == 'INTEGRATED')
        self.check('worktree-matches-adopted-code', (self.project / 'calc.py').read_text() == module.GOOD_SOURCE)
        self.check('merge-has-both-parents', self.git('show', '-s', '--format=%P', 'HEAD').decode().split() ==
                   [self.before_head, adopted['adoption']['receipt']['commit']])
        self.check('tracked-working-tree-and-index-clean', not self.git('diff', '--name-only').strip()
                   and not self.git('diff', '--cached', '--name-only').strip())
        self.cli('signed-command-not-repeated', 'authority-execute', '--approval', self.last_approval,
                 '--signature', self.last_signature, expected=2, error='AUTHORITY_USED')
        replayed = self.cli('integration-replay', 'replay', 'candidate')
        self.check('integration-replay-is-identical', replayed['projection_hash'] == integrated['projection_hash'])
        self.report['integration'] = {'id': identifier, 'receipt': item['receipt'], 'signature_mode': True}
        self.report['fixture_key'] = 'EPHEMERAL_SYNTHETIC_PRIVATE_KEY_NOT_SAVED'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    parser.add_argument('--cross', required=True)
    parser.add_argument('--precedent', required=True)
    args = parser.parse_args()
    output = Path(args.output).resolve()
    if output.exists():
        print('Refusing to overwrite an existing output directory', file=sys.stderr)
        return 2
    output.mkdir(parents=True)
    demo = AdvancedDemo(output, Path(args.cross).resolve(), Path(args.precedent).resolve())
    demo.report['format'] = 'verantyx.advanced-workflow.v1'
    try:
        demo.run_advanced()
        demo.report.update(passed=True, cli_invocations=len(demo.commands))
    except Exception as error:
        demo.report['error'] = {'type': type(error).__name__, 'message': str(error)}
    write_json(output / 'commands.json', demo.commands)
    write_json(output / 'report.json', demo.report)
    print(json.dumps({'passed': demo.report['passed'], 'commands': len(demo.commands), 'error': demo.report.get('error')}))
    return 0 if demo.report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
