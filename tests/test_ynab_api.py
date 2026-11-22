import unittest
from unittest.mock import patch

import ynab_api


class AccountResolutionTests(unittest.TestCase):
    def setUp(self):
        self.accounts = [
            {"id": "acct-1", "name": "Bancolombia", "deleted": False},
            {"id": "acct-2", "name": "Efectivo", "deleted": False},
        ]

    def test_explicit_account_id_wins(self):
        selected = ynab_api.resolver_cuenta(self.accounts, account_id="acct-2")
        self.assertEqual(selected["name"], "Efectivo")

    def test_removed_account_does_not_silently_fallback(self):
        with patch.object(ynab_api, "ACCOUNT_NAME", "Pockets"):
            self.assertIsNone(ynab_api.resolver_cuenta(self.accounts))

    def test_single_active_account_is_selected(self):
        self.assertEqual(
            ynab_api.resolver_cuenta([self.accounts[0]])["id"], "acct-1"
        )

    def test_unknown_explicit_id_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "ya no está activa"):
            ynab_api.resolver_cuenta(self.accounts, account_id="deleted-id")


class AmountConversionTests(unittest.TestCase):
    def test_cop_amount_is_converted_to_negative_milliunits(self):
        self.assertEqual(ynab_api._a_milliunits("1234.56"), -1234560)

    def test_zero_and_negative_amounts_are_rejected(self):
        for amount in ("0", "-10"):
            with self.subTest(amount=amount):
                with self.assertRaises(ValueError):
                    ynab_api._a_milliunits(amount)

    def test_more_than_three_decimals_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "más de tres decimales"):
            ynab_api._a_milliunits("1.0001")


class TransactionBatchTests(unittest.TestCase):
    @patch.object(ynab_api, "_post")
    @patch.object(ynab_api, "obtener_cuentas")
    def test_batch_uses_current_account_and_one_request(self, get_accounts, post):
        get_accounts.return_value = [{"id": "acct-1", "deleted": False}]
        post.return_value = {"transactions": [{"id": "tx-1"}, {"id": "tx-2"}]}
        rows = [
            {"category_id": "cat-1", "proveedor": "Tienda", "precio": 1000,
             "fecha": "2026-11-22", "producto": "Producto A"},
            {"category_id": "cat-2", "proveedor": "Tienda", "precio": 2500,
             "fecha": "2026-11-22", "producto": "Producto B"},
        ]

        created = ynab_api.crear_transacciones("budget-1", "acct-1", rows)

        self.assertEqual(len(created), 2)
        post.assert_called_once()
        args, kwargs = post.call_args
        self.assertEqual(args[0], "/budgets/budget-1/transactions")
        self.assertEqual(len(args[1]["transactions"]), 2)
        self.assertEqual(args[1]["transactions"][0]["amount"], -1000000)
        self.assertEqual(args[1]["transactions"][1]["amount"], -2500000)

    @patch.object(ynab_api, "_post")
    @patch.object(ynab_api, "obtener_cuentas")
    def test_invalid_account_prevents_write(self, get_accounts, post):
        get_accounts.return_value = [{"id": "other-account"}]
        with self.assertRaisesRegex(RuntimeError, "ya no pertenece"):
            ynab_api.crear_transacciones("budget-1", "acct-1", [{
                "category_id": "cat-1", "proveedor": "Tienda", "precio": 1000,
                "fecha": "2026-11-22", "producto": "Producto A",
            }])
        post.assert_not_called()

    @patch.object(ynab_api, "_post")
    @patch.object(ynab_api, "obtener_cuentas")
    def test_missing_category_prevents_write(self, get_accounts, post):
        get_accounts.return_value = [{"id": "acct-1"}]
        with self.assertRaisesRegex(ValueError, "no tiene categoría"):
            ynab_api.crear_transacciones("budget-1", "acct-1", [{
                "category_id": None, "proveedor": "Tienda", "precio": 1000,
                "fecha": "2026-11-22", "producto": "Producto A",
            }])
        post.assert_not_called()


if __name__ == "__main__":
    unittest.main()
