import os
import unittest

import index


class ApiLogicTests(unittest.TestCase):
    def test_clean_url(self):
        self.assertEqual(index.clean_url('https://example.com/deal'), 'https://example.com/deal')
        self.assertEqual(index.clean_url('javascript:alert(1)'), '')
        self.assertEqual(index.clean_url('https://user:pass@example.com'), '')
        self.assertEqual(index.clean_url('https://example.com/' + 'x' * 2100), '')

    def test_price_rule_respects_currency(self):
        item = {'target_price': 100, 'min_discount': None}
        self.assertTrue(index.qualifies(item, {'currency': 'BRL', 'price': 99, 'discount': 0}))
        self.assertFalse(index.qualifies(item, {'currency': 'USD', 'price': 1, 'discount': 0}))

    def test_discount_rule_is_independent(self):
        item = {'target_price': None, 'min_discount': 40}
        self.assertTrue(index.qualifies(item, {'currency': 'USD', 'price': 50, 'discount': 45}))
        self.assertFalse(index.qualifies(item, {'currency': 'USD', 'price': 50, 'discount': 20}))

    def test_jwt_token_validates_and_expires(self):
        os.environ['JWT_SECRET'] = 'test-secret-that-is-long-enough-for-hmac'
        token = index.issue_token()
        self.assertEqual(len(token.split('.')), 3)
        self.assertTrue(index.verify_token(token))
        self.assertFalse(index.verify_token(token + 'x'))

    def test_frequency_values(self):
        self.assertEqual(index.frequency_seconds('A cada 15 min'), 900)
        self.assertEqual(index.frequency_seconds('A cada hora'), 3600)
        self.assertEqual(index.frequency_seconds('A cada 6 horas'), 21600)
        self.assertEqual(index.frequency_seconds('Uma vez por dia'), 86400)


if __name__ == '__main__':
    unittest.main()
