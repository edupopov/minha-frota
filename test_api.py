import json
import os
import tempfile
import unittest
from pathlib import Path

with tempfile.TemporaryDirectory() as directory:
    os.environ["LOCALAPPDATA"] = directory
    import app

    class ApiDataTests(unittest.TestCase):
        def setUp(self):
            app.APP_DIR = Path(directory) / "MinhaFrota"
            app.DB_PATH = app.APP_DIR / "test.sqlite3"
            if app.DB_PATH.exists(): app.DB_PATH.unlink()
            app.init_database()

        def test_seeds_three_independent_vehicles(self):
            with app.closing(app.connect()) as conn:
                items = app.rows(conn, "SELECT type, plate FROM vehicles ORDER BY id")
            self.assertEqual(3, len(items)); self.assertEqual("moto", items[2]["type"])

        def test_vehicle_validation(self):
            with self.assertRaises(ValueError): app.vehicle_payload({"type":"carro", "brand":"A", "model":"B", "year":2022, "plate":"errada"})

        def test_record_is_related_to_a_vehicle(self):
            with app.closing(app.connect()) as conn:
                conn.execute("INSERT INTO records(vehicle_id,kind,category,description,amount) VALUES(2,'despesa','Teste','Registro',10)")
                conn.commit()
                self.assertEqual(1, conn.execute("SELECT COUNT(*) FROM records WHERE vehicle_id=2").fetchone()[0])

    if __name__ == "__main__": unittest.main()
