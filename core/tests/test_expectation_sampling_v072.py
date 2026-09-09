"""Constrained sampling preserves source values; the host checks their use."""
from copy import deepcopy
import unittest

from jsonschema import Draft202012Validator
from verantyx.domain.asset_workflow import _typed_check_schema
from verantyx.ollama_schema import _portable


class SourceValueSamplingTests(unittest.TestCase):
    def schema(self, text, target='{"answer":7}'):
        context = {'request_ref': 'request', 'request': text, 'expectation_binding_version': 2,
                   'selected_files': [{'source_ref': 'output', 'path': 'output.json', 'text': target}]}
        return _portable(_typed_check_schema(context, source_value_sampling=True))

    def allowed(self, schema, value):
        return Draft202012Validator(schema).is_valid(
            {'id': 'value', 'kind': 'json.equals', 'pointer': '/answer', 'expected': value})

    def test_number_is_offered_without_target_value_or_wrapper(self):
        schema = self.schema('要求: /answer は数値の43。')
        self.assertTrue(self.allowed(schema, 43))
        for value in (7, '43', {'type': 'integer', 'value': 43}):
            self.assertFalse(self.allowed(schema, value))

    def test_objects_and_schema_named_keys_keep_exact_data(self):
        value = {'description': 'literal', 'title': 'required', '$schema': 'application data',
                 'enum': [1, 2], 'const': {'type': 'integer', 'value': 43}}
        import json
        schema = self.schema('要求するオブジェクト: ' + json.dumps(value))
        self.assertTrue(self.allowed(schema, value))
        wrong = deepcopy(value)
        del wrong['description']
        self.assertFalse(self.allowed(schema, wrong))
        # Nested constants in ordinary schemas must preserve the same data.
        self.assertEqual(_portable({'const': value}), {'const': value})

    def test_source_string_does_not_offer_a_numeric_value(self):
        schema = self.schema('JSONの値は "43" です。')
        self.assertTrue(self.allowed(schema, '43'))
        self.assertFalse(self.allowed(schema, 43))

    def test_large_choice_sets_fall_back_without_cutting_off_the_last_value(self):
        text = ' '.join(map(str, range(300)))
        schema = self.schema(text)
        self.assertTrue(self.allowed(schema, 299))
        # Sampling is generic in this case; the separate source-binding
        # validator remains responsible for rejecting unsupported values.
        self.assertTrue(self.allowed(schema, 400))

    def test_legacy_sampling_does_not_reinterpret_saved_contracts(self):
        self.assertTrue(self.allowed(_portable(_typed_check_schema()), {'type': 'integer', 'value': 43}))


if __name__ == '__main__':
    unittest.main()
