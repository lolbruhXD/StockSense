import tempfile
import unittest
from pathlib import Path

from stocksense.database import connect, initialize
from stocksense import inventory


class InventoryFlowTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "test.sqlite3"
        initialize(self.path)
        self.db = connect(self.path)
        self.db.execute("INSERT INTO users(name,email,password_hash,salt) VALUES ('Test','test@example.com','x','y')")
        self.main = inventory.create_warehouse(self.db, {"name": "Main", "code": "WH1"})
        self.second = inventory.create_warehouse(self.db, {"name": "Second", "code": "WH2"})
        self.main_location = self.db.execute("SELECT id FROM locations WHERE warehouse_id=?", (self.main,)).fetchone()[0]
        self.second_location = self.db.execute("SELECT id FROM locations WHERE warehouse_id=?", (self.second,)).fetchone()[0]
        self.product = inventory.create_product(self.db, {"sku": "ROD-01", "name": "Steel rods", "uom": "kg", "reorder_point": 10})

    def tearDown(self):
        self.db.close()
        self.directory.cleanup()

    def operation(self, kind, amount, source=None, destination=None):
        return inventory.create_operation(self.db, {
            "type": kind, "from_location_id": source, "to_location_id": destination,
            "lines": [{"product_id": self.product, "quantity": amount}],
        }, 1)

    def post(self, operation_id):
        inventory.set_status(self.db, operation_id, "ready")
        inventory.validate_operation(self.db, operation_id)

    def balance(self, location):
        row = self.db.execute("SELECT quantity_milli FROM stock_levels WHERE product_id=? AND location_id=?",
                              (self.product, location)).fetchone()
        return (row[0] if row else 0) / 1000

    def test_complete_stock_flow_and_ledger(self):
        receipt = self.operation("receipt", 100.5, destination=self.main_location)
        self.assertEqual(self.balance(self.main_location), 0)
        self.post(receipt)
        transfer = self.operation("transfer", 30, self.main_location, self.second_location)
        self.post(transfer)
        delivery = self.operation("delivery", 20, self.second_location)
        inventory.set_status(self.db, delivery, "submit")
        inventory.set_status(self.db, delivery, "pick")
        inventory.set_status(self.db, delivery, "pack")
        inventory.set_status(self.db, delivery, "ready")
        inventory.validate_operation(self.db, delivery)
        adjustment = self.operation("adjustment", 8, self.second_location)
        self.post(adjustment)
        self.assertEqual(self.balance(self.main_location), 70.5)
        self.assertEqual(self.balance(self.second_location), 8)
        self.assertEqual(sum(row["delta"] for row in inventory.history(self.db)), 78.5)
        self.assertEqual(len(inventory.history(self.db)), 5)

    def test_failed_delivery_does_not_change_stock_or_status(self):
        receipt = self.operation("receipt", 3, destination=self.main_location)
        self.post(receipt)
        delivery = self.operation("delivery", 4, self.main_location)
        inventory.set_status(self.db, delivery, "submit")
        inventory.set_status(self.db, delivery, "pick")
        inventory.set_status(self.db, delivery, "pack")
        inventory.set_status(self.db, delivery, "ready")
        with self.assertRaisesRegex(inventory.InventoryError, "Not enough"):
            inventory.validate_operation(self.db, delivery)
        self.assertEqual(self.balance(self.main_location), 3)
        self.assertEqual(inventory.operation_detail(self.db, delivery)["status"], "ready")
        self.assertEqual(len(inventory.history(self.db)), 1)

    def test_duplicate_validation_is_rejected(self):
        receipt = self.operation("receipt", 5, destination=self.main_location)
        self.post(receipt)
        with self.assertRaisesRegex(inventory.InventoryError, "ready"):
            inventory.validate_operation(self.db, receipt)
        self.assertEqual(self.balance(self.main_location), 5)

    def test_adjustment_can_set_zero(self):
        receipt = self.operation("receipt", 5, destination=self.main_location)
        self.post(receipt)
        adjustment = self.operation("adjustment", 0, self.main_location)
        self.post(adjustment)
        self.assertEqual(self.balance(self.main_location), 0)

    def test_transfer_is_atomic_when_source_lacks_stock(self):
        transfer = self.operation("transfer", 1, self.main_location, self.second_location)
        inventory.set_status(self.db, transfer, "ready")
        with self.assertRaises(inventory.InventoryError):
            inventory.validate_operation(self.db, transfer)
        self.assertEqual(self.balance(self.second_location), 0)
        self.assertEqual(len(inventory.history(self.db)), 0)


if __name__ == "__main__":
    unittest.main()
